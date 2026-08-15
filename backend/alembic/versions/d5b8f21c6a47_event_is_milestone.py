"""events 加 is_milestone：標記人生里程碑

Revision ID: d5b8f21c6a47
Revises: c1a4e7b02f83
Create Date: 2026-08-16

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5b8f21c6a47"  # pragma: allowlist secret
down_revision: str | None = "c1a4e7b02f83"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default 讓既有列直接補 false；之後由 ORM 的 default 負責新列，
    # 故建完就把 DB 端預設拿掉，避免與 models 的定義分歧。
    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_milestone", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.alter_column("is_milestone", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.drop_column("is_milestone")
