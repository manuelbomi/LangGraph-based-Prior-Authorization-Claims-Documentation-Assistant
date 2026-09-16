"""LangGraph node implementations for the Prior-Authorization & Claims
Documentation Assistant.

Six real (non-stub) nodes, wired as a straight line (no conditional
routing -- every request goes through the same pipeline):

    ingest -> extract_clinical_summary -> match_policy_criteria
    -> draft_pa_request -> staff_review -> finalize

  ingest                  - reads raw text from a .txt file or a .pdf's text
                            layer (pdfplumber)
  extract_clinical_summary - LLM extracts a `ClinicalSummary`: diagnosis,
                            requested service, symptom duration, prior
                            treatments tried, exam findings, relevant
                            history -- constrained to only structure what
                            the referring clinician already wrote
  match_policy_criteria   - semantic search (Milvus Lite) of the selected
                            payer's medical-necessity criteria for the
                            requested service, then an LLM assesses each
                            criterion as met/unmet/unclear with evidence
                            quoted from the chart -- a DRAFT ASSESSMENT FOR
                            STAFF REVIEW, never a coverage decision
  draft_pa_request        - assembles a filled draft PA request form:
                            trusted patient/provider/payer identifiers (from
                            state, sourced from Postgres) plus an LLM-chosen
                            procedure/diagnosis code (from a small fixed
                            reference list, never invented) and a clinical
                            justification narrative
  staff_review            - interrupt() pauses the graph for a licensed
                            staff member/clinician's review/edit/approval --
                            the mandatory safety gate; nothing is submitted
                            to a payer without it
  finalize                - records the staff decision; `ready_to_submit`
                            is a DRAFTING outcome only, never a submission

This app is strictly an administrative documentation assistant. It never
diagnoses, recommends treatment, offers medical advice, or decides coverage
or medical necessity -- see the root README's "Scope & Safety" section and
the seeded prompt text in `app/prompts/seed_prompts.py`.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from langgraph.types import interrupt

from app.graph.pa_schema import ClinicalSummary, CriteriaChecklist, DraftCodesAndNarrative
from app.graph.state import PAIntakeState, TraceEvent
from app.llm import get_chat_model
from app.prompts import render_prompt
from app.tools.code_reference import reference_codes_text
from app.tools.document_ingest import detect_file_kind, extract_pdf_text, extract_text_file
from app.tools.policy_kb import search_policy_criteria

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trace(node: str, summary: str) -> list[TraceEvent]:
    return [{"node": node, "timestamp": _now(), "summary": summary}]


# --------------------------------------------------------------------------
# 1. ingest
# --------------------------------------------------------------------------
async def ingest_node(state: PAIntakeState) -> dict:
    file_path = state["file_path"]
    kind = detect_file_kind(file_path)

    if kind == "pdf":
        raw_text = extract_pdf_text(file_path)
        note = "" if len(raw_text) >= 40 else " (suspiciously little text extracted)"
        return {
            "raw_text": raw_text,
            "trace": _trace("ingest", f"Detected PDF; extracted {len(raw_text)} chars of text{note}."),
        }

    raw_text = extract_text_file(file_path)
    return {
        "raw_text": raw_text,
        "trace": _trace("ingest", f"Detected plain-text chart excerpt; read {len(raw_text)} chars."),
    }


# --------------------------------------------------------------------------
# 2. extract_clinical_summary
# --------------------------------------------------------------------------
async def extract_clinical_summary_node(state: PAIntakeState) -> dict:
    llm = get_chat_model()
    structured_llm = llm.with_structured_output(ClinicalSummary)

    try:
        prompt_text = render_prompt("extract_clinical_summary", raw_text=state.get("raw_text", ""))
        result = await structured_llm.ainvoke(prompt_text)
        clinical_summary = result.model_dump()
    except Exception as exc:  # noqa: BLE001
        logger.exception("extract_clinical_summary_node: extraction failed")
        return {
            "clinical_summary": ClinicalSummary().model_dump(),
            "trace": _trace(
                "extract_clinical_summary",
                f"Extraction failed ({exc.__class__.__name__}); left clinical summary empty.",
            ),
        }

    return {
        "clinical_summary": clinical_summary,
        "trace": _trace(
            "extract_clinical_summary",
            f"Extracted requested service {clinical_summary.get('requested_service') or '(none stated)'!r} "
            f"for diagnosis {clinical_summary.get('diagnosis') or '(none stated)'!r}.",
        ),
    }


# --------------------------------------------------------------------------
# 3. match_policy_criteria
# --------------------------------------------------------------------------
async def match_policy_criteria_node(state: PAIntakeState) -> dict:
    clinical_summary = state.get("clinical_summary") or {}
    payer_name = state.get("payer_name", "")
    query = f"{clinical_summary.get('requested_service', '')} {clinical_summary.get('diagnosis', '')}".strip()

    chunks = search_policy_criteria(query, payer_name=payer_name) if query else []

    if not chunks:
        return {
            "criteria_checklist": [],
            "trace": _trace(
                "match_policy_criteria",
                f"No matching {payer_name!r} policy criteria found for this service; "
                "staff must evaluate the payer's published policy manually.",
            ),
        }

    criteria_text = "\n".join(f"{i + 1}. [{c.criterion_id}] {c.text}" for i, c in enumerate(chunks))

    llm = get_chat_model()
    structured_llm = llm.with_structured_output(CriteriaChecklist)
    try:
        prompt_text = render_prompt(
            "evaluate_policy_criteria",
            clinical_summary_json=json.dumps(clinical_summary),
            raw_text=state.get("raw_text", ""),
            criteria_text=criteria_text,
        )
        result = await structured_llm.ainvoke(prompt_text)
        checklist = [a.model_dump() for a in result.assessments]
    except Exception as exc:  # noqa: BLE001
        logger.exception("match_policy_criteria_node: evaluation failed")
        # Fall back to an "unclear" entry per retrieved criterion so staff
        # still sees which criteria apply, even though the LLM assessment
        # itself failed.
        checklist = [
            {
                "criterion_id": c.criterion_id,
                "criterion_text": c.text,
                "status": "unclear",
                "evidence": f"Automatic assessment failed ({exc.__class__.__name__}); please review manually.",
            }
            for c in chunks
        ]
        return {
            "criteria_checklist": checklist,
            "trace": _trace(
                "match_policy_criteria",
                f"Retrieved {len(chunks)} criteria but assessment failed ({exc.__class__.__name__}); "
                "marked unclear for staff review.",
            ),
        }

    met = sum(1 for a in checklist if a.get("status") == "met")
    return {
        "criteria_checklist": checklist,
        "trace": _trace(
            "match_policy_criteria",
            f"Draft assessment for staff review: {met}/{len(checklist)} of {payer_name}'s criteria "
            "appear met based on the chart excerpt (not a coverage decision).",
        ),
    }


# --------------------------------------------------------------------------
# 4. draft_pa_request
# --------------------------------------------------------------------------
async def draft_pa_request_node(state: PAIntakeState) -> dict:
    clinical_summary = state.get("clinical_summary") or {}
    criteria_checklist = state.get("criteria_checklist") or []

    llm = get_chat_model()
    structured_llm = llm.with_structured_output(DraftCodesAndNarrative)

    try:
        prompt_text = render_prompt(
            "draft_pa_request",
            clinical_summary_json=json.dumps(clinical_summary),
            criteria_checklist_json=json.dumps(criteria_checklist),
            reference_codes_text=reference_codes_text(),
        )
        result = await structured_llm.ainvoke(prompt_text)
        service_code = result.service_code
        diagnosis_code = result.diagnosis_code
        clinical_justification = result.clinical_justification
        trace_summary = "Drafted PA request form with LLM-assembled codes and clinical justification."
    except Exception as exc:  # noqa: BLE001
        logger.exception("draft_pa_request_node: drafting failed")
        service_code = ""
        diagnosis_code = ""
        clinical_justification = (
            "A clinical justification narrative could not be generated automatically for this "
            "request. Please draft the justification manually from the clinical summary and "
            "criteria checklist above before submission."
        )
        trace_summary = f"Drafting failed ({exc.__class__.__name__}); used fallback placeholder text."

    draft_form = {
        "patient_name": state.get("patient_name", ""),
        "patient_dob": state.get("patient_dob", ""),
        "patient_member_id": state.get("patient_member_id", ""),
        "payer_name": state.get("payer_name", ""),
        "provider_name": clinical_summary.get("referring_provider_name") or state.get("provider_name", ""),
        "provider_npi": state.get("provider_npi", ""),
        "requested_service": clinical_summary.get("requested_service", ""),
        "service_code": service_code,
        "diagnosis": clinical_summary.get("diagnosis", ""),
        "diagnosis_code": diagnosis_code,
        "clinical_justification": clinical_justification,
    }

    return {"draft_form": draft_form, "trace": _trace("draft_pa_request", trace_summary)}


# --------------------------------------------------------------------------
# 5. staff_review
# --------------------------------------------------------------------------
async def staff_review_node(state: PAIntakeState) -> dict:
    """Pause the graph and wait for a staff member's decision.

    `interrupt()` raises a `GraphInterrupt` the first time this node runs
    for a given thread; LangGraph's Postgres checkpointer persists state up
    to (but not including) this node's completion, so the process can exit
    entirely and be resumed later via `Command(resume=...)` against the
    same `thread_id` -- see `app/api/routers/pa_requests.py::resume_pa_request`.

    This is the mandatory safety gate for the whole application: nothing
    produced by `extract_clinical_summary`/`match_policy_criteria`/
    `draft_pa_request` is ready to submit to a payer until a licensed staff
    member/clinician explicitly approves, corrects, or rejects it here. A PA
    request's real-world lifecycle spans days to weeks and a staff member
    typically works through a review queue asynchronously -- not
    necessarily right after a chart is uploaded -- which is exactly why this
    graph needs a durable, Postgres-backed checkpointer rather than
    in-process state: the interrupt must survive a server restart just as
    easily as it survives staff simply closing their browser tab.
    """
    payload = interrupt(
        {
            "original_filename": state.get("original_filename"),
            "clinical_summary": state.get("clinical_summary", {}),
            "criteria_checklist": state.get("criteria_checklist", []),
            "draft_form": state.get("draft_form", {}),
        }
    )
    decision = str(payload.get("decision", "approve")).lower()
    feedback = str(payload.get("feedback", ""))
    corrected_draft_form = payload.get("corrected_draft_form")
    corrected_criteria_checklist = payload.get("corrected_criteria_checklist")
    if decision not in {"approve", "correct", "reject"}:
        decision = "approve"

    update: dict = {
        "human_decision": decision,
        "human_feedback": feedback,
        "trace": _trace("staff_review", f"Staff decision={decision} | {feedback[:200]}"),
    }

    if decision == "correct":
        if corrected_draft_form:
            update["draft_form"] = corrected_draft_form
            update["corrected_draft_form"] = corrected_draft_form
        if corrected_criteria_checklist is not None:
            update["criteria_checklist"] = corrected_criteria_checklist
            update["corrected_criteria_checklist"] = corrected_criteria_checklist

    return update


# --------------------------------------------------------------------------
# 6. finalize
# --------------------------------------------------------------------------
async def finalize_node(state: PAIntakeState) -> dict:
    decision = state.get("human_decision", "approve")

    if decision == "reject":
        final_status, status = "rejected", "rejected"
        summary = "PA request draft rejected by staff; not queued for submission."
    else:
        final_status = "corrected_and_ready" if decision == "correct" else "ready_to_submit"
        status = "ready_to_submit"
        summary = (
            f"PA request draft finalized with status={final_status}. Ready for staff to submit to the "
            "payer -- this status change is drafting-only and does not submit anything automatically."
        )

    return {"final_status": final_status, "status": status, "trace": _trace("finalize", summary)}
