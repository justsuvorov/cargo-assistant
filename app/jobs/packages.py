from dataclasses import dataclass
from typing import Final, Protocol, final

from sqlalchemy import select

from app.jobs.database import Sessions
from app.jobs.models import Policy, PolicyDocument
from app.jobs.queue import Jobs
from app.policy.package import Package
from app.storage.archive import Stored
from app.storage.disk import Storage
from app.storage.layout import Layout


@final
@dataclass(frozen=True)
class Registered:
    """Identifiers of the policy and of the job that builds its profile."""

    policy_id: int
    job_id: int


class Packages(Protocol):
    """Place where the files of a policy package turn into stored files and a build job."""

    async def receive(self, files: tuple[Stored, ...], group: str) -> Registered: ...

    async def rebuild(self, policy_id: int) -> int: ...

    async def classify(self, policy_id: int, package: Package) -> None: ...


@final
class Shelving:
    """Packages that save every file under its relative path and queue the build in one
    transaction, so the folders of the package stay as the customer made them."""

    __slots__ = ("_jobs", "_layout", "_sessions", "_storage")

    def __init__(self, sessions: Sessions, jobs: Jobs, storage: Storage, layout: Layout) -> None:
        self._sessions: Final = sessions
        self._jobs: Final = jobs
        self._storage: Final = storage
        self._layout: Final = layout

    async def receive(self, files: tuple[Stored, ...], group: str) -> Registered:
        keys: list[str] = []
        async with self._sessions.session() as session:
            policy = Policy(access_group=group, number="", insured="")
            session.add(policy)
            await session.flush()
            try:
                for file in files:
                    key = self._layout.document(policy.id, file.name())
                    self._storage.save(key, file.data())
                    keys.append(key)
                    session.add(PolicyDocument(policy_id=policy.id, kind="file", file_key=key))
                policy.job_id = await self._jobs.add(
                    session, "profile_build", {"policy_id": policy.id}
                )
                await session.commit()
            except Exception:
                for key in keys:
                    self._storage.remove(key)
                raise
            return Registered(policy.id, policy.job_id)

    async def rebuild(self, policy_id: int) -> int:
        async with self._sessions.session() as session:
            policy = await session.get(Policy, policy_id)
            if policy is None:
                raise LookupError(f"Полис {policy_id} не найден")
            policy.job_id = await self._jobs.add(session, "profile_build", {"policy_id": policy_id})
            await session.commit()
            return policy.job_id

    async def classify(self, policy_id: int, package: Package) -> None:
        async with self._sessions.session() as session:
            rows = (
                await session.scalars(
                    select(PolicyDocument).where(PolicyDocument.policy_id == policy_id)
                )
            ).all()
            by_key = {row.file_key: row for row in rows}
            policy = by_key.get(self._layout.document(policy_id, package.policy().reference()))
            if policy is not None:
                policy.kind = "policy"
            for amendment in package.amendments():
                row = by_key.get(self._layout.document(policy_id, amendment.reference()))
                if row is not None:
                    row.kind = "amendment"
                    row.addendum_number = str(amendment.number())
                    row.effective_from = amendment.effective()
                    row.applies_to = list(amendment.scope())
            await session.commit()
