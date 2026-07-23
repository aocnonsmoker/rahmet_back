"""add slot_step_minutes to sections (configurable time-slot granularity
per section, since different businesses using the time_slot template may
want 15/30/60-minute booking steps instead of the fixed 30 minutes)

Revision ID: 0004_add_slot_step_minutes
Revises: 0003_generalize_sections_records
Create Date: 2026-07-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_add_slot_step_minutes"
down_revision: Union[str, None] = "0003_generalize_sections_records"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sections", sa.Column("slot_step_minutes", sa.Integer(), nullable=False, server_default="30"))
    op.alter_column("sections", "slot_step_minutes", server_default=None)


def downgrade() -> None:
    op.drop_column("sections", "slot_step_minutes")
