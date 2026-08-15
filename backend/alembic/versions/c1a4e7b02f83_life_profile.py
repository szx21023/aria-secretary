"""life_profile 表：人生倒數的生日與預期壽命

Revision ID: c1a4e7b02f83
Revises: 7a369f628967
Create Date: 2026-08-15

"""

from collections.abc import Sequence

import sqlalchemy as sa

import app.models.base  # UTCDateTime 自訂型別
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1a4e7b02f83"  # pragma: allowlist secret
down_revision: str | None = "7a369f628967"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "life_profile",
        sa.Column("birthday", sa.Date(), nullable=False),
        sa.Column("life_expectancy", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.models.base.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("life_profile")
