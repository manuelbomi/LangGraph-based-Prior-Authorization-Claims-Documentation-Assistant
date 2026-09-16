"""Graph state schema.

A `TypedDict` (LangGraph's preferred state shape) rather than a Pydantic
model, so partial node returns (`{"clinical_summary": {...}}`) merge
cleanly via LangGraph's default "last write wins per key" reducer. Only
`trace` accumulates (via an `operator.add` reducer) since every other field
is written exactly once per run (this graph is a straight line -- there are
no revision loops; a staff member's correction is applied inline in
`staff_review_node`, not by looping back).

Patient/provider/payer identifying fields (`patient_name`, `patient_dob`,
`patient_member_id`, `payer_name`, `provider_name`, `provider_npi`) are
passed in as plain input state by the API layer (which looks them up from
Postgres before starting the graph) rather than being extracted by an LLM
from the chart -- this keeps every identifying field on the drafted form
sourced from a trusted record, never hallucinated by a model.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class TraceEvent(TypedDict):
    node: str
    timestamp: str
    summary: str


class PAIntakeState(TypedDict, total=False):
    # --- input ---
    file_path: str
    original_filename: str
    patient_id: str
    patient_name: str
    patient_dob: str
    patient_member_id: str
    payer_name: str
    provider_name: str
    provider_npi: str

    # --- ingest ---
    raw_text: str

    # --- extract_clinical_summary ---
    clinical_summary: dict[str, Any]  # dumped ClinicalSummary

    # --- match_policy_criteria ---
    criteria_checklist: list[dict[str, Any]]  # dumped CriterionAssessment list

    # --- draft_pa_request ---
    draft_form: dict[str, Any]

    # --- staff_review (human-in-the-loop, the mandatory safety gate) ---
    human_decision: str  # "approve" | "correct" | "reject" | ""
    human_feedback: str
    corrected_draft_form: dict[str, Any]
    corrected_criteria_checklist: list[dict[str, Any]]

    # --- finalize ---
    final_status: str  # "ready_to_submit" | "corrected_and_ready" | "rejected"
    status: str  # mirrors app.db.models.PARequest.status

    # --- observability (appended to, not replaced) ---
    trace: Annotated[list[TraceEvent], operator.add]
