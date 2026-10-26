import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("number", sa.String(64), nullable=False),
        sa.Column("insured", sa.String(255), nullable=False),
        sa.Column("access_group", sa.String(128), nullable=False),
    )
    op.create_index("ix_policies_number", "policies", ["number"])
    op.create_index("ix_policies_access_group", "policies", ["access_group"])
    op.create_table(
        "policy_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("policy_id", sa.Integer(), sa.ForeignKey("policies.id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("file_key", sa.String(512), nullable=False),
        sa.Column("addendum_number", sa.String(32), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("applies_to", sa.JSON(), nullable=False),
        sa.Column("changed_clauses", sa.JSON(), nullable=False),
    )
    op.create_index("ix_policy_documents_policy_id", "policy_documents", ["policy_id"])
    op.create_table(
        "policy_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("policy_id", sa.Integer(), sa.ForeignKey("policies.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("approved_by", sa.String(128), nullable=False),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_policy_profiles_policy_id", "policy_profiles", ["policy_id"])
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("stage", sa.String(64), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("timings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_table(
        "declarations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("policy_id", sa.Integer(), sa.ForeignKey("policies.id"), nullable=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=True),
        sa.Column("access_group", sa.String(128), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_key", sa.String(512), nullable=False),
        sa.Column("number", sa.String(64), nullable=False),
        sa.Column("form", sa.String(32), nullable=False),
        sa.Column("shipments", sa.Integer(), nullable=False),
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column("result_key", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_declarations_access_group", "declarations", ["access_group"])
    op.create_index("ix_declarations_month", "declarations", ["month"])
    op.create_table(
        "check_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("declaration_id", sa.Integer(), sa.ForeignKey("declarations.id"), nullable=False),
        sa.Column("line", sa.String(32), nullable=False),
        sa.Column("field", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("clause", sa.String(255), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("source", sa.String(8), nullable=False),
        sa.Column("correction", sa.Text(), nullable=False),
    )
    op.create_index("ix_check_results_declaration_id", "check_results", ["declaration_id"])
    op.create_table(
        "rule_sets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(512), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "eval_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code_version", sa.String(64), nullable=False),
        sa.Column("cards_version", sa.String(64), nullable=False),
        sa.Column("accuracy", sa.JSON(), nullable=False),
        sa.Column("seconds", sa.Float(), nullable=False),
        sa.Column("llm_calls", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=True),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False),
        sa.Column("tokens_out", sa.Integer(), nullable=False),
        sa.Column("latency", sa.Float(), nullable=False),
        sa.Column("valid", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_llm_calls_job_id", "llm_calls", ["job_id"])


def downgrade() -> None:
    for table in (
        "llm_calls",
        "eval_runs",
        "rule_sets",
        "check_results",
        "declarations",
        "jobs",
        "policy_profiles",
        "policy_documents",
        "policies",
    ):
        op.drop_table(table)
