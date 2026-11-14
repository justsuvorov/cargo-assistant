import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("owner", sa.String(128), nullable=False),
        sa.Column("owner_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        sa.Column("found", sa.JSON, nullable=False),
        sa.Column("policy_id", sa.Integer, sa.ForeignKey("policies.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_workspaces_owner", "workspaces", ["owner"])
    with op.batch_alter_table("policies") as batch:
        batch.add_column(sa.Column("owner", sa.String(128), nullable=False, server_default=""))
        batch.add_column(sa.Column("package_sha", sa.String(64), nullable=False, server_default=""))
        batch.add_column(sa.Column("package_key", sa.String(512), nullable=False, server_default=""))
    op.execute("UPDATE policies SET package_sha = 'legacy-' || CAST(id AS VARCHAR(20))")
    with op.batch_alter_table("policies") as batch:
        batch.create_index("ix_policies_owner", ["owner"])
        batch.create_unique_constraint("uq_policy_package", ["owner", "package_sha"])
        batch.drop_index("ix_policies_access_group")
        batch.drop_column("access_group")
    with op.batch_alter_table("declarations") as batch:
        batch.add_column(sa.Column("owner", sa.String(128), nullable=False, server_default=""))
        batch.add_column(sa.Column("workspace_id", sa.Integer, nullable=True))
        batch.add_column(
            sa.Column("profile_status", sa.String(16), nullable=False, server_default="")
        )
        batch.create_foreign_key("fk_declarations_workspace", "workspaces", ["workspace_id"], ["id"])
        batch.create_index("ix_declarations_owner", ["owner"])
        batch.create_index("ix_declarations_workspace_id", ["workspace_id"])
        batch.drop_index("ix_declarations_access_group")
        batch.drop_column("access_group")


def downgrade() -> None:
    with op.batch_alter_table("declarations") as batch:
        batch.add_column(
            sa.Column("access_group", sa.String(128), nullable=False, server_default="")
        )
        batch.create_index("ix_declarations_access_group", ["access_group"])
        batch.drop_index("ix_declarations_workspace_id")
        batch.drop_index("ix_declarations_owner")
        batch.drop_constraint("fk_declarations_workspace", type_="foreignkey")
        batch.drop_column("profile_status")
        batch.drop_column("workspace_id")
        batch.drop_column("owner")
    with op.batch_alter_table("policies") as batch:
        batch.add_column(
            sa.Column("access_group", sa.String(128), nullable=False, server_default="")
        )
        batch.create_index("ix_policies_access_group", ["access_group"])
        batch.drop_constraint("uq_policy_package", type_="unique")
        batch.drop_index("ix_policies_owner")
        batch.drop_column("package_key")
        batch.drop_column("package_sha")
        batch.drop_column("owner")
    op.drop_index("ix_workspaces_owner", table_name="workspaces")
    op.drop_table("workspaces")
