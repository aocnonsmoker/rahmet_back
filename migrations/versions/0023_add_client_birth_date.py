"""add clients.birth_date — entered from the birth certificate; the client's
age is derived from it instead of being typed in and going stale.

Revision ID: 0023_add_client_birth_date
Revises: 0022_add_client_note
Create Date: 2026-10-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0023_add_client_birth_date"
down_revision: Union[str, None] = "0022_add_client_note"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("birth_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "birth_date")
