"""Read-only patient endpoints: the per-patient PA request history that
backs the "PA Request Tracking" page's patient filters."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.schemas import PARequestSummary, PatientDetail, PatientListResponse, PatientSummary
from app.db.models import Patient
from app.db.session import SessionLocal

router = APIRouter(prefix="/patients", tags=["patients"])


def _to_summary(patient: Patient) -> PatientSummary:
    return PatientSummary(
        id=patient.id,
        name=patient.name,
        member_id=patient.member_id,
        date_of_birth=patient.date_of_birth,
        primary_payer=patient.primary_payer,
    )


@router.get("", response_model=PatientListResponse)
async def list_patients() -> PatientListResponse:
    with SessionLocal() as db:
        rows = db.execute(select(Patient).order_by(Patient.name)).scalars().all()
        return PatientListResponse(patients=[_to_summary(p) for p in rows])


@router.get("/{patient_id}", response_model=PatientDetail)
async def get_patient(patient_id: str) -> PatientDetail:
    with SessionLocal() as db:
        patient = db.get(Patient, patient_id)
        if patient is None:
            raise HTTPException(404, "patient not found")
        pa_requests = [
            PARequestSummary(
                id=r.id,
                patient_id=r.patient_id,
                payer_name=r.payer_name,
                original_filename=r.original_filename,
                status=r.status,  # type: ignore[arg-type]
                final_status=r.final_status,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in patient.pa_requests
        ]
        summary = _to_summary(patient)
        return PatientDetail(
            **summary.model_dump(),
            provider_name=patient.provider_name,
            provider_npi=patient.provider_npi,
            notes=patient.notes,
            pa_requests=pa_requests,
        )
