"""add memberships.contract_number — Urban Sport tracks a manual contract
number per abonement on paper (already numbered 1-18); no backfill, existing
rows just get NULL.

Revision ID: 0013_add_contract_number
Revises: 0012_add_group_schedule
Create Date: 2026-08-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0013_add_contract_number"
down_revision: Union[str, None] = "0012_add_group_schedule"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("memberships", sa.Column("contract_number", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("memberships", "contract_number")
