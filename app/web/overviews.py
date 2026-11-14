from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import select

from app.auth.identity import Identity
from app.jobs.errors import MissingProfileError, SchemaVersionError
from app.jobs.models import Declaration, Job, Policy, Workspace
from app.jobs.queue import Snapshot
from app.web.security import services

_FOLDER = "/folder/"


@dataclass(frozen=True)
class Line:
    """Declaration of a session with the state of its job and its path inside the folder."""

    declaration: Declaration
    job: Snapshot
    path: str


@dataclass(frozen=True)
class Basis:
    """Profile of the policy as a page tells it: its status (none before the start, missing when
    no profile was built, draft or approved), the version and the problems of the package."""

    status: str
    version: int
    problems: tuple[str, ...]


@dataclass(frozen=True)
class Overview:
    """Everything a page or the API tells about one session: its declarations with the state of
    their jobs, the policy, the profile they are checked by and the build of that profile."""

    workspace: Workspace
    lines: tuple[Line, ...]
    policy: Policy | None
    basis: Basis
    build: Snapshot | None

    def started(self) -> bool:
        return self.workspace.started_at is not None

    def finished(self) -> bool:
        return bool(self.lines) and all(line.job.finished() for line in self.lines)

    def done(self) -> int:
        return sum(1 for line in self.lines if line.job.status == "done")

    def results(self) -> int:
        return sum(1 for line in self.lines if line.declaration.result_key)

    def progress(self) -> int:
        return (
            sum(100 if line.job.finished() else line.job.progress for line in self.lines)
            // len(self.lines)
            if self.lines
            else 0
        )


async def overview(request: Request, who: Identity, workspace: Workspace) -> Overview:
    async with services(request).database.session() as session:
        found = (
            await session.execute(
                select(Declaration, Job)
                .join(Job, Declaration.job_id == Job.id)
                .where(Declaration.workspace_id == workspace.id, Declaration.owner == who.id())
                .order_by(Declaration.id)
            )
        ).all()
        policy = (
            await session.scalar(
                select(Policy).where(Policy.id == workspace.policy_id, Policy.owner == who.id())
            )
            if workspace.policy_id is not None
            else None
        )
        build = (
            await session.get(Job, policy.job_id)
            if policy is not None and policy.job_id is not None
            else None
        )
    return Overview(
        workspace,
        tuple(
            Line(declaration, Snapshot.of(job), declaration.file_key.split(_FOLDER, 1)[-1])
            for declaration, job in found
        ),
        policy,
        await basis(request, policy),
        Snapshot.of(build) if build is not None else None,
    )


async def basis(request: Request, policy: Policy | None) -> Basis:
    if policy is None:
        return Basis("none", 0, ())
    try:
        taken = await services(request).folio.taken(policy.id)
    except (MissingProfileError, SchemaVersionError):
        return Basis("missing", 0, ())
    return Basis(taken.status, taken.version, taken.problems)
