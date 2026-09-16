"""End-to-end graph flow tests using LangGraph's in-memory checkpointer.

This proves the interrupt/resume *mechanics* (the same API the FastAPI app
uses against Postgres in `app/db/checkpointer.py`) without needing a real
database or LLM. The equivalent test against a *real* Postgres checkpointer
and a *real* OpenAI key lives in `tests/live/test_live_smoke.py`.
"""
from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.graph.graph import build_graph
from app.graph.pa_schema import ClinicalSummary, CriteriaChecklist, CriterionAssessment, DraftCodesAndNarrative
from app.tools.policy_kb import PolicyCriterionResult

_GRAPH_INPUT = {
    "file_path": "referral.txt",
    "original_filename": "referral.txt",
    "patient_id": "jordan-blake",
    "patient_name": "Jordan Blake",
    "patient_dob": "1979-03-14",
    "patient_member_id": "MHP-5521309",
    "payer_name": "Meridian Health Plan",
    "provider_name": "Dr. Alicia Munoz, MD",
    "provider_npi": "1447920033",
}


def _one_criterion_result() -> PolicyCriterionResult:
    return PolicyCriterionResult(
        criterion_id="meridian-health-plan-a",
        payer_name="Meridian Health Plan",
        service="Lumbar Spine MRI",
        policy_title="Medical Necessity Criteria for Lumbar Spine MRI",
        criterion_label="a",
        text="Low back pain symptoms have been present for greater than 6 weeks.",
        score=0.9,
    )


async def test_request_pauses_at_staff_review_and_resumes_to_completion(
    fake_chat_model, fake_prompts, no_policy_io, monkeypatch
):
    monkeypatch.setattr("app.graph.nodes.detect_file_kind", lambda p: "text")
    monkeypatch.setattr("app.graph.nodes.extract_text_file", lambda p: "10 weeks of low back pain")
    no_policy_io.default_results = [_one_criterion_result()]

    fake_chat_model(
        [
            ClinicalSummary(
                diagnosis="Chronic low back pain with radiculopathy",
                requested_service="Lumbar spine MRI",
                duration_of_symptoms="10 weeks",
            ),
            CriteriaChecklist(
                assessments=[
                    CriterionAssessment(
                        criterion_id="meridian-health-plan-a",
                        criterion_text="Low back pain symptoms have been present for greater than 6 weeks.",
                        status="met",
                        evidence="10 weeks of symptoms documented.",
                    )
                ]
            ),
            DraftCodesAndNarrative(
                service_code="72148", diagnosis_code="M54.16", clinical_justification="Draft justification."
            ),
        ]
    )

    graph = build_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "test-thread-lumbar-mri"}}

    result = None
    async for event in graph.astream(_GRAPH_INPUT, config=config, stream_mode="updates"):
        result = event

    assert result is not None
    assert "__interrupt__" in result, "graph should pause at staff_review"
    interrupt_payload = result["__interrupt__"][0].value
    assert interrupt_payload["clinical_summary"]["requested_service"] == "Lumbar spine MRI"
    assert interrupt_payload["criteria_checklist"][0]["status"] == "met"
    assert interrupt_payload["draft_form"]["service_code"] == "72148"

    state_before_resume = await graph.aget_state(config)
    assert state_before_resume.next == ("staff_review",)

    final_event = None
    async for event in graph.astream(
        Command(resume={"decision": "approve", "feedback": "Looks correct."}),
        config=config,
        stream_mode="updates",
    ):
        final_event = event

    assert "finalize" in final_event
    final_state = await graph.aget_state(config)
    assert final_state.next == ()  # graph reached END
    assert final_state.values["status"] == "ready_to_submit"
    assert final_state.values["final_status"] == "ready_to_submit"


async def test_correct_decision_replaces_draft_form(fake_chat_model, fake_prompts, no_policy_io, monkeypatch):
    monkeypatch.setattr("app.graph.nodes.detect_file_kind", lambda p: "text")
    monkeypatch.setattr("app.graph.nodes.extract_text_file", lambda p: "chart text")
    no_policy_io.default_results = []

    fake_chat_model(
        [
            ClinicalSummary(diagnosis="Psoriatic arthritis", requested_service="Adalimumab"),
            DraftCodesAndNarrative(
                service_code="J0135", diagnosis_code="L40.50", clinical_justification="Initial justification."
            ),
        ]
    )

    graph = build_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "test-thread-correct"}}

    async for _ in graph.astream(_GRAPH_INPUT, config=config, stream_mode="updates"):
        pass

    corrected_form = {
        "patient_name": "Jordan Blake",
        "patient_dob": "1979-03-14",
        "patient_member_id": "MHP-5521309",
        "payer_name": "Meridian Health Plan",
        "provider_name": "Dr. Alicia Munoz, MD",
        "provider_npi": "1447920033",
        "requested_service": "Adalimumab",
        "service_code": "J0135",
        "diagnosis": "Psoriatic arthritis",
        "diagnosis_code": "L40.50",
        "clinical_justification": "Corrected justification with staff edits.",
    }
    async for _ in graph.astream(
        Command(
            resume={
                "decision": "correct",
                "feedback": "Clarified justification wording.",
                "corrected_draft_form": corrected_form,
            }
        ),
        config=config,
        stream_mode="updates",
    ):
        pass

    final_state = await graph.aget_state(config)
    assert final_state.values["draft_form"]["clinical_justification"] == "Corrected justification with staff edits."
    assert final_state.values["final_status"] == "corrected_and_ready"


async def test_reject_decision_does_not_mark_ready(fake_chat_model, fake_prompts, no_policy_io, monkeypatch):
    monkeypatch.setattr("app.graph.nodes.detect_file_kind", lambda p: "text")
    monkeypatch.setattr("app.graph.nodes.extract_text_file", lambda p: "note text")
    no_policy_io.default_results = []

    fake_chat_model(
        [
            ClinicalSummary(diagnosis="Acute low back pain", requested_service="Lumbar spine MRI"),
            DraftCodesAndNarrative(service_code="", diagnosis_code="", clinical_justification="Draft."),
        ]
    )

    graph = build_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "test-thread-reject"}}

    async for _ in graph.astream(_GRAPH_INPUT, config=config, stream_mode="updates"):
        pass

    async for _ in graph.astream(
        Command(resume={"decision": "reject", "feedback": "Criteria not yet met."}),
        config=config,
        stream_mode="updates",
    ):
        pass

    final_state = await graph.aget_state(config)
    assert final_state.values["final_status"] == "rejected"
    assert final_state.values["status"] == "rejected"
