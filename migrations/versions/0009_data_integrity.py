from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("policy_profiles") as batch:
        batch.create_unique_constraint("uq_profile_version", ["policy_id", "version"])


def downgrade() -> None:
    with op.batch_alter_table("policy_profiles") as batch:
        batch.drop_constraint("uq_profile_version", type_="unique")
