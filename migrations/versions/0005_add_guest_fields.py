"""add guest_fields to sections (per-section control over whether the
time_slot template shows no guest-count field, a single generic "Количество"
field, or the adult/child split — instead of adult/child being hardcoded for
every time_slot business)

Revision ID: 0005_add_guest_fields
Revises: 0004_add_slot_step_minutes
Create Date: 2026-07-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_add_guest_fields"
down_revision: Union[str, None] = "0004_add_slot_step_minutes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sections", sa.Column("guest_fields", sa.String(), nullable=False, server_default="none"))
    op.alter_column("sections", "guest_fields", server_default=None)
    # Existing time_slot sections (e.g. Баня) already rely on the adult/child
    # split in the UI — preserve that behavior instead of silently hiding it.
    op.execute("UPDATE sections SET guest_fields = 'split' WHERE template = 'time_slot'")


def downgrade() -> None:
    op.drop_column("sections", "guest_fields")
