from typing import Final, Protocol, final

from sqlalchemy import delete

from app.jobs.database import Sessions
from app.jobs.models import Policy, PolicyDocument
from app.jobs.queue import Jobs
from app.policy.package import Package
from app.storage.relative import Relative


class Packages(Protocol):
    """Place where the package of a policy is found in the storage, built again and described."""

    async def prefix(self, policy_id: int) -> str: ...

    async def rebuild(self, policy_id: int) -> int: ...

    async def classify(self, policy_id: int, package: Package) -> None: ...


@final
class Shelving:
    """Packages kept in the database: the folder of a policy is the folder of the session that
    brought its files, and the documents of the package are told apart after it is read."""

    __slots__ = ("_jobs", "_sessions")

    def __init__(self, sessions: Sessions, jobs: Jobs) -> None:
        self._sessions: Final = sessions
        self._jobs: Final = jobs

    async def prefix(self, policy_id: int) -> str:
        async with self._sessions.session() as session:
            policy = await session.get(Policy, policy_id)
        if policy is None or not policy.package_key:
            raise LookupError(f"У полиса {policy_id} нет папки с файлами")
        return policy.package_key

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
            policy = await session.get(Policy, policy_id)
            if policy is None:
                raise LookupError(f"Полис {policy_id} не найден")
            await session.execute(
                delete(PolicyDocument).where(PolicyDocument.policy_id == policy_id)
            )
            session.add(
                PolicyDocument(
                    policy_id=policy_id,
                    kind="policy",
                    file_key=f"{policy.package_key}/{Relative(package.policy().reference()).path()}",
                )
            )
            session.add_all(
                PolicyDocument(
                    policy_id=policy_id,
                    kind="amendment",
                    file_key=f"{policy.package_key}/{Relative(amendment.reference()).path()}",
                    addendum_number=str(amendment.number()),
                    effective_from=amendment.effective(),
                    applies_to=list(amendment.scope()),
                )
                for amendment in package.amendments()
            )
            await session.commit()
