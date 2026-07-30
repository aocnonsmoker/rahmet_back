"""add trainers table (club module) plus a trainer link on resources
(a group can have a trainer) and a resource link on trial_lessons
(so a trial lesson can be tied to a specific group, not just a section).

Revision ID: 0007_add_trainers
Revises: 0006_add_club_module
Create Date: 2026-07-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_add_trainers"
down_revision: Union[str, None] = "0006_add_club_module"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trainers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.alter_column("trainers", "is_active", server_default=None)
    op.create_index(op.f("ix_trainers_tenant_id"), "trainers", ["tenant_id"], unique=False)

    op.add_column("resources", sa.Column("trainer_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_resources_trainer_id", "resources", "trainers", ["trainer_id"], ["id"])

    op.add_column("trial_lessons", sa.Column("resource_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_trial_lessons_resource_id", "trial_lessons", "resources", ["resource_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_trial_lessons_resource_id", "trial_lessons", type_="foreignkey")
    op.drop_column("trial_lessons", "resource_id")

    op.drop_constraint("fk_resources_trainer_id", "resources", type_="foreignkey")
    op.drop_column("resources", "trainer_id")

    op.drop_index(op.f("ix_trainers_tenant_id"), table_name="trainers")
    op.drop_table("trainers")
