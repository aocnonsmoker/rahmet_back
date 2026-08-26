"""group_schedules.days_of_week + start_time/end_time (one shared time range
for all selected days) -> day_times JSONB (each day of the week can have its
own start/end time, e.g. Пн 16:00-17:00, Ср 18:00-19:00). Feedback from Urban
Sport: a group's schedule isn't always the same time every day.

Revision ID: 0016_group_schedule_day_times
Revises: 0015_group_schedule_room_id
Create Date: 2026-08-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, ARRAY


revision: str = "0016_group_schedule_day_times"
down_revision: Union[str, None] = "0015_group_schedule_room_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("group_schedules", sa.Column("day_times", JSONB(), nullable=True))

    op.execute(
        "UPDATE group_schedules SET day_times = ("
        "  SELECT jsonb_agg(jsonb_build_object("
        "    'day', d,"
        "    'start_time', to_char(start_time, 'HH24:MI'),"
        "    'end_time', to_char(end_time, 'HH24:MI')"
        "  ))"
        "  FROM unnest(days_of_week) AS d"
        ")"
    )

    op.alter_column("group_schedules", "day_times", nullable=False)
    op.drop_column("group_schedules", "days_of_week")
    op.drop_column("group_schedules", "start_time")
    op.drop_column("group_schedules", "end_time")


def downgrade() -> None:
    op.add_column("group_schedules", sa.Column("days_of_week", ARRAY(sa.Integer()), nullable=True))
    op.add_column("group_schedules", sa.Column("start_time", sa.Time(), nullable=True))
    op.add_column("group_schedules", sa.Column("end_time", sa.Time(), nullable=True))

    # Best-effort — collapses per-day times back into one shared range taken
    # from the first day, same pattern as other lossy downgrades in this chain.
    op.execute(
        "UPDATE group_schedules SET "
        "  days_of_week = (SELECT array_agg((elem->>'day')::int) FROM jsonb_array_elements(day_times) AS elem),"
        "  start_time = (day_times->0->>'start_time')::time,"
        "  end_time = (day_times->0->>'end_time')::time"
    )

    op.alter_column("group_schedules", "days_of_week", nullable=False)
    op.alter_column("group_schedules", "start_time", nullable=False)
    op.alter_column("group_schedules", "end_time", nullable=False)
    op.drop_column("group_schedules", "day_times")
