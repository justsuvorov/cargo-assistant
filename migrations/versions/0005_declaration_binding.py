import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("declarations") as batch:
        batch.add_column(sa.Column("binding", sa.String(32), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("declarations") as batch:
        batch.drop_column("binding")
