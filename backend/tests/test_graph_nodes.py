"""Unit tests for individual graph nodes.

Everything here is mocked: LLM calls go through `FakeChatModel` (see
conftest.py), and policy-criteria search I/O is monkeypatched via the
`no_policy_io` fixture. No network, no Postgres, no Milvus, no API key
spend.
"""
from __future__ import annotations

from app.graph import nodes
from app.graph.pa_schema import ClinicalSummary, CriteriaChecklist, CriterionAssessment, DraftCodesAndNarrative
from app.tools.policy_kb import PolicyCriterionResult


# ---------------------------------------------------------------------
# ingest_node
# ---------------------------------------------------------------------
async def test_ingest_node_text(monkeypatch):
    monkeypatch.setattr(nodes, "detect_file_kind", lambda p: "text")
    monkeypatch.setattr(nodes, "extract_text_file", lambda p: "Chief complaint: low back pain.")

    result = await nodes.ingest_node({"file_path": "note.txt"})

    assert result["raw_text"] == "Chief complaint: low back pain."
    assert len(result["trace"]) == 1


async def test_ingest_node_pdf(monkeypatch):
    monkeypatch.setattr(nodes, "detect_file_kind", lambda p: "pdf")
    monkeypatch.setattr(nodes, "extract_pdf_text", lambda p: "REFERRAL NOTE " * 5)

    result = await nodes.ingest_node({"file_path": "note.pdf"})

    assert "raw_text" in result
    assert len(result["trace"]) == 1


# ---------------------------------------------------------------------
# extract_clinical_summary_node
# ---------------------------------------------------------------------
async def test_extract_clinical_summary_node_success(fake_chat_model, fake_prompts):
    summary = ClinicalSummary(
        diagnosis="Chronic low back pain with radiculopathy",
        requested_service="Lumbar spine MRI",
        duration_of_symptoms="10 weeks",
        prior_treatments_tried=["Physical therapy", "NSAIDs"],
    )
    fake_chat_model([summary])

    result = await nodes.extract_clinical_summary_node({"raw_text": "some chart text"})

    assert result["clinical_summary"]["diagnosis"] == "Chronic low back pain with radiculopathy"
    assert result["clinical_summary"]["requested_service"] == "Lumbar spine MRI"
    assert result["trace"][0]["node"] == "extract_clinical_summary"


async def test_extract_clinical_summary_node_handles_failure(fake_chat_model, fake_prompts):
    fake_chat_model([RuntimeError("model refused")])

    result = await nodes.extract_clinical_summary_node({"raw_text": "garbled"})

    assert result["clinical_summary"] == ClinicalSummary().model_dump()
    assert "failed" in result["trace"][0]["summary"].lower()


# ---------------------------------------------------------------------
# match_policy_criteria_node
# ---------------------------------------------------------------------
async def test_match_policy_criteria_node_builds_checklist(fake_chat_model, fake_prompts, no_policy_io):
    no_policy_io.default_results = [
        PolicyCriterionResult(
            criterion_id="meridian-health-plan-a",
            payer_name="Meridian Health Plan",
            service="Lumbar Spine MRI",
            policy_title="Medical Necessity Criteria for Lumbar Spine MRI",
            criterion_label="a",
            text="Low back pain symptoms have been present for greater than 6 weeks.",
            score=0.9,
        )
    ]
    checklist = CriteriaChecklist(
        assessments=[
            CriterionAssessment(
                criterion_id="meridian-health-plan-a",
                criterion_text="Low back pain symptoms have been present for greater than 6 weeks.",
                status="met",
                evidence="Pain began 10 weeks ago.",
            )
        ]
    )
    fake_chat_model([checklist])

    result = await nodes.match_policy_criteria_node(
        {
            "clinical_summary": {"requested_service": "Lumbar spine MRI", "diagnosis": "low back pain"},
            "payer_name": "Meridian Health Plan",
            "raw_text": "chart text",
        }
    )

    assert len(result["criteria_checklist"]) == 1
    assert result["criteria_checklist"][0]["status"] == "met"
    assert no_policy_io.calls == [("Lumbar spine MRI low back pain", "Meridian Health Plan")]


