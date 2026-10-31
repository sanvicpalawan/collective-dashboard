"""Add agent_jobs queue for the AI Agency OS execution engine.

Revision ID: a1b2c3d4e5f6
Revises: e1c4d7f9a023
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "e1c4d7f9a023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("job_type", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("worker_id", sa.String(100), nullable=True),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_agent_jobs_tenant_id", "agent_jobs", ["tenant_id"])
    op.create_index("ix_agent_jobs_job_type", "agent_jobs", ["job_type"])
    op.create_index("ix_agent_jobs_status", "agent_jobs", ["status"])
    op.create_index("ix_agent_jobs_run_after", "agent_jobs", ["run_after"])
    # Queue scan: claim oldest/highest priority runnable rows first.
    op.create_index(
        "ix_agent_jobs_claim",
        "agent_jobs",
        ["status", "priority", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_jobs_claim", table_name="agent_jobs")
    op.drop_index("ix_agent_jobs_run_after", table_name="agent_jobs")
    op.drop_index("ix_agent_jobs_status", table_name="agent_jobs")
    op.drop_index("ix_agent_jobs_job_type", table_name="agent_jobs")
    op.drop_index("ix_agent_jobs_tenant_id", table_name="agent_jobs")
    op.drop_table("agent_jobs")
