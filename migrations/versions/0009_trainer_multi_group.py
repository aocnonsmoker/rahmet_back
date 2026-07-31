"""invert the trainer/group relationship — a trainer now teaches several
groups (resources), assigned when creating/editing the trainer, instead of
each group picking one trainer. Replaces resources.trainer_id (single
trainer) with a trainer_resources join table.

Revision ID: 0009_trainer_multi_group
Revises: 0008_membership_multi_group
Create Date: 2026-07-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_trainer_multi_group"
down_revision: Union[str, None] = "0008_membership_multi_group"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trainer_resources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trainer_id", sa.Integer(), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["trainer_id"], ["trainers.id"]),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trainer_id", "resource_id", name="uq_trainer_resources"),
    )
    op.create_index(op.f("ix_trainer_resources_trainer_id"), "trainer_resources", ["trainer_id"], unique=False)
    op.create_index(op.f("ix_trainer_resources_resource_id"), "trainer_resources", ["resource_id"], unique=False)

    op.execute(
        "INSERT INTO trainer_resources (trainer_id, resource_id) "
        "SELECT trainer_id, id FROM resources WHERE trainer_id IS NOT NULL"
    )

    op.drop_constraint("fk_resources_trainer_id", "resources", type_="foreignkey")
    op.drop_column("resources", "trainer_id")


def downgrade() -> None:
    op.add_column("resources", sa.Column("trainer_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_resources_trainer_id", "resources", "trainers", ["trainer_id"], ["id"])

    op.execute(
        "UPDATE resources SET trainer_id = sub.trainer_id FROM ("
        "  SELECT DISTINCT ON (resource_id) resource_id, trainer_id "
        "  FROM trainer_resources ORDER BY resource_id, trainer_id"
        ") AS sub WHERE resources.id = sub.resource_id"
    )

    op.drop_index(op.f("ix_trainer_resources_resource_id"), table_name="trainer_resources")
    op.drop_index(op.f("ix_trainer_resources_trainer_id"), table_name="trainer_resources")
    op.drop_table("trainer_resources")
