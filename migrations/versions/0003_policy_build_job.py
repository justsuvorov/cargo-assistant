import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("policies") as batch:
        batch.add_column(sa.Column("job_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_policies_job_id", "jobs", ["job_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("policies") as batch:
        batch.drop_constraint("fk_policies_job_id", type_="foreignkey")
        batch.drop_column("job_id")
