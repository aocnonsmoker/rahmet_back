"""add resources.kind — a Resource already plays "room/box" for time_slot and
"group" for club; this discriminator lets club sections manage a second kind
of resource ("room" — Tatami/Dayang) through the exact same CRUD, instead of
building a parallel table for it. Existing rows all become "group" (correct
for every current usage — time_slot rooms and club groups alike).

Revision ID: 0014_add_resource_kind
Revises: 0013_add_contract_number
Create Date: 2026-08-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014_add_resource_kind"
down_revision: Union[str, None] = "0013_add_contract_number"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("resources", sa.Column("kind", sa.String(), nullable=False, server_default="group"))


def downgrade() -> None:
    op.drop_column("resources", "kind")
