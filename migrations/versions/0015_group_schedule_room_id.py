"""group_schedules.room (free text) -> room_id (FK to resources, kind="room").
Feedback from Urban Sport: a class always runs in a real, named room —
managed the same way as groups (add/edit/delete list in Settings), not typed
in free-hand each time. Backfills a Resource(kind="room") row for every
distinct room string already in use, per tenant+section, then repoints
group_schedules at it.

Revision ID: 0015_group_schedule_room_id
Revises: 0014_add_resource_kind
Create Date: 2026-08-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0015_group_schedule_room_id"
down_revision: Union[str, None] = "0014_add_resource_kind"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("group_schedules", sa.Column("room_id", sa.Integer(), nullable=True))

    op.execute(
        "INSERT INTO resources (tenant_id, section, label, color, sort_order, is_active, kind) "
        "SELECT DISTINCT tenant_id, section, room, '#9aa0a6', 0, true, 'room' "
        "FROM group_schedules WHERE room IS NOT NULL AND room <> ''"
    )
    op.execute(
        "UPDATE group_schedules gs SET room_id = r.id "
        "FROM resources r "
        "WHERE r.kind = 'room' AND r.tenant_id = gs.tenant_id AND r.section = gs.section AND r.label = gs.room"
    )

    op.drop_column("group_schedules", "room")
    op.alter_column("group_schedules", "room_id", nullable=False)
    op.create_foreign_key(None, "group_schedules", "resources", ["room_id"], ["id"])
    op.create_index(op.f("ix_group_schedules_room_id"), "group_schedules", ["room_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_group_schedules_room_id"), table_name="group_schedules")
    op.add_column("group_schedules", sa.Column("room", sa.String(), nullable=True))
    op.execute(
        "UPDATE group_schedules gs SET room = r.label FROM resources r WHERE r.id = gs.room_id"
    )
    op.drop_column("group_schedules", "room_id")
