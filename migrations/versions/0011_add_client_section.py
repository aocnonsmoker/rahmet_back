"""add clients.section — a client card now belongs to one club-template
section's roster (created there via "+ Добавить клиента"), instead of being
implicitly created/reused by phone match from inside the membership form.
Existing clients are backfilled from any membership's section.

Revision ID: 0011_add_client_section
Revises: 0010_seed_superadmin
Create Date: 2026-08-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011_add_client_section"
down_revision: Union[str, None] = "0010_seed_superadmin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("section", sa.String(), nullable=True))

    op.execute(
        "UPDATE clients SET section = sub.section FROM ("
        "  SELECT DISTINCT ON (client_id) client_id, section "
        "  FROM memberships ORDER BY client_id, id"
        ") AS sub WHERE clients.id = sub.client_id"
    )
    # Any client left without a membership (created directly, or orphaned test
    # data) has no section to infer — fall back to a placeholder so the
    # column can be made NOT NULL; harmless, such a card just won't show up
    # in any real roster until edited.
    op.execute("UPDATE clients SET section = '' WHERE section IS NULL")

    op.alter_column("clients", "section", nullable=False)
    op.create_index(op.f("ix_clients_section"), "clients", ["section"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_clients_section"), table_name="clients")
    op.drop_column("clients", "section")
