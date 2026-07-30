"""allow a membership to span multiple groups (resources) — a client can
attend several groups on one membership. Replaces memberships.resource_id
(single group) with a membership_resources join table.

Revision ID: 0008_membership_multi_group
Revises: 0007_add_trainers
Create Date: 2026-07-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_membership_multi_group"
down_revision: Union[str, None] = "0007_add_trainers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "membership_resources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("membership_id", sa.Integer(), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["membership_id"], ["memberships.id"]),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("membership_id", "resource_id", name="uq_membership_resources"),
    )
    op.create_index(
        op.f("ix_membership_resources_membership_id"), "membership_resources", ["membership_id"], unique=False
    )
    op.create_index(
        op.f("ix_membership_resources_resource_id"), "membership_resources", ["resource_id"], unique=False
    )

    op.execute(
        "INSERT INTO membership_resources (membership_id, resource_id) "
        "SELECT id, resource_id FROM memberships WHERE resource_id IS NOT NULL"
    )

    op.drop_constraint("memberships_resource_id_fkey", "memberships", type_="foreignkey")
    op.drop_column("memberships", "resource_id")


def downgrade() -> None:
    op.add_column("memberships", sa.Column("resource_id", sa.Integer(), nullable=True))
    op.create_foreign_key("memberships_resource_id_fkey", "memberships", "resources", ["resource_id"], ["id"])

    op.execute(
        "UPDATE memberships SET resource_id = sub.resource_id FROM ("
        "  SELECT DISTINCT ON (membership_id) membership_id, resource_id "
        "  FROM membership_resources ORDER BY membership_id, resource_id"
        ") AS sub WHERE memberships.id = sub.membership_id"
    )

    op.alter_column("memberships", "resource_id", nullable=False)

    op.drop_index(op.f("ix_membership_resources_resource_id"), table_name="membership_resources")
    op.drop_index(op.f("ix_membership_resources_membership_id"), table_name="membership_resources")
    op.drop_table("membership_resources")
