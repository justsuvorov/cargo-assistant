import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("llm_calls") as table:
        table.add_column(sa.Column("provider", sa.String(32), nullable=False, server_default=""))
        table.add_column(sa.Column("model", sa.String(128), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("llm_calls") as table:
        table.drop_column("model")
        table.drop_column("provider")
