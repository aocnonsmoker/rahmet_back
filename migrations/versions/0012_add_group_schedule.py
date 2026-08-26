"""add group_schedules — recurring weekly class slots for a club-template
group (which room, which days of week, what time range). Feedback from the
Urban Sport demo: they need to see/derive "what runs where and when" instead
of nothing at all, and the monthly attendance journal needs it to compute
which calendar days actually belong to a group.

Revision ID: 0012_add_group_schedule
Revises: 0011_add_client_section
Create Date: 2026-08-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0012_add_group_schedule"
down_revision: Union[str, None] = "0011_add_client_section"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "group_schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("room", sa.String(), nullable=True),
        sa.Column("days_of_week", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_group_schedules_tenant_id"), "group_schedules", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_group_schedules_section"), "group_schedules", ["section"], unique=False)
    op.create_index(op.f("ix_group_schedules_resource_id"), "group_schedules", ["resource_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_group_schedules_resource_id"), table_name="group_schedules")
    op.drop_index(op.f("ix_group_schedules_section"), table_name="group_schedules")
    op.drop_index(op.f("ix_group_schedules_tenant_id"), table_name="group_schedules")
    op.drop_table("group_schedules")
