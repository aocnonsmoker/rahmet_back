"""seed the platform-admin account — a service tenant ("jmb") that exists only
to hold the superadmin login, reusing the same tenant_slug/username/password
login form as every other user instead of a separate auth flow.

Revision ID: 0010_seed_superadmin
Revises: 0009_trainer_multi_group
Create Date: 2026-07-31

"""
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import bcrypt


revision: str = "0010_seed_superadmin"
down_revision: Union[str, None] = "0009_trainer_multi_group"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ADMIN_SLUG = "jmb"


def upgrade() -> None:
    bind = op.get_bind()

    tenant_id = bind.execute(
        sa.text("INSERT INTO tenants (name, slug) VALUES (:name, :slug) RETURNING id"),
        {"name": "Platform Admin", "slug": ADMIN_SLUG},
    ).scalar_one()

    bind.execute(
        sa.text(
            "INSERT INTO subscriptions (tenant_id, status, expires_at, notes) "
            "VALUES (:tid, 'active', :expires, :notes)"
        ),
        {"tid": tenant_id, "expires": datetime(2099, 1, 1), "notes": "Служебный тенант для платформенной админки"},
    )

    password_hash = bcrypt.hashpw(b"nonsmoker123", bcrypt.gensalt()).decode()
    bind.execute(
        sa.text(
            "INSERT INTO users (tenant_id, username, password_hash, role, is_active, read_only) "
            "VALUES (:tid, 'zhambo', :ph, 'superadmin', true, false)"
        ),
        {"tid": tenant_id, "ph": password_hash},
    )


def downgrade() -> None:
    bind = op.get_bind()
    tenant_id = bind.execute(sa.text("SELECT id FROM tenants WHERE slug = :slug"), {"slug": ADMIN_SLUG}).scalar_one_or_none()
    if tenant_id is None:
        return
    bind.execute(sa.text("DELETE FROM users WHERE tenant_id = :tid"), {"tid": tenant_id})
    bind.execute(sa.text("DELETE FROM subscriptions WHERE tenant_id = :tid"), {"tid": tenant_id})
    bind.execute(sa.text("DELETE FROM tenants WHERE id = :tid"), {"tid": tenant_id})
