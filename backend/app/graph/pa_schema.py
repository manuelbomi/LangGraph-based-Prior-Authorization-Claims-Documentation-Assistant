"""Pydantic schemas used for LLM structured-output calls in the
prior-authorization drafting graph (`app/graph/nodes.py`).

Every schema here is deliberately narrow, mirroring the same design
principle used across this tutorial series: a field can only ever hold
information that was already present in the chart excerpt (or, for
`DraftCodesAndNarrative`, a code chosen from a small fixed reference list --
never invented). There is no "coverage_decision" or "medical_advice" field
anywhere -- see the root README's "Scope & Safety" section and the seeded
prompt text in `app/prompts/seed_prompts.py`.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ClinicalSummary(BaseModel):
    diagnosis: str = Field(default="", description="Primary diagnosis/clinical impression, as stated in the chart.")
    requested_service: str = Field(
        default="", description="The specific service, procedure, or medication being requested."
    )
    duration_of_symptoms: str = Field(default="", description="How long symptoms have been present, as stated.")
    prior_treatments_tried: list[str] = Field(
        default_factory=list, description="Prior treatments already tried, each as the clinician described it."
    )
    exam_findings: list[str] = Field(default_factory=list, description="Relevant physical exam/imaging findings.")
    relevant_history: list[str] = Field(
        default_factory=list, description="Other relevant history (prior imaging, screening, comorbidities)."
    )
    referring_provider_name: str = Field(default="", description="Referring provider's name, if stated.")


class CriterionAssessment(BaseModel):
    criterion_id: str = Field(description="The id of the criterion being assessed, copied from the input list.")
    criterion_text: str = Field(description="The criterion text being assessed, copied from the input list.")
    status: Literal["met", "unmet", "unclear"] = Field(
        description="Whether the chart excerpt shows this criterion is met, unmet, or unclear."
    )
    evidence: str = Field(
        description=(
            "A quote or close paraphrase from the chart excerpt supporting this assessment, "
            "or a note on what information is missing if unclear."
        )
    )


class CriteriaChecklist(BaseModel):
    assessments: list[CriterionAssessment] = Field(default_factory=list)


class DraftCodesAndNarrative(BaseModel):
    service_code: str = Field(
        default="", description="Best-matching procedure/drug code from the provided reference list, or empty."
    )
    diagnosis_code: str = Field(
        default="", description="Best-matching diagnosis code from the provided reference list, or empty."
    )
    clinical_justification: str = Field(
        default="",
        description=(
            "Objective narrative summarizing symptom duration, prior treatments, exam findings, and which "
            "criteria appear met/unmet/unclear, ending with a draft-for-staff-review disclaimer."
        ),
    )
