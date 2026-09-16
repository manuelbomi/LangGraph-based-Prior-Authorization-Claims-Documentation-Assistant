"""REST + SSE API for prior-authorization requests: upload, the bundled-
sample-referral catalog (for a zero-setup demo), starting/streaming/resuming
a PA request's graph run, serving the original chart excerpt back to the
frontend, and updating a request's post-drafting lifecycle status (the
"track over days/weeks" endpoint).

Concurrency model (intentionally simple for a tutorial app): each active PA
request run gets one `asyncio.Queue` in `request.app.state.run_queues`, fed
by a background `asyncio.Task` that drives `graph.astream(...)`. The SSE
endpoint just relays whatever lands on that queue. Every event is also
persisted to the `pa_requests` table as it happens, so a client that
reconnects (or a run that finished while nobody was watching) can still be
inspected via `GET /pa-requests/{id}` / replayed via
`GET /pa-requests/{id}/stream`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from langgraph.types import Command
from sqlalchemy import select

from app.api.schemas import (
    PARequestCreateResponse,
    PARequestDetail,
    PARequestListResponse,
    PARequestSummary,
    HumanDecisionRequest,
    PayersResponse,
    SampleDocument,
    SamplesResponse,
    StatusUpdateRequest,
)
from app.config import get_settings
from app.db.models import PARequest, Patient
from app.db.session import SessionLocal
from app.tools.document_ingest import detect_file_kind

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pa-requests", tags=["pa-requests"])

_ALLOWED_EXTENSIONS = {".txt", ".pdf"}

# Fictitious payer names offered in the "select a payer" dropdown. See
# sample-data/README.md -- these do not represent any real insurance
# company, and their "policies" (sample-data/payer-policies/) are invented.
PAYERS: list[str] = ["Meridian Health Plan", "Cascade Community Health", "Beacon Preferred Insurance"]

# The catalog backing the "or pick one of the bundled sample referrals"
# zero-setup demo path -- see sample-data/README.md for what each one is.
# `suggested_patient_id`/`suggested_payer` are hints the frontend uses to
# preselect values; any sample can be run for any patient/payer combination.
SAMPLE_CATALOG: list[dict[str, str]] = [
    {
        "id": "lumbar-mri-jordan-blake",
        "label": "Jordan Blake - chronic low back pain, lumbar MRI referral",
        "relative_path": "referrals/lumbar_mri_referral_jordan_blake.txt",
        "suggested_patient_id": "jordan-blake",
        "suggested_payer": "Meridian Health Plan",
    },
    {
        "id": "adalimumab-casey-rivera",
        "label": "Casey Rivera - psoriatic arthritis, adalimumab request",
        "relative_path": "referrals/specialty_medication_adalimumab_casey_rivera.txt",
        "suggested_patient_id": "casey-rivera",
        "suggested_payer": "Cascade Community Health",
    },
    {
        "id": "pt-extension-morgan-ellis",
        "label": "Morgan Ellis - post-op knee, physical therapy extension",
        "relative_path": "referrals/pt_extension_request_morgan_ellis.txt",
        "suggested_patient_id": "morgan-ellis",
        "suggested_payer": "Beacon Preferred Insurance",
    },
    {
        "id": "lumbar-mri-sam-okafor",
        "label": "Sam Okafor - new/acute low back pain, lumbar MRI request",
        "relative_path": "referrals/lumbar_mri_referral_sam_okafor.txt",
        "suggested_patient_id": "sam-okafor",
        "suggested_payer": "Meridian Health Plan",
    },
]
_SAMPLE_BY_ID = {s["id"]: s for s in SAMPLE_CATALOG}

# Allowed forward transitions for the post-drafting tracking endpoint. This
# is a plain field update -- not a graph re-entry -- modeling the real-world
# "track status over days/weeks" burden. See app/db/models.py::PARequest.
_ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "ready_to_submit": {"submitted"},
    "submitted": {"approved", "denied", "more_info_requested"},
    "more_info_requested": {"submitted"},
}


def _to_summary(pa_request: PARequest) -> PARequestSummary:
    return PARequestSummary(
        id=pa_request.id,
        patient_id=pa_request.patient_id,
        payer_name=pa_request.payer_name,
        original_filename=pa_request.original_filename,
        status=pa_request.status,  # type: ignore[arg-type]
        final_status=pa_request.final_status,
        created_at=pa_request.created_at,
        updated_at=pa_request.updated_at,
    )


def _sse(event_type: str, data: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"


async def _run_graph(request: Request, thread_id: str, graph_input: Any) -> None:
    """Background task: drive the graph, persist + broadcast each step."""
    graph = request.app.state.graph
    queue: asyncio.Queue = request.app.state.run_queues[thread_id]
    config = {"configurable": {"thread_id": thread_id}}

    def _set_status(status: str, **extra: Any) -> None:
        with SessionLocal() as db:
            req = db.get(PARequest, thread_id)
            if req is None:
                return
            req.status = status
            for k, v in extra.items():
                setattr(req, k, v)
            db.commit()

    def _record_event(node_output: dict[str, Any]) -> None:
        trace_items = node_output.get("trace", [])
        with SessionLocal() as db:
            req = db.get(PARequest, thread_id)
            if req is None:
                return
            req.trace = [*req.trace, *trace_items]
            merged_snapshot = {**req.state_snapshot, **{k: v for k, v in node_output.items() if k != "trace"}}
            req.state_snapshot = merged_snapshot
            if "clinical_summary" in node_output:
                req.clinical_summary = node_output["clinical_summary"]
            if "criteria_checklist" in node_output:
                req.criteria_checklist = node_output["criteria_checklist"]
            if "draft_form" in node_output:
                req.draft_form = node_output["draft_form"]
            db.commit()

    try:
        _set_status("running")
        async for event in graph.astream(graph_input, config=config, stream_mode="updates"):
            if "__interrupt__" in event:
                interrupt_obj = event["__interrupt__"][0]
                payload = dict(interrupt_obj.value)
                with SessionLocal() as db:
                    req = db.get(PARequest, thread_id)
                    if req is not None:
                        req.status = "awaiting_staff_review"
                        req.state_snapshot = {**req.state_snapshot, "interrupt": payload}
                        db.commit()
                await queue.put(_sse("interrupt", payload))
                continue

            for node_name, node_output in event.items():
                if not isinstance(node_output, dict):
                    continue
                _record_event(node_output)
                await queue.put(
                    _sse(
                        "node",
                        {
                            "node": node_name,
                            "output": {k: v for k, v in node_output.items() if k != "trace"},
                            "trace": node_output.get("trace", []),
                        },
                    )
                )
                if node_name != "staff_review":
                    _set_status("running")

        # Loop ended without an interrupt -> graph ran to completion (END).
        state = await graph.aget_state(config)
        if not state.next:  # no pending nodes => finished
            values = state.values
            status = values.get("status", "ready_to_submit")
            final_status = values.get("final_status")
            with SessionLocal() as db:
                req = db.get(PARequest, thread_id)
                if req is not None:
                    req.status = status
                    req.final_status = final_status
                    merged_snapshot = {**req.state_snapshot, **values}
                    req.state_snapshot = merged_snapshot
                    req.clinical_summary = values.get("clinical_summary", req.clinical_summary)
                    req.criteria_checklist = values.get("criteria_checklist", req.criteria_checklist)
                    req.draft_form = values.get("draft_form", req.draft_form)
                    if status != "rejected":
                        req.status_history = [
                            *req.status_history,
                            {"status": status, "timestamp": datetime.now(timezone.utc).isoformat(), "note": "Drafting complete."},
                        ]
                    db.commit()
            await queue.put(_sse("done", {"status": status, "final_status": final_status}))
    except Exception as exc:  # noqa: BLE001
        logger.exception("PA request run %s failed", thread_id)
        with SessionLocal() as db:
            req = db.get(PARequest, thread_id)
            if req is not None:
                req.status = "error"
                req.error = str(exc)
                db.commit()
        await queue.put(_sse("error", {"message": str(exc)}))
    finally:
        await queue.put(None)  # sentinel: close the SSE stream


def _start_background_run(request: Request, thread_id: str, graph_input: Any) -> None:
    queue: asyncio.Queue = asyncio.Queue()
    request.app.state.run_queues[thread_id] = queue
    task = asyncio.create_task(_run_graph(request, thread_id, graph_input))
    request.app.state.run_tasks[thread_id] = task


async def start_pa_request_run(
    request: Request,
    *,
    patient_id: str,
    payer_name: str,
    file_path: str,
    original_filename: str,
    run_id: str | None = None,
) -> PARequestCreateResponse:
    """Create a `PARequest` row and kick off the graph in the background.
    Shared by both the upload and run-a-sample-referral endpoints below."""
    if payer_name not in PAYERS:
        raise HTTPException(400, f"unknown payer {payer_name!r}. Allowed: {PAYERS}")

    with SessionLocal() as db:
        patient = db.get(Patient, patient_id)
        if patient is None:
            raise HTTPException(404, f"patient {patient_id!r} not found")
        patient_name = patient.name
        patient_dob = patient.date_of_birth
        patient_member_id = patient.member_id
        provider_name = patient.provider_name
        provider_npi = patient.provider_npi

    run_id = run_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        req = PARequest(
            id=run_id,
            patient_id=patient_id,
            payer_name=payer_name,
            original_filename=original_filename,
            status="pending",
            clinical_summary={},
            criteria_checklist=[],
            draft_form={},
            trace=[],
            state_snapshot={},
            status_history=[],
            created_at=now,
            updated_at=now,
        )
        db.add(req)
        db.commit()

    _start_background_run(
        request,
        run_id,
        {
            "file_path": file_path,
            "original_filename": original_filename,
            "patient_id": patient_id,
            "patient_name": patient_name,
            "patient_dob": patient_dob,
            "patient_member_id": patient_member_id,
            "payer_name": payer_name,
            "provider_name": provider_name,
            "provider_npi": provider_npi,
        },
    )
    return PARequestCreateResponse(
        id=run_id, patient_id=patient_id, payer_name=payer_name, status="pending", original_filename=original_filename
    )


@router.get("/payers", response_model=PayersResponse)
async def list_payers() -> PayersResponse:
    return PayersResponse(payers=PAYERS)


@router.get("/samples", response_model=SamplesResponse)
async def list_samples() -> SamplesResponse:
    return SamplesResponse(
        samples=[
            SampleDocument(
                id=s["id"],
                label=s["label"],
                suggested_patient_id=s["suggested_patient_id"],
                suggested_payer=s["suggested_payer"],
            )
            for s in SAMPLE_CATALOG
        ]
    )


@router.post("/samples/{sample_id}/run", response_model=PARequestCreateResponse)
async def run_sample_referral(
    sample_id: str, request: Request, patient_id: str = Form(...), payer_name: str = Form(...)
) -> PARequestCreateResponse:
    entry = _SAMPLE_BY_ID.get(sample_id)
    if entry is None:
        raise HTTPException(404, "unknown sample id")

    settings = get_settings()
    src_path = os.path.join(settings.sample_data_dir, entry["relative_path"])
    if not os.path.exists(src_path):
        raise HTTPException(500, f"sample file missing on server: {entry['relative_path']}")

    return await start_pa_request_run(
        request,
        patient_id=patient_id,
        payer_name=payer_name,
        file_path=src_path,
        original_filename=os.path.basename(entry["relative_path"]),
    )


@router.post("/upload", response_model=PARequestCreateResponse)
async def upload_pa_request(
    request: Request, patient_id: str = Form(...), payer_name: str = Form(...), file: UploadFile = File(...)
) -> PARequestCreateResponse:
    filename = file.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type {ext or '(none)'!r}. Allowed: {sorted(_ALLOWED_EXTENSIONS)}")
    detect_file_kind(filename)  # raises if truly unrecognized

    settings = get_settings()
    run_id = str(uuid.uuid4())
    dest_dir = os.path.join(settings.upload_dir, run_id)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, filename)

    contents = await file.read()
    with open(dest_path, "wb") as f:
        f.write(contents)

    return await start_pa_request_run(
        request, patient_id=patient_id, payer_name=payer_name, file_path=dest_path, original_filename=filename, run_id=run_id
    )


@router.get("/{pa_request_id}/file")
async def get_pa_request_source_file(pa_request_id: str):
    """Serve the original uploaded/sample chart excerpt back to the
    frontend, so the request detail view can show the source alongside its
    structured record."""
    with SessionLocal() as db:
        req = db.get(PARequest, pa_request_id)
    if req is None:
        raise HTTPException(404, "PA request not found")

    settings = get_settings()
    candidate = os.path.join(settings.upload_dir, pa_request_id, req.original_filename)
    if not os.path.exists(candidate):
        for sample in SAMPLE_CATALOG:
            if os.path.basename(sample["relative_path"]) == req.original_filename:
                candidate = os.path.join(settings.sample_data_dir, sample["relative_path"])
                break

    if not os.path.exists(candidate):
        raise HTTPException(404, "original chart excerpt not found on the server")

    return FileResponse(candidate, filename=req.original_filename)


@router.post("/{pa_request_id}/resume", response_model=PARequestCreateResponse)
async def resume_pa_request(pa_request_id: str, body: HumanDecisionRequest, request: Request) -> PARequestCreateResponse:
    with SessionLocal() as db:
        req = db.get(PARequest, pa_request_id)
        if req is None:
            raise HTTPException(404, "PA request not found")
        if req.status != "awaiting_staff_review":
            raise HTTPException(409, f"PA request is not awaiting staff review (status={req.status})")
        patient_id = req.patient_id
        payer_name = req.payer_name
        original_filename = req.original_filename

    _start_background_run(
        request,
        pa_request_id,
        Command(
            resume={
                "decision": body.decision,
                "feedback": body.feedback,
                "corrected_draft_form": body.corrected_draft_form,
                "corrected_criteria_checklist": body.corrected_criteria_checklist,
            }
        ),
    )
    return PARequestCreateResponse(
        id=pa_request_id, patient_id=patient_id, payer_name=payer_name, status="running", original_filename=original_filename
    )


@router.get("/{pa_request_id}/stream")
async def stream_pa_request(pa_request_id: str, request: Request) -> StreamingResponse:
    async def event_source():
        queue: asyncio.Queue | None = request.app.state.run_queues.get(pa_request_id)

        if queue is None:
            # No live background task (already finished, or the server was
            # restarted after this request reached a terminal/awaiting
            # state). Replay what's durably stored instead of streaming live.
            with SessionLocal() as db:
                req = db.get(PARequest, pa_request_id)
            if req is None:
                yield _sse("error", {"message": "PA request not found"})
                return
            yield _sse(
                "replay",
                {
                    "status": req.status,
                    "trace": req.trace,
                    "state_snapshot": req.state_snapshot,
                    "final_status": req.final_status,
                },
            )
            if req.status == "awaiting_staff_review":
                interrupt_payload = req.state_snapshot.get("interrupt", {})
                yield _sse("interrupt", interrupt_payload)
            yield _sse("done", {"status": req.status, "final_status": req.final_status})
            return

        while True:
            item = await queue.get()
            if item is None:
                break
            yield item

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("", response_model=PARequestListResponse)
async def list_pa_requests(patient_id: str | None = None, status: str | None = None) -> PARequestListResponse:
    with SessionLocal() as db:
        stmt = select(PARequest).order_by(PARequest.created_at.desc())
        if patient_id:
            stmt = stmt.where(PARequest.patient_id == patient_id)
        if status:
            stmt = stmt.where(PARequest.status == status)
        rows = db.execute(stmt).scalars().all()
        return PARequestListResponse(pa_requests=[_to_summary(r) for r in rows])


@router.get("/{pa_request_id}", response_model=PARequestDetail)
async def get_pa_request(pa_request_id: str) -> PARequestDetail:
    with SessionLocal() as db:
        req = db.get(PARequest, pa_request_id)
        if req is None:
            raise HTTPException(404, "PA request not found")
        return PARequestDetail(
            **_to_summary(req).model_dump(),
            clinical_summary=req.clinical_summary,
            criteria_checklist=req.criteria_checklist,
            draft_form=req.draft_form,
            trace=req.trace,
            state_snapshot=req.state_snapshot,
            status_history=req.status_history,
            error=req.error,
        )


@router.post("/{pa_request_id}/status", response_model=PARequestDetail)
async def update_pa_request_status(pa_request_id: str, body: StatusUpdateRequest) -> PARequestDetail:
    """Update a PA request's post-drafting lifecycle status.

    This is a PLAIN FIELD UPDATE, not a graph re-entry -- it models the
    real-world burden of tracking a prior-authorization request's status
    (submitted -> approved / denied / more info requested) over the days to
    weeks a payer typically takes to decide, without needing to re-run any
    LLM step. See the root README's "Why LangGraph" section.
    """
    with SessionLocal() as db:
        req = db.get(PARequest, pa_request_id)
        if req is None:
            raise HTTPException(404, "PA request not found")

        allowed = _ALLOWED_STATUS_TRANSITIONS.get(req.status, set())
        if body.status not in allowed:
            raise HTTPException(
                409,
                f"Cannot move a PA request from status={req.status!r} to {body.status!r}. "
                f"Allowed next statuses: {sorted(allowed) or 'none (terminal status)'}",
            )

        req.status = body.status
        req.status_history = [
            *req.status_history,
            {"status": body.status, "timestamp": datetime.now(timezone.utc).isoformat(), "note": body.note},
        ]
        db.commit()
        db.refresh(req)

        return PARequestDetail(
            **_to_summary(req).model_dump(),
            clinical_summary=req.clinical_summary,
            criteria_checklist=req.criteria_checklist,
            draft_form=req.draft_form,
            trace=req.trace,
            state_snapshot=req.state_snapshot,
            status_history=req.status_history,
            error=req.error,
        )
