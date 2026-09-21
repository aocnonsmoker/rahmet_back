"""club module feedback fixes — trainer photo, membership freeze tracking.

Feedback from Urban Sport on the club template: trainer cards need a photo,
and freezing a membership needs to remember when the freeze started so the
end date can be pushed back by the frozen days once it's lifted.

Revision ID: 0019_club_feedback_fixes
Revises: 0018_add_client_contract_date
Create Date: 2026-09-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0019_club_feedback_fixes"
down_revision: Union[str, None] = "0018_add_client_contract_date"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("trainers", sa.Column("photo_url", sa.Text(), nullable=True))
    op.add_column("memberships", sa.Column("frozen_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("memberships", "frozen_at")
    op.drop_column("trainers", "photo_url")