async def test_match_policy_criteria_node_no_matches(no_policy_io):
    no_policy_io.default_results = []

    result = await nodes.match_policy_criteria_node(
        {
            "clinical_summary": {"requested_service": "Unmapped service", "diagnosis": "unknown"},
            "payer_name": "Meridian Health Plan",
            "raw_text": "chart text",
        }
    )

    assert result["criteria_checklist"] == []
    assert "no matching" in result["trace"][0]["summary"].lower()


async def test_match_policy_criteria_node_handles_llm_failure(fake_chat_model, fake_prompts, no_policy_io):
    no_policy_io.default_results = [
        PolicyCriterionResult(
            criterion_id="c-a",
            payer_name="Meridian Health Plan",
            service="Lumbar Spine MRI",
            policy_title="Policy",
            criterion_label="a",
            text="Symptoms present > 6 weeks.",
            score=0.9,
        )
    ]
    fake_chat_model([RuntimeError("model refused")])

    result = await nodes.match_policy_criteria_node(
        {
            "clinical_summary": {"requested_service": "Lumbar spine MRI", "diagnosis": "low back pain"},
            "payer_name": "Meridian Health Plan",
            "raw_text": "chart text",
        }
    )

    assert len(result["criteria_checklist"]) == 1
    assert result["criteria_checklist"][0]["status"] == "unclear"


# ---------------------------------------------------------------------
# draft_pa_request_node
# ---------------------------------------------------------------------
async def test_draft_pa_request_node_success(fake_chat_model, fake_prompts):
    fake_chat_model(
        [
            DraftCodesAndNarrative(
                service_code="72148",
                diagnosis_code="M54.16",
                clinical_justification="Draft justification referencing met criteria.",
            )
        ]
    )

    result = await nodes.draft_pa_request_node(
        {
            "clinical_summary": {"requested_service": "Lumbar spine MRI", "diagnosis": "radiculopathy"},
            "criteria_checklist": [],
            "patient_name": "Jordan Blake",
            "patient_dob": "1979-03-14",
            "patient_member_id": "MHP-5521309",
            "payer_name": "Meridian Health Plan",
            "provider_name": "Dr. Alicia Munoz, MD",
            "provider_npi": "1447920033",
        }
    )

    draft = result["draft_form"]
    assert draft["patient_name"] == "Jordan Blake"
    assert draft["service_code"] == "72148"
    assert draft["requested_service"] == "Lumbar spine MRI"
    assert "Draft justification" in draft["clinical_justification"]


async def test_draft_pa_request_node_handles_failure(fake_chat_model, fake_prompts):
    fake_chat_model([RuntimeError("model refused")])

    result = await nodes.draft_pa_request_node(
        {
            "clinical_summary": {"requested_service": "Lumbar spine MRI", "diagnosis": "radiculopathy"},
            "criteria_checklist": [],
            "patient_name": "Jordan Blake",
            "payer_name": "Meridian Health Plan",
        }
    )

    draft = result["draft_form"]
    assert draft["service_code"] == ""
    assert "could not be generated" in draft["clinical_justification"]
    assert "failed" in result["trace"][0]["summary"].lower()


# ---------------------------------------------------------------------
# finalize_node
# ---------------------------------------------------------------------
async def test_finalize_node_approved():
    result = await nodes.finalize_node({"human_decision": "approve"})
    assert result["final_status"] == "ready_to_submit"
    assert result["status"] == "ready_to_submit"


async def test_finalize_node_corrected():
    result = await nodes.finalize_node({"human_decision": "correct"})
    assert result["final_status"] == "corrected_and_ready"
    assert result["status"] == "ready_to_submit"


async def test_finalize_node_rejected():
    result = await nodes.finalize_node({"human_decision": "reject"})
    assert result["final_status"] == "rejected"
    assert result["status"] == "rejected"
