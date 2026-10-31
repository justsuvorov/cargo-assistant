from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Common parent of every table of the service."""


class Policy(Base):
    """General policy with the insured party and the group that may see its data."""

    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(64), index=True)
    insured: Mapped[str] = mapped_column(String(255), default="")
    access_group: Mapped[str] = mapped_column(String(128), index=True)


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


class Declaration(Base):
    """Uploaded declaration file that waits for, or already has, a reconciliation result."""

    __tablename__ = "declarations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[int | None] = mapped_column(ForeignKey("policies.id"), nullable=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    access_group: Mapped[str] = mapped_column(String(128), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_key: Mapped[str] = mapped_column(String(512), default="")
    number: Mapped[str] = mapped_column(String(64), default="")
    form: Mapped[str] = mapped_column(String(32), default="")
    shipments: Mapped[int] = mapped_column(Integer, default=0)
    month: Mapped[str] = mapped_column(String(7), default="", index=True)
    result_key: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime)


class CheckResult(Base):
    """Verdict on one field of one declaration row, with its reason, clause and source."""

    __tablename__ = "check_results"

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
