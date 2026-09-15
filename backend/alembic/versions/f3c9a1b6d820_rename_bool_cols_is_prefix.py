"""布林欄位加 is_ 前綴：tasks.done→is_done、reminders.enabled→is_enabled

Revision ID: f3c9a1b6d820
Revises: d5b8f21c6a47
Create Date: 2026-09-15

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3c9a1b6d820"  # pragma: allowlist secret
down_revision: str | None = "d5b8f21c6a47"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.alter_column("done", new_column_name="is_done")
    with op.batch_alter_table("reminders", schema=None) as batch_op:
        batch_op.alter_column("enabled", new_column_name="is_enabled")


def downgrade() -> None:
    with op.batch_alter_table("reminders", schema=None) as batch_op:
        batch_op.alter_column("is_enabled", new_column_name="enabled")
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.alter_column("is_done", new_column_name="done")
