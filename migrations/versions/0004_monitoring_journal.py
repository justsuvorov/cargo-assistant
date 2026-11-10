import sqlalchemy as sa
from alembic import op

from migrations.monitoring import Views

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeats",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("host", sa.String(128), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen", sa.DateTime(), nullable=False),
        sa.Column("running", sa.Integer(), nullable=False),
        sa.Column("stopped_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_worker_heartbeats_last_seen", "worker_heartbeats", ["last_seen"])
    op.create_table(
        "job_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(36), sa.ForeignKey("worker_heartbeats.id"), nullable=True),
        sa.Column("queued_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("error_class", sa.String(128), nullable=False),
        sa.Column("error_text", sa.Text(), nullable=False),
        sa.Column("timings", sa.JSON(), nullable=False),
        sa.Column("code_version", sa.String(64), nullable=False),
        sa.Column("cards_version", sa.String(64), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("prompts_version", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
    )
    op.create_index("ix_job_runs_job_id", "job_runs", ["job_id"])
    op.create_index("ix_job_runs_worker_id", "job_runs", ["worker_id"])
    op.create_index("ix_job_runs_started_at", "job_runs", ["started_at"])
    with op.batch_alter_table("jobs") as table:
        table.add_column(sa.Column("queued_at", sa.DateTime(), nullable=True))
        table.add_column(
            sa.Column("uploaded_by", sa.String(128), nullable=False, server_default="")
        )
        table.add_column(
            sa.Column("access_group", sa.String(128), nullable=False, server_default="")
        )
        table.add_column(sa.Column("file_sha256", sa.String(64), nullable=False, server_default=""))
        table.add_column(sa.Column("outcome", sa.String(16), nullable=False, server_default=""))
        table.add_column(sa.Column("finished_at", sa.DateTime(), nullable=True))
    op.create_index("ix_jobs_file_sha256", "jobs", ["file_sha256"])
    op.execute(
        "UPDATE jobs SET outcome = CASE status WHEN 'done' THEN 'success' "
        "WHEN 'failed' THEN 'error' ELSE '' END, "
        "finished_at = CASE WHEN status IN ('done', 'failed') THEN updated_at END, "
        "queued_at = CASE WHEN status = 'queued' THEN updated_at END"
    )
    with op.batch_alter_table("llm_calls") as table:
        table.add_column(
            sa.Column("outcome", sa.String(16), nullable=False, server_default="success")
        )
        table.add_column(sa.Column("subject", sa.String(128), nullable=False, server_default=""))
        table.add_column(sa.Column("questions", sa.Integer(), nullable=False, server_default="0"))
        table.add_column(sa.Column("dropped", sa.Integer(), nullable=False, server_default="0"))
        table.add_column(sa.Column("created_at", sa.DateTime(), nullable=True))
    with op.batch_alter_table("declarations") as table:
        table.add_column(
            sa.Column("places_expected", sa.Integer(), nullable=False, server_default="0")
        )
        table.add_column(
            sa.Column("places_answered", sa.Integer(), nullable=False, server_default="0")
        )
    with op.batch_alter_table("check_results") as table:
        table.add_column(sa.Column("created_at", sa.DateTime(), nullable=True))
    if op.get_context().dialect.name == "postgresql":
        for statement in Views().creating():
            op.execute(sa.text(statement))


def downgrade() -> None:
    if op.get_context().dialect.name == "postgresql":
        for statement in Views().dropping():
            op.execute(sa.text(statement))
    with op.batch_alter_table("check_results") as table:
        table.drop_column("created_at")
    with op.batch_alter_table("declarations") as table:
        table.drop_column("places_answered")
        table.drop_column("places_expected")
    with op.batch_alter_table("llm_calls") as table:
        table.drop_column("created_at")
        table.drop_column("dropped")
        table.drop_column("questions")
        table.drop_column("subject")
        table.drop_column("outcome")
    op.drop_index("ix_jobs_file_sha256", "jobs")
    with op.batch_alter_table("jobs") as table:
        table.drop_column("finished_at")
        table.drop_column("outcome")
        table.drop_column("file_sha256")
        table.drop_column("access_group")
        table.drop_column("uploaded_by")
        table.drop_column("queued_at")
    op.drop_table("job_runs")
    op.drop_table("worker_heartbeats")
