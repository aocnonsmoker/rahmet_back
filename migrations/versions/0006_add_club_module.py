"""add club module tables (clients, memberships, attendance, trial_lessons)
for the new "club" section template — sports-club style businesses with
recurring memberships/groups instead of one-off bookings.

Revision ID: 0006_add_club_module
Revises: 0005_add_guest_fields
Create Date: 2026-07-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_add_club_module"
down_revision: Union[str, None] = "0005_add_guest_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("phone", sa.String(), nullable=False),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("parent_name", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_clients_tenant_id"), "clients", ["tenant_id"], unique=False)

    op.create_table(
        "memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("payment_date", sa.DateTime(), nullable=True),
        sa.Column("start_date", sa.DateTime(), nullable=False),
        sa.Column("end_date", sa.DateTime(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_memberships_tenant_id"), "memberships", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_memberships_client_id"), "memberships", ["client_id"], unique=False)

    op.create_table(
        "attendance",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("membership_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["membership_id"], ["memberships.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("membership_id", "date", name="uq_attendance_membership_date"),
    )
    op.create_index(op.f("ix_attendance_tenant_id"), "attendance", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_attendance_membership_id"), "attendance", ["membership_id"], unique=False)
    op.create_index(op.f("ix_attendance_date"), "attendance", ["date"], unique=False)

    op.create_table(
        "trial_lessons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("phone", sa.String(), nullable=False),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("section", sa.String(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_trial_lessons_tenant_id"), "trial_lessons", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_trial_lessons_tenant_id"), table_name="trial_lessons")
    op.drop_table("trial_lessons")

    op.drop_index(op.f("ix_attendance_date"), table_name="attendance")
    op.drop_index(op.f("ix_attendance_membership_id"), table_name="attendance")
    op.drop_index(op.f("ix_attendance_tenant_id"), table_name="attendance")
    op.drop_table("attendance")

    op.drop_index(op.f("ix_memberships_client_id"), table_name="memberships")
    op.drop_index(op.f("ix_memberships_tenant_id"), table_name="memberships")
    op.drop_table("memberships")

    op.drop_index(op.f("ix_clients_tenant_id"), table_name="clients")
    op.drop_table("clients")
