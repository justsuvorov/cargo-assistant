import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

_VERSIONS = (
    ("code_version", sa.String(64)),
    ("cards_version", sa.String(64)),
    ("prompts_version", sa.String(64)),
    ("model", sa.String(128)),
)


def upgrade() -> None:
    with op.batch_alter_table("check_results") as batch:
        batch.create_unique_constraint("uq_check_place", ["declaration_id", "line", "field"])
    with op.batch_alter_table("declarations") as batch:
        for name, kind in _VERSIONS:
            batch.add_column(sa.Column(name, kind, nullable=False, server_default=""))
        batch.add_column(
            sa.Column("profile_version", sa.Integer, nullable=False, server_default="0")
        )
    op.create_table(
        "corrections",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("declaration_id", sa.Integer, sa.ForeignKey("declarations.id"), nullable=False),
        sa.Column("line", sa.String(32), nullable=False),
        sa.Column("field", sa.String(64), nullable=False),
        sa.Column("author", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("seen_status", sa.String(16), nullable=False, server_default=""),
        sa.Column("comment", sa.Text, nullable=False, server_default=""),
        sa.UniqueConstraint("declaration_id", "line", "field", name="uq_correction"),
    )
    op.create_index("ix_corrections_declaration_id", "corrections", ["declaration_id"])


def downgrade() -> None:
    op.drop_index("ix_corrections_declaration_id", table_name="corrections")
    op.drop_table("corrections")
    with op.batch_alter_table("declarations") as batch:
        batch.drop_column("profile_version")
        for name, _ in reversed(_VERSIONS):
            batch.drop_column(name)
    with op.batch_alter_table("check_results") as batch:
        batch.drop_constraint("uq_check_place", type_="unique")
