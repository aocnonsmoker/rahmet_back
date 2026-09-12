"""move contract_number from memberships to clients — a contract belongs to
the client, not to a specific abonement (memberships.contract_number was
being re-numbered per abonement, which was wrong).

Revision ID: 0017_contract_number_to_client
Revises: 0016_group_schedule_day_times
Create Date: 2026-09-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0017_contract_number_to_client"
down_revision: Union[str, None] = "0016_group_schedule_day_times"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("contract_number", sa.String(), nullable=True))
    op.execute(
        """
        UPDATE clients c SET contract_number = m.contract_number
        FROM memberships m
        WHERE m.client_id = c.id AND m.contract_number IS NOT NULL
        """
    )
    op.drop_column("memberships", "contract_number")


def downgrade() -> None:
    op.add_column("memberships", sa.Column("contract_number", sa.String(), nullable=True))
    op.execute(
        """
        UPDATE memberships m SET contract_number = c.contract_number
        FROM clients c
        WHERE c.id = m.client_id AND c.contract_number IS NOT NULL
        """
    )
    op.drop_column("clients", "contract_number")
