from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    """Common parent of every table of the service."""


class Policy(Base):
    """General policy of one owner with its insured party, the folder it was read from and its
    last build; the folder is told apart by the checksum of the files of the policy and the
    addenda, so the same files of the same owner are one policy."""

    __tablename__ = "policies"
    __table_args__ = (UniqueConstraint("owner", "package_sha", name="uq_policy_package"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(64), default="", index=True)
    insured: Mapped[str] = mapped_column(String(255), default="")
    owner: Mapped[str] = mapped_column(String(128), default="", index=True)
    package_sha: Mapped[str] = mapped_column(String(64), default="")
    package_key: Mapped[str] = mapped_column(String(512), default="")
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)


class Workspace(Base):
    """Session of a user: the folder of a policy that the user opened, the declarations found in
    it and the policy it is checked against; it belongs to one owner, the Keycloak subject."""

    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner: Mapped[str] = mapped_column(String(128), index=True)
    owner_name: Mapped[str] = mapped_column(String(128), default="")
    name: Mapped[str] = mapped_column(String(255), default="")
    found: Mapped[list[str]] = mapped_column(JSON, default=list)
    package_sha: Mapped[str] = mapped_column(String(64), default="")
    client_file: Mapped[str] = mapped_column(String(512), default="")
    client_chosen: Mapped[bool] = mapped_column(Boolean, default=False)
    client_lines: Mapped[list[str]] = mapped_column(JSON, default=list)
    client_problems: Mapped[list[str]] = mapped_column(JSON, default=list)
    policy_id: Mapped[int | None] = mapped_column(ForeignKey("policies.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PolicyDocument(Base):
    """File of a policy package: the policy itself, an addendum, special terms or carriers."""

    __tablename__ = "policy_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policies.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    file_key: Mapped[str] = mapped_column(String(512))
    addendum_number: Mapped[str] = mapped_column(String(32), default="")
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    applies_to: Mapped[list[str]] = mapped_column(JSON, default=list)
    changed_clauses: Mapped[list[str]] = mapped_column(JSON, default=list)


class PolicyProfile(Base):
    """Versioned profile of a policy extracted from its documents and approved by an expert."""

    __tablename__ = "policy_profiles"
    __table_args__ = (UniqueConstraint("policy_id", "version", name="uq_profile_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policies.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    body: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    approved_by: Mapped[str] = mapped_column(String(128), default="")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Job(Base):
    """Unit of background work with its progress, stage timings and attempt counter."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(64), default="")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    timings: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    uploaded_by: Mapped[str] = mapped_column(String(128), default="")
    access_group: Mapped[str] = mapped_column(String(128), default="")
    file_sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    outcome: Mapped[str] = mapped_column(String(16), default="")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Declaration(Base):
    """Declaration of a session that waits for, or already has, a reconciliation result."""

    __tablename__ = "declarations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[int | None] = mapped_column(ForeignKey("policies.id"), nullable=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    owner: Mapped[str] = mapped_column(String(128), default="", index=True)
    workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspaces.id"), nullable=True, index=True
    )
    file_name: Mapped[str] = mapped_column(String(255))
    file_key: Mapped[str] = mapped_column(String(512), default="")
    number: Mapped[str] = mapped_column(String(64), default="")
    form: Mapped[str] = mapped_column(String(32), default="")
    shipments: Mapped[int] = mapped_column(Integer, default=0)
    month: Mapped[str] = mapped_column(String(7), default="", index=True)
    binding: Mapped[str] = mapped_column(String(32), default="")
    result_key: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime)
    places_expected: Mapped[int] = mapped_column(Integer, default=0)
    places_answered: Mapped[int] = mapped_column(Integer, default=0)
    code_version: Mapped[str] = mapped_column(String(64), default="")
    cards_version: Mapped[str] = mapped_column(String(64), default="")
    profile_version: Mapped[int] = mapped_column(Integer, default=0)
    profile_status: Mapped[str] = mapped_column(String(16), default="")
    prompts_version: Mapped[str] = mapped_column(String(64), default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    conditions: Mapped[list[list[str]]] = mapped_column(JSON, default=list)
    conditions_problems: Mapped[list[str]] = mapped_column(JSON, default=list)


class CheckResult(Base):
    """Verdict on one field of one declaration row, with its reason, clause and source."""

    __tablename__ = "check_results"
    __table_args__ = (UniqueConstraint("declaration_id", "line", "field", name="uq_check_place"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    declaration_id: Mapped[int] = mapped_column(ForeignKey("declarations.id"), index=True)
    line: Mapped[str] = mapped_column(String(32))
    field: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(64))
    clause: Mapped[str] = mapped_column(String(255), default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(8))
    correction: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=utc)


class Correction(Base):
    """Correction of one check result by an expert; a new run of the job leaves it in place and
    the status of the check that the expert saw stays next to it."""

    __tablename__ = "corrections"
    __table_args__ = (UniqueConstraint("declaration_id", "line", "field", name="uq_correction"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    declaration_id: Mapped[int] = mapped_column(ForeignKey("declarations.id"), index=True)
    line: Mapped[str] = mapped_column(String(32))
    field: Mapped[str] = mapped_column(String(64))
    author: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16))
    seen_status: Mapped[str] = mapped_column(String(16), default="")
    comment: Mapped[str] = mapped_column(Text, default="")


class RuleSet(Base):
    """Version of the rule cards compiled from a knowledge base file."""

    __tablename__ = "rule_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    source_key: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(16), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime)


class EvalRun(Base):
    """Run of the gold set with accuracy per field, duration and number of model calls."""

    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code_version: Mapped[str] = mapped_column(String(64))
    cards_version: Mapped[str] = mapped_column(String(64))
    accuracy: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    seconds: Mapped[float] = mapped_column(Float, default=0.0)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class LLMCall(Base):
    """Record of one call to the model gateway."""

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True, index=True)
    purpose: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(32), default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    prompt_hash: Mapped[str] = mapped_column(String(64))
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    latency: Mapped[float] = mapped_column(Float, default=0.0)
    valid: Mapped[bool] = mapped_column(default=True)
    outcome: Mapped[str] = mapped_column(String(16), default="success")
    subject: Mapped[str] = mapped_column(String(128), default="")
    questions: Mapped[int] = mapped_column(Integer, default=0)
    dropped: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=utc)


class WorkerHeartbeat(Base):
    """Worker process with the moment it started, its last signal and how many jobs it runs."""

    __tablename__ = "worker_heartbeats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    host: Mapped[str] = mapped_column(String(128))
    pid: Mapped[int] = mapped_column(Integer)
    version: Mapped[str] = mapped_column(String(64), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime)
    last_seen: Mapped[datetime] = mapped_column(DateTime, index=True)
    running: Mapped[int] = mapped_column(Integer, default=0)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class JobRun(Base):
    """One attempt to run a job on a worker, with its outcome, stage times and versions."""

    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    worker_id: Mapped[str | None] = mapped_column(
        ForeignKey("worker_heartbeats.id"), nullable=True, index=True
    )
    queued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), default="running")
    error_class: Mapped[str] = mapped_column(String(128), default="")
    error_text: Mapped[str] = mapped_column(Text, default="")
    timings: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    code_version: Mapped[str] = mapped_column(String(64), default="")
    cards_version: Mapped[str] = mapped_column(String(64), default="")
    profile_version: Mapped[int] = mapped_column(Integer, default=0)
    prompts_version: Mapped[str] = mapped_column(String(64), default="")
    model: Mapped[str] = mapped_column(String(128), default="")
