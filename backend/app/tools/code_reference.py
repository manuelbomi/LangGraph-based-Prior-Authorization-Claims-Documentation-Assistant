"""A small, fixed, hand-curated reference table of procedure/drug codes
(CPT/HCPCS) and diagnosis codes (ICD-10-CM) relevant to the sample-data
scenarios in this demo.

This is deliberately NOT a complete or authoritative code set (it covers
only the handful of services/diagnoses the bundled sample referrals and
payer policies mention) and is NOT sourced from any real payer. It exists
so `draft_pa_request_node` can ask the LLM to choose the closest-matching
code from a small, fixed, non-hallucinatable list rather than generating a
plausible-looking-but-invented code from scratch -- mirroring the "suggest
from a curated reference set, for staff confirmation" pattern used for
ICD-10 lookup in `langgraph-tutorial-04-clinical-documentation-assistant`,
just via a lightweight lookup table here instead of a second vector
collection (Milvus Lite in this repo is reserved for the higher-value
semantic task: matching a request against a payer's medical-necessity
criteria -- see `app/tools/policy_kb.py`).

Codes are real, publicly-published CPT/HCPCS/ICD-10-CM style codes used
purely as realistic examples, the same way public code sets are commonly
referenced in software documentation and tutorials.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ReferenceCode:
    service_description: str
    service_code: str
    service_code_type: str  # "CPT" | "HCPCS"
    diagnosis_description: str
    diagnosis_code: str


REFERENCE_CODES: list[ReferenceCode] = [
    ReferenceCode(
        service_description="Lumbar spine MRI without contrast",
        service_code="72148",
        service_code_type="CPT",
        diagnosis_description="Lumbar radiculopathy",
        diagnosis_code="M54.16",
    ),
    ReferenceCode(
        service_description="Lumbar spine MRI without contrast",
        service_code="72148",
        service_code_type="CPT",
        diagnosis_description="Low back pain, unspecified",
        diagnosis_code="M54.50",
    ),
    ReferenceCode(
        service_description="Adalimumab (Humira) injection, 20 mg",
        service_code="J0135",
        service_code_type="HCPCS",
        diagnosis_description="Psoriatic arthropathy, unspecified",
        diagnosis_code="L40.50",
    ),
    ReferenceCode(
        service_description="Therapeutic exercise, physical therapy",
        service_code="97110",
        service_code_type="CPT",
        diagnosis_description="Pain in right knee",
        diagnosis_code="M25.561",
    ),
    ReferenceCode(
        service_description="Neuromuscular reeducation, physical therapy",
        service_code="97112",
        service_code_type="CPT",
        diagnosis_description="Pain in right knee",
        diagnosis_code="M25.561",
    ),
    ReferenceCode(
        service_description="Manual therapy techniques, physical therapy",
        service_code="97140",
        service_code_type="CPT",
        diagnosis_description="Other specified postprocedural states, knee",
        diagnosis_code="Z98.89",
    ),
]


def reference_codes_text() -> str:
    """Render the fixed reference table as short lines for prompt context."""
    lines = [
        f"- {c.service_description} -> {c.service_code_type} {c.service_code}; "
        f"{c.diagnosis_description} -> ICD-10 {c.diagnosis_code}"
        for c in REFERENCE_CODES
    ]
    return "\n".join(lines)
