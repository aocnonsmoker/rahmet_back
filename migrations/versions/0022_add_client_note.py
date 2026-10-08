"""add clients.note — free-form staff note on the client card (e.g. a family
discount for siblings, so it isn't missed when selling a membership).

Revision ID: 0022_add_client_note
Revises: 0021_add_membership_paid
Create Date: 2026-10-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0022_add_client_note"
down_revision: Union[str, None] = "0021_add_membership_paid"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "note")
