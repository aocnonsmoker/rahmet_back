"""backfill tenant_id on events/car/hotel/ps for the "Рахмет" tenant,
remap historical hotel/events split values to the new resources.id

Revision ID: 0002_backfill_tenant_id
Revises: 0001_tenant_tables_and_seed
Create Date: 2026-07-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_backfill_tenant_id"
down_revision: Union[str, None] = "0001_tenant_tables_and_seed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("car", "events", "hotel", "ps")


def _remap_split(bind, table: str, section: str, tenant_id: int) -> None:
    """Old split values referenced position in the hardcoded room/sauna list
    (e.g. hotel.split=3 meant "Номер 3"). Point them at the matching
    resources.id created in the previous revision instead."""
    rows = bind.execute(
        sa.text("SELECT id, sort_order FROM resources WHERE tenant_id = :tid AND section = :section"),
        {"tid": tenant_id, "section": section},
    ).fetchall()
    if not rows:
        return
    values_sql = ", ".join(f"({row.sort_order}, {row.id})" for row in rows)
    bind.execute(
        sa.text(
            f"UPDATE {table} SET split = m.new_id FROM (VALUES {values_sql}) AS m(old_split, new_id) "
            f"WHERE {table}.split = m.old_split"
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    tenant_id = bind.execute(sa.text("SELECT id FROM tenants WHERE slug = 'rahmet'")).scalar_one()

    # add-nullable -> backfill -> not-null, so existing rows on a live table are never blocked
    for table in TABLES:
        op.add_column(table, sa.Column("tenant_id", sa.Integer(), nullable=True))
    for table in TABLES:
        bind.execute(sa.text(f"UPDATE {table} SET tenant_id = :tid"), {"tid": tenant_id})

    _remap_split(bind, "hotel", "hotel", tenant_id)
    _remap_split(bind, "events", "spa", tenant_id)

    for table in TABLES:
        op.alter_column(table, "tenant_id", existing_type=sa.Integer(), nullable=False)
        op.create_foreign_key(None, table, "tenants", ["tenant_id"], ["id"])
        op.create_index(op.f(f"ix_{table}_tenant_id"), table, ["tenant_id"], unique=False)


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, "tenant_id")
