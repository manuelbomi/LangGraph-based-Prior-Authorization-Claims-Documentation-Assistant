"""Pydantic request/response schemas for the REST + SSE API.

Keep these in sync with `frontend/src/api/types.ts` -- that file is a
hand-written TypeScript mirror of this one.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

PARequestStatus = Literal[
    "pending",
    "running",
    "awaiting_staff_review",
    "ready_to_submit",
    "submitted",
    "approved",
    "denied",
    "more_info_requested",
    "rejected",
    "error",
]

# Statuses settable via POST /pa-requests/{id}/status -- a plain field
# update modeling real-world tracking, NOT a graph re-entry. See the root
# README's "Scope & Safety" section and app/db/models.py::PARequest.
TrackablePAStatus = Literal["submitted", "approved", "denied", "more_info_requested"]


class PatientSummary(BaseModel):
    id: str
    name: str
    member_id: str
    date_of_birth: str
    primary_payer: str


class PatientDetail(PatientSummary):
    provider_name: str
    provider_npi: str
    notes: str
    pa_requests: list["PARequestSummary"]


class PatientListResponse(BaseModel):
    patients: list[PatientSummary]


class PayersResponse(BaseModel):
    payers: list[str]


class SampleDocument(BaseModel):
    id: str
    label: str
    suggested_patient_id: str | None = None
    suggested_payer: str | None = None


class SamplesResponse(BaseModel):
    samples: list[SampleDocument]


class PARequestCreateResponse(BaseModel):
    id: str
    patient_id: str
    payer_name: str
    status: PARequestStatus
    original_filename: str


class HumanDecisionRequest(BaseModel):
    decision: Literal["approve", "correct", "reject"]
    feedback: str = ""
    corrected_draft_form: dict[str, Any] | None = None
    corrected_criteria_checklist: list[dict[str, Any]] | None = None


class StatusUpdateRequest(BaseModel):
    status: TrackablePAStatus
    note: str = ""


class TraceEventOut(BaseModel):
    node: str
    timestamp: datetime
    summary: str


class StatusHistoryEntryOut(BaseModel):
    status: str
    timestamp: datetime
    note: str = ""


class PARequestSummary(BaseModel):
    id: str
    patient_id: str
    payer_name: str
    original_filename: str
    status: PARequestStatus
    final_status: str | None
    created_at: datetime
    updated_at: datetime


class PARequestDetail(PARequestSummary):
    clinical_summary: dict[str, Any]
    criteria_checklist: list[dict[str, Any]]
    draft_form: dict[str, Any]
    trace: list[TraceEventOut]
    state_snapshot: dict[str, Any]
    status_history: list[StatusHistoryEntryOut]
    error: str | None


class PARequestListResponse(BaseModel):
    pa_requests: list[PARequestSummary]


PatientDetail.model_rebuild()
