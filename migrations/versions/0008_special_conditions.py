import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workspaces") as batch:
        batch.add_column(
            sa.Column("client_file", sa.String(512), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column("client_chosen", sa.Boolean, nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("client_lines", sa.JSON, nullable=False, server_default="[]"))
        batch.add_column(sa.Column("client_problems", sa.JSON, nullable=False, server_default="[]"))
    with op.batch_alter_table("declarations") as batch:
        batch.add_column(sa.Column("conditions", sa.JSON, nullable=False, server_default="[]"))
        batch.add_column(
            sa.Column("conditions_problems", sa.JSON, nullable=False, server_default="[]")
        )


def downgrade() -> None:
    with op.batch_alter_table("declarations") as batch:
        batch.drop_column("conditions_problems")
        batch.drop_column("conditions")
    with op.batch_alter_table("workspaces") as batch:
        batch.drop_column("client_problems")
        batch.drop_column("client_lines")
        batch.drop_column("client_chosen")
        batch.drop_column("client_file")
