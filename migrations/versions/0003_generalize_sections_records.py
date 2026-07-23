"""generalize sections and records (replace fixed spa/car/hotel/ps tables
and the Settings.tabs JSON blob with a generic sections+records model so an
owner can create arbitrary business sections from a small set of templates)

Revision ID: 0003_generalize_sections_records
Revises: 6848eb43c6a6
Create Date: 2026-07-21

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_generalize_sections_records"
down_revision: Union[str, None] = "6848eb43c6a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_TABS = {
    "spa": {"enabled": True, "label": "Баня"},
    "car": {"enabled": True, "label": "Автомойка"},
    "hotel": {"enabled": True, "label": "Гостиница"},
    "ps": {"enabled": True, "label": "PS"},
}
SECTION_META = {
    "spa": ("💧", "time_slot"),
    "car": ("🚗", "queue"),
    "hotel": ("🏨", "date_range"),
    "ps": ("🎮", "queue"),
}


def upgrade() -> None:
    bind = op.get_bind()

    op.create_table(
        "sections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("icon", sa.String(), nullable=False),
        sa.Column("template", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "key", name="uq_sections_tenant_key"),
    )
    op.create_index(op.f("ix_sections_tenant_id"), "sections", ["tenant_id"], unique=False)

    op.create_table(
        "records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=True),
        sa.Column("start", sa.DateTime(), nullable=True),
        sa.Column("end", sa.DateTime(), nullable=True),
        sa.Column("adult", sa.Integer(), nullable=True),
        sa.Column("child", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_records_tenant_id"), "records", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_records_section"), "records", ["section"], unique=False)
    op.create_index(op.f("ix_records_start"), "records", ["start"], unique=False)
    op.create_index(op.f("ix_records_end"), "records", ["end"], unique=False)

    # --- seed sections per tenant from existing Settings.tabs JSON (fallback to defaults
    # for a tenant that never wrote a settings row, e.g. one created directly via SQL) ---
    tenants = bind.execute(sa.text("SELECT id FROM tenants")).fetchall()
    for row in tenants:
        tenant_id = row.id
        settings_row = bind.execute(
            sa.text("SELECT value FROM settings WHERE tenant_id = :tid AND key = 'config'"),
            {"tid": tenant_id},
        ).fetchone()
        tabs = DEFAULT_TABS
        if settings_row is not None:
            try:
                tabs = json.loads(settings_row.value).get("tabs", DEFAULT_TABS)
            except (ValueError, AttributeError):
                tabs = DEFAULT_TABS

        for order, key in enumerate(("spa", "car", "hotel", "ps"), start=1):
            icon, template = SECTION_META[key]
            entry = tabs.get(key, DEFAULT_TABS[key])
            bind.execute(
                sa.text(
                    "INSERT INTO sections (tenant_id, key, label, icon, template, enabled, sort_order) "
                    "VALUES (:tid, :key, :label, :icon, :template, :enabled, :order)"
                ),
                {
                    "tid": tenant_id,
                    "key": key,
                    "label": entry.get("label", DEFAULT_TABS[key]["label"]),
                    "icon": icon,
                    "template": template,
                    "enabled": entry.get("enabled", True),
                    "order": order,
                },
            )

    # --- copy legacy per-business tables into the generic records table ---
    bind.execute(sa.text(
        "INSERT INTO records (tenant_id, section, resource_id, title, price, start, \"end\", adult, child) "
        "SELECT tenant_id, 'spa', split, title, price, start, \"end\", adult, child FROM events"
    ))
    bind.execute(sa.text(
        "INSERT INTO records (tenant_id, section, resource_id, title, price, start, \"end\", adult, child) "
        "SELECT tenant_id, 'hotel', split, title, price, start, \"end\", NULL, NULL FROM hotel"
    ))
    bind.execute(sa.text(
        "INSERT INTO records (tenant_id, section, resource_id, title, price, start, \"end\", adult, child) "
        "SELECT tenant_id, 'car', NULL, title, price, start, NULL, NULL, NULL FROM car"
    ))
    bind.execute(sa.text(
        "INSERT INTO records (tenant_id, section, resource_id, title, price, start, \"end\", adult, child) "
        "SELECT tenant_id, 'ps', NULL, title, price, start, NULL, NULL, NULL FROM ps"
    ))

    op.drop_table("events")
    op.drop_table("car")
    op.drop_table("ps")
    op.drop_table("hotel")
    op.drop_table("settings")


def downgrade() -> None:
    bind = op.get_bind()

    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("adult", sa.Integer(), nullable=True),
        sa.Column("child", sa.Integer(), nullable=True),
        sa.Column("split", sa.Integer(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=True),
        sa.Column("start", sa.DateTime(), nullable=True),
        sa.Column("end", sa.DateTime(), nullable=True),
        sa.Column("duration", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_events_tenant_id", "events", ["tenant_id"])
    op.create_index("ix_events_start", "events", ["start"])
    op.create_index("ix_events_end", "events", ["end"])

    op.create_table(
        "car",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=True),
        sa.Column("start", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_car_tenant_id", "car", ["tenant_id"])
    op.create_index("ix_car_start", "car", ["start"])

    op.create_table(
        "ps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=True),
        sa.Column("start", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ps_tenant_id", "ps", ["tenant_id"])
    op.create_index("ix_ps_start", "ps", ["start"])

    op.create_table(
        "hotel",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("split", sa.Integer(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=True),
        sa.Column("start", sa.DateTime(), nullable=True),
        sa.Column("end", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hotel_tenant_id", "hotel", ["tenant_id"])
    op.create_index("ix_hotel_start", "hotel", ["start"])
    op.create_index("ix_hotel_end", "hotel", ["end"])

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
    op.create_index("ix_settings_tenant_id", "settings", ["tenant_id"])

    bind.execute(sa.text(
        "INSERT INTO events (tenant_id, title, adult, child, split, price, start, \"end\", duration) "
        "SELECT tenant_id, title, adult, child, resource_id, price, start, \"end\", "
        "EXTRACT(EPOCH FROM (\"end\" - start)) / 3600.0 FROM records WHERE section = 'spa'"
    ))
    bind.execute(sa.text(
        "INSERT INTO hotel (tenant_id, title, split, price, start, \"end\") "
        "SELECT tenant_id, title, resource_id, price, start, \"end\" FROM records WHERE section = 'hotel'"
    ))
    bind.execute(sa.text(
        "INSERT INTO car (tenant_id, title, price, start) "
        "SELECT tenant_id, title, price, start FROM records WHERE section = 'car'"
    ))
    bind.execute(sa.text(
        "INSERT INTO ps (tenant_id, title, price, start) "
        "SELECT tenant_id, title, price, start FROM records WHERE section = 'ps'"
    ))

    sections = bind.execute(sa.text("SELECT tenant_id, key, label, enabled FROM sections")).fetchall()
    by_tenant = {}
    for s in sections:
        by_tenant.setdefault(s.tenant_id, {})[s.key] = {"enabled": s.enabled, "label": s.label}
    for tenant_id, tabs in by_tenant.items():
        bind.execute(
            sa.text("INSERT INTO settings (tenant_id, key, value) VALUES (:tid, 'config', :value)"),
            {"tid": tenant_id, "value": json.dumps({"tabs": tabs}, ensure_ascii=False)},
        )

    op.drop_index("ix_records_end", table_name="records")
    op.drop_index("ix_records_start", table_name="records")
    op.drop_index("ix_records_section", table_name="records")
    op.drop_index("ix_records_tenant_id", table_name="records")
    op.drop_table("records")
    op.drop_index("ix_sections_tenant_id", table_name="sections")
    op.drop_table("sections")
