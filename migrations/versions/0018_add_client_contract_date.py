"""add clients.contract_date — set automatically alongside contract_number
when a client card is created, same as the number.

Revision ID: 0018_add_client_contract_date
Revises: 0017_contract_number_to_client
Create Date: 2026-09-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0018_add_client_contract_date"
down_revision: Union[str, None] = "0017_contract_number_to_client"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("contract_date", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "contract_date")
