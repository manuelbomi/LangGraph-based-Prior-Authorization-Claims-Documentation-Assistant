"""Initial schema: prompts registry, patients (fictitious demo identities),
pa_requests (per-patient prior-authorization drafting history).

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_prompts_name", "prompts", ["name"])
    op.create_unique_constraint("uq_prompts_name_version", "prompts", ["name", "version"])

    op.create_table(
        "patients",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("member_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("date_of_birth", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("primary_payer", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("provider_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("provider_npi", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "pa_requests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "patient_id",
            sa.String(length=64),
            sa.ForeignKey("patients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("payer_name", sa.String(length=128), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("final_status", sa.String(length=32), nullable=True),
        sa.Column(
            "clinical_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "criteria_checklist",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "draft_form",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "trace",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "state_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "status_history",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_pa_requests_patient_id", "pa_requests", ["patient_id"])
    op.create_index("ix_pa_requests_created_at", "pa_requests", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_pa_requests_created_at", table_name="pa_requests")
    op.drop_index("ix_pa_requests_patient_id", table_name="pa_requests")
    op.drop_table("pa_requests")
    op.drop_table("patients")
    op.drop_constraint("uq_prompts_name_version", "prompts", type_="unique")
    op.drop_index("ix_prompts_name", table_name="prompts")
    op.drop_table("prompts")
