import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workspaces", sa.Column("client_conditions", sa.JSON, nullable=False, server_default="{}"))
    op.add_column("declarations", sa.Column("conditions", sa.JSON, nullable=False, server_default="{}"))


def downgrade() -> None:
    with op.batch_alter_table("declarations") as batch:
        batch.drop_column("conditions")
    with op.batch_alter_table("workspaces") as batch:
        batch.drop_column("client_conditions")
