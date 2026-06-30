"""create core tables

Revision ID: 0001
Revises:
Create Date: 2026-06-28

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("dataset_id", sa.String(36), primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("s3_path", sa.String(500), nullable=False, server_default=""),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("col_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="READY"),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "jobs",
        sa.Column("job_id", sa.String(36), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.String(36),
            sa.ForeignKey("datasets.dataset_id"),
            nullable=False,
        ),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="QUEUED"),
        sa.Column("current_node", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("report_id", sa.String(36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "reports",
        sa.Column("report_id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.job_id"), nullable=False),
        sa.Column(
            "dataset_id",
            sa.String(36),
            sa.ForeignKey("datasets.dataset_id"),
            nullable=False,
        ),
        sa.Column("s3_path", sa.String(500), nullable=False, server_default=""),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("report_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "feedback",
        sa.Column("feedback_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "report_id",
            sa.String(36),
            sa.ForeignKey("reports.report_id"),
            nullable=False,
        ),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("feedback")
    op.drop_table("reports")
    op.drop_table("jobs")
    op.drop_table("datasets")
