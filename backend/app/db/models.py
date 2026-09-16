"""SQLAlchemy models: the `prompts` registry, `patients` (fictitious
identities), and `pa_requests` (every prior-authorization drafting run ever
started for a patient -- this doubles as both the "run history" and the
durable, status-tracked PA request record).

Note: LangGraph's `AsyncPostgresSaver` manages its own checkpoint tables
(`checkpoints`, `checkpoint_writes`, ...) via `checkpointer.setup()` -- those
are NOT modeled here and are intentionally left out of Alembic's autogenerate
scope (see `db/migrations/env.py`).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Prompt(Base):
    """A versioned prompt template.

    Only one version per `name` is `is_active` at a time; `get_prompt(name)`
    (see `app/prompts/registry.py`) resolves to that active version. There
    are exactly three prompts in this app: `extract_clinical_summary`,
    `evaluate_policy_criteria`, and `draft_pa_request`.
    """

    __tablename__ = "prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Prompt name={self.name!r} v{self.version} active={self.is_active}>"


class Patient(Base):
    """One fictitious demo patient (see `sample-data/README.md` -- entirely
    synthetic identities, never real patient data)."""

    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    member_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    date_of_birth: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    primary_payer: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    provider_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    provider_npi: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    pa_requests: Mapped[list["PARequest"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan", order_by="PARequest.created_at"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Patient name={self.name!r} member_id={self.member_id!r}>"


class PARequest(Base):
    """One end-to-end prior-authorization drafting run, keyed by the
    LangGraph `thread_id`. Every chart excerpt ever submitted for a patient
    gets a row here -- this is both the "run history" for the frontend and
    the durable, status-tracked PA request record `finalize_node` writes to.

    Nothing in `clinical_summary` / `criteria_checklist` / `draft_form` is a
    coverage decision or ready for submission until a staff member has
    reviewed it via the `staff_review` interrupt and this row's
    `final_status` reflects that decision. After that, `status` continues to
    track the request's real-world lifecycle (submitted -> approved / denied
    / more_info_requested) via `POST /pa-requests/{id}/status`, which is a
    plain field update -- not a graph re-entry -- modeling the days-to-weeks
    tracking burden this app addresses. See the root README's "Scope &
    Safety" section.
    """

    __tablename__ = "pa_requests"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    patient_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payer_name: Mapped[str] = mapped_column(String(128), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    # pending | running | awaiting_staff_review | ready_to_submit | submitted |
    # approved | denied | more_info_requested | rejected | error
    final_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # ready_to_submit | corrected_and_ready | rejected (set once by finalize_node)

    clinical_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    criteria_checklist: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    draft_form: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    trace: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    state_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Append-only lifecycle history: [{"status": ..., "timestamp": ..., "note": ...}, ...]
    status_history: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    patient: Mapped[Patient] = relationship(back_populates="pa_requests")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PARequest id={self.id} patient_id={self.patient_id!r} status={self.status!r}>"
