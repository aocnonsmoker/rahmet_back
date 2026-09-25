"""add memberships.paid — a renewal/creation made without payment shows as
"Долг" (debt) on the client card instead of silently looking active.

Revision ID: 0021_add_membership_paid
Revises: 0020_add_audit_logs
Create Date: 2026-09-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0021_add_membership_paid"
down_revision: Union[str, None] = "0020_add_audit_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "memberships",
        sa.Column("paid", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("memberships", "paid", server_default=None)


def downgrade() -> None:
    op.drop_column("memberships", "paid")
