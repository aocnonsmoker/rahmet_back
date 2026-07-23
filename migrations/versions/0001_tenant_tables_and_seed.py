"""add tenant tables, seed initial "Рахмет" tenant/subscription/owner/resources

Revision ID: 0001_tenant_tables_and_seed
Revises:
Create Date: 2026-07-21

"""
import secrets
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import bcrypt


revision: str = "0001_tenant_tables_and_seed"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (sort_order, color, label) — matches the hardcoded splitDays lists that
# currently live in src/views/Hotel.vue and src/views/SPA.vue.
HOTEL_ROOMS = [
    (1, "#2196f3", "Номер 1"), (2, "#4caf50", "Номер 2"), (3, "#ff9800", "Номер 3"),
    (4, "#f44336", "Номер 4"), (5, "#9c27b0", "Номер 5"), (6, "#009688", "Номер 6"),
    (7, "#795548", "Номер 7"), (8, "#3f51b5", "Номер 8"), (9, "#827717", "Номер 9"),
    (10, "#d32f2f", "Номер 10"),
]
SPA_SAUNAS = [
    (1, "#2196f3", "Баня 1"), (2, "#4caf50", "Баня 2"),
    (3, "#ff9800", "Баня 3"), (4, "#f44336", "Баня 4"),
]

DEFAULT_SETTINGS_JSON = (
    '{"tabs": {'
    '"spa": {"enabled": true, "label": "Баня"}, '
    '"car": {"enabled": true, "label": "Автомойка"}, '
    '"hotel": {"enabled": true, "label": "Гостиница"}, '
    '"ps": {"enabled": true, "label": "PS"}'
    "}}"
)


def upgrade() -> None:
    # ### new tables ###
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "resources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("color", sa.String(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_resources_tenant_id"), "resources", ["tenant_id"], unique=False)
    op.create_table(
        "settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "key", name="uq_settings_tenant_key"),
    )
    op.create_index(op.f("ix_settings_tenant_id"), "settings", ["tenant_id"], unique=False)
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "username", name="uq_users_tenant_username"),
    )
    op.create_index(op.f("ix_users_tenant_id"), "users", ["tenant_id"], unique=False)
    op.create_table(
        "user_sections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "section", name="uq_user_sections_user_section"),
    )
    op.create_index(op.f("ix_user_sections_user_id"), "user_sections", ["user_id"], unique=False)

    # ### seed the "Рахмет" tenant so existing single-tenant data has a home ###
    bind = op.get_bind()

    tenant_id = bind.execute(
        sa.text("INSERT INTO tenants (name, slug) VALUES (:name, :slug) RETURNING id"),
        {"name": "Рахмет", "slug": "rahmet"},
    ).scalar_one()

    bind.execute(
        sa.text(
            "INSERT INTO subscriptions (tenant_id, status, expires_at, notes) "
            "VALUES (:tid, 'active', :expires, :notes)"
        ),
        {"tid": tenant_id, "expires": datetime(2099, 1, 1), "notes": "Начальный тенант, создан миграцией"},
    )

    generated_password = secrets.token_urlsafe(9)
    password_hash = bcrypt.hashpw(generated_password.encode(), bcrypt.gensalt()).decode()
    bind.execute(
        sa.text(
            "INSERT INTO users (tenant_id, username, password_hash, role, is_active) "
            "VALUES (:tid, 'owner', :ph, 'owner', true)"
        ),
        {"tid": tenant_id, "ph": password_hash},
    )
    print(
        f"\n>>> Owner-логин для тенанта 'Рахмет': username=owner password={generated_password}\n"
        ">>> Сохраните пароль сейчас — он больше нигде не отображается.\n"
    )

    bind.execute(
        sa.text("INSERT INTO settings (tenant_id, key, value) VALUES (:tid, 'config', :value)"),
        {"tid": tenant_id, "value": DEFAULT_SETTINGS_JSON},
    )

    for order, color, label in HOTEL_ROOMS:
        bind.execute(
            sa.text(
                "INSERT INTO resources (tenant_id, section, label, color, sort_order, is_active) "
                "VALUES (:tid, 'hotel', :label, :color, :order, true)"
            ),
            {"tid": tenant_id, "label": label, "color": color, "order": order},
        )
    for order, color, label in SPA_SAUNAS:
        bind.execute(
            sa.text(
                "INSERT INTO resources (tenant_id, section, label, color, sort_order, is_active) "
                "VALUES (:tid, 'spa', :label, :color, :order, true)"
            ),
            {"tid": tenant_id, "label": label, "color": color, "order": order},
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_user_sections_user_id"), table_name="user_sections")
    op.drop_table("user_sections")
    op.drop_index(op.f("ix_users_tenant_id"), table_name="users")
    op.drop_table("users")
    op.drop_table("subscriptions")
    op.drop_index(op.f("ix_settings_tenant_id"), table_name="settings")
    op.drop_table("settings")
    op.drop_index(op.f("ix_resources_tenant_id"), table_name="resources")
    op.drop_table("resources")
    op.drop_table("tenants")
