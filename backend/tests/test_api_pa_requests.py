"""API contract tests for the /patients and /pa-requests endpoints.

Uses a lightweight in-memory fake in place of the Postgres-backed
`SessionLocal`, and an `InMemorySaver` in place of the Postgres checkpointer,
so these run without any real database. LLM + policy-criteria lookup calls
are mocked exactly as in `test_graph_nodes.py` / `test_graph_flow.py`.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from langgraph.checkpoint.memory import InMemorySaver

from app.api.routers.pa_requests import router as pa_requests_router
from app.api.routers.patients import router as patients_router
from app.config import Settings
from app.db.models import PARequest, Patient
from app.graph.graph import build_graph
from app.graph.pa_schema import ClinicalSummary, DraftCodesAndNarrative


class _FakeResultSet:
    def __init__(self, rows: list):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, patients: dict, pa_requests: dict):
        self._patients = patients
        self._pa_requests = pa_requests

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def add(self, obj) -> None:
        if isinstance(obj, Patient):
            self._patients[obj.id] = obj
        elif isinstance(obj, PARequest):
            self._pa_requests[obj.id] = obj

    def commit(self) -> None:
        pass

    def refresh(self, obj) -> None:
        pass

    def get(self, model, id_):
        if model is Patient:
            return self._patients.get(id_)
        if model is PARequest:
            return self._pa_requests.get(id_)
        return None

    def execute(self, stmt):
        entity = stmt.column_descriptions[0]["entity"]
        if entity is Patient:
            rows = sorted(self._patients.values(), key=lambda p: p.name)
        else:
            rows = sorted(self._pa_requests.values(), key=lambda r: r.created_at, reverse=True)
        return _FakeResultSet(rows)


def _seed_patient(patients: dict, patient_id="jordan-blake") -> Patient:
    patient = Patient(
        id=patient_id,
        name="Jordan Blake",
        member_id="MHP-5521309",
        date_of_birth="1979-03-14",
        primary_payer="Meridian Health Plan",
        provider_name="Dr. Alicia Munoz, MD",
        provider_npi="1447920033",
        notes="",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    patients[patient_id] = patient
    return patient


@pytest.fixture
def api_app(monkeypatch, fake_chat_model, fake_prompts, no_policy_io, tmp_path):
    patients: dict[str, Patient] = {}
    pa_requests: dict[str, PARequest] = {}
    _seed_patient(patients)

    monkeypatch.setattr("app.api.routers.patients.SessionLocal", lambda: _FakeSession(patients, pa_requests))
    monkeypatch.setattr("app.api.routers.pa_requests.SessionLocal", lambda: _FakeSession(patients, pa_requests))

    fake_settings = Settings(
        upload_dir=str(tmp_path / "uploads"), sample_data_dir=str(tmp_path / "sample-data")
    )
    monkeypatch.setattr("app.api.routers.pa_requests.get_settings", lambda: fake_settings)

    monkeypatch.setattr("app.graph.nodes.extract_text_file", lambda p: "10 weeks of low back pain")
    monkeypatch.setattr("app.graph.nodes.extract_pdf_text", lambda p: "10 weeks of low back pain")

    app = FastAPI()
    app.state.run_queues = {}
    app.state.run_tasks = {}
    app.state.graph = build_graph(checkpointer=InMemorySaver())
    app.include_router(patients_router)
    app.include_router(pa_requests_router)
    return app, patients, pa_requests


async def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _extraction_and_draft_responses() -> list:
    return [
        ClinicalSummary(
            diagnosis="Chronic low back pain with radiculopathy",
            requested_service="Lumbar spine MRI",
            duration_of_symptoms="10 weeks",
        ),
        DraftCodesAndNarrative(
            service_code="72148", diagnosis_code="M54.16", clinical_justification="Draft justification."
        ),
    ]


async def test_list_patients_returns_seeded_patient(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.get("/patients")
        assert resp.status_code == 200
        ids = {p["id"] for p in resp.json()["patients"]}
        assert "jordan-blake" in ids


async def test_get_patient_detail(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.get("/patients/jordan-blake")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Jordan Blake"


async def test_get_unknown_patient_404(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.get("/patients/does-not-exist")
        assert resp.status_code == 404


async def test_list_payers(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.get("/pa-requests/payers")
        assert resp.status_code == 200
        assert "Meridian Health Plan" in resp.json()["payers"]


async def test_list_samples_returns_catalog(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.get("/pa-requests/samples")
        assert resp.status_code == 200
        ids = {s["id"] for s in resp.json()["samples"]}
        assert "lumbar-mri-jordan-blake" in ids


async def test_upload_referral_reaches_staff_review(api_app, fake_chat_model):
    app, _, _ = api_app
    fake_chat_model(_extraction_and_draft_responses())

    async with await _client(app) as client:
        resp = await client.post(
            "/pa-requests/upload",
            data={"patient_id": "jordan-blake", "payer_name": "Meridian Health Plan"},
            files={"file": ("referral.txt", b"Chief complaint: low back pain.", "text/plain")},
        )
        assert resp.status_code == 200
        req_id = resp.json()["id"]

        await app.state.run_tasks[req_id]

        detail = await client.get(f"/pa-requests/{req_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["status"] == "awaiting_staff_review"
        assert body["clinical_summary"]["requested_service"] == "Lumbar spine MRI"
        assert len(body["trace"]) >= 3


async def test_upload_unknown_patient_404(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.post(
            "/pa-requests/upload",
            data={"patient_id": "does-not-exist", "payer_name": "Meridian Health Plan"},
            files={"file": ("referral.txt", b"hello", "text/plain")},
        )
        assert resp.status_code == 404


async def test_upload_unknown_payer_400(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.post(
            "/pa-requests/upload",
            data={"patient_id": "jordan-blake", "payer_name": "Not A Real Payer"},
            files={"file": ("referral.txt", b"hello", "text/plain")},
        )
        assert resp.status_code == 400


async def test_upload_rejects_unsupported_extension(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.post(
            "/pa-requests/upload",
            data={"patient_id": "jordan-blake", "payer_name": "Meridian Health Plan"},
            files={"file": ("referral.docx", b"hello", "application/octet-stream")},
        )
        assert resp.status_code == 400


async def test_run_sample_referral(api_app, fake_chat_model, tmp_path):
    app, _, _ = api_app
    fake_chat_model(_extraction_and_draft_responses())

    sample_dir = tmp_path / "sample-data" / "referrals"
    sample_dir.mkdir(parents=True)
    (sample_dir / "lumbar_mri_referral_jordan_blake.txt").write_text("Chief complaint: low back pain.")

    async with await _client(app) as client:
        resp = await client.post(
            "/pa-requests/samples/lumbar-mri-jordan-blake/run",
            data={"patient_id": "jordan-blake", "payer_name": "Meridian Health Plan"},
        )
        assert resp.status_code == 200
        req_id = resp.json()["id"]

        await app.state.run_tasks[req_id]

        detail = await client.get(f"/pa-requests/{req_id}")
        assert detail.json()["clinical_summary"]["requested_service"] == "Lumbar spine MRI"


async def test_run_unknown_sample_404(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.post(
            "/pa-requests/samples/does-not-exist/run",
            data={"patient_id": "jordan-blake", "payer_name": "Meridian Health Plan"},
        )
        assert resp.status_code == 404


async def test_resume_pa_request_completes(api_app, fake_chat_model):
    app, _, _ = api_app
    fake_chat_model(_extraction_and_draft_responses())

    async with await _client(app) as client:
        resp = await client.post(
            "/pa-requests/upload",
            data={"patient_id": "jordan-blake", "payer_name": "Meridian Health Plan"},
            files={"file": ("referral.txt", b"Chief complaint: low back pain.", "text/plain")},
        )
        req_id = resp.json()["id"]
        await app.state.run_tasks[req_id]

        resume_resp = await client.post(
            f"/pa-requests/{req_id}/resume", json={"decision": "approve", "feedback": "Looks good."}
        )
        assert resume_resp.status_code == 200
        await app.state.run_tasks[req_id]

        detail = await client.get(f"/pa-requests/{req_id}")
        body = detail.json()
        assert body["status"] == "ready_to_submit"
        assert body["final_status"] == "ready_to_submit"


async def test_resume_rejects_when_not_found(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.post(
            "/pa-requests/does-not-exist/resume", json={"decision": "approve", "feedback": ""}
        )
        assert resp.status_code == 404


async def test_list_pa_requests_returns_summaries(api_app):
    app, _, pa_requests = api_app
    now = datetime.now(timezone.utc)
    pa_requests["r1"] = PARequest(
        id="r1", patient_id="jordan-blake", payer_name="Meridian Health Plan", original_filename="a.txt",
        status="ready_to_submit", final_status="ready_to_submit", clinical_summary={}, criteria_checklist=[],
        draft_form={}, trace=[], state_snapshot={}, status_history=[], created_at=now, updated_at=now,
    )
    pa_requests["r2"] = PARequest(
        id="r2", patient_id="jordan-blake", payer_name="Meridian Health Plan", original_filename="b.txt",
        status="awaiting_staff_review", final_status=None, clinical_summary={}, criteria_checklist=[],
        draft_form={}, trace=[], state_snapshot={}, status_history=[], created_at=now, updated_at=now,
    )

    async with await _client(app) as client:
        resp = await client.get("/pa-requests")
        assert resp.status_code == 200
        ids = {r["id"] for r in resp.json()["pa_requests"]}
        assert ids == {"r1", "r2"}


async def test_get_unknown_pa_request_404(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.get("/pa-requests/nope")
        assert resp.status_code == 404


async def test_update_status_ready_to_submit_to_submitted(api_app):
    app, _, pa_requests = api_app
    now = datetime.now(timezone.utc)
    pa_requests["r1"] = PARequest(
        id="r1", patient_id="jordan-blake", payer_name="Meridian Health Plan", original_filename="a.txt",
        status="ready_to_submit", final_status="ready_to_submit", clinical_summary={}, criteria_checklist=[],
        draft_form={}, trace=[], state_snapshot={}, status_history=[], created_at=now, updated_at=now,
    )

    async with await _client(app) as client:
        resp = await client.post("/pa-requests/r1/status", json={"status": "submitted", "note": "Submitted via portal."})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "submitted"
        assert len(body["status_history"]) == 1
        assert body["status_history"][0]["status"] == "submitted"


async def test_update_status_rejects_invalid_transition(api_app):
    app, _, pa_requests = api_app
    now = datetime.now(timezone.utc)
    pa_requests["r1"] = PARequest(
        id="r1", patient_id="jordan-blake", payer_name="Meridian Health Plan", original_filename="a.txt",
        status="ready_to_submit", final_status="ready_to_submit", clinical_summary={}, criteria_checklist=[],
        draft_form={}, trace=[], state_snapshot={}, status_history=[], created_at=now, updated_at=now,
    )

    async with await _client(app) as client:
        resp = await client.post("/pa-requests/r1/status", json={"status": "approved"})
        assert resp.status_code == 409


async def test_update_status_unknown_request_404(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.post("/pa-requests/nope/status", json={"status": "submitted"})
        assert resp.status_code == 404
