from dataclasses import dataclass
from datetime import date, datetime
from typing import Final, Protocol, final

from sqlalchemy import select

from app.core.clock import Clock
from app.domain.policy import Policy as Reference
from app.jobs.database import Sessions
from app.jobs.errors import MissingProfileError, NotReadyError, WaitingError
from app.jobs.models import Policy, PolicyProfile
from app.jobs.queue import Jobs
from app.policy.approved import Approved
from app.policy.schema.profile import Profile


@final
@dataclass(frozen=True)
class Version:
    """One saved version of a profile with its status and who approved it and when."""

    number: int
    status: str
    profile: Profile
    approved_by: str
    approved_at: datetime | None


@final
class Gaps:
    """Requisites of a profile that an expert has to fill in before approving it."""

    __slots__ = ("_profile",)

    def __init__(self, profile: Profile) -> None:
        self._profile: Final = profile

    def names(self) -> tuple[str, ...]:
        profile = self._profile
        return tuple(
            name
            for name, empty in (
                ("номер полиса", not profile.number.strip()),
                ("дата выдачи", profile.issued == date.min),
                ("страхователь", not profile.insurer.strip()),
            )
            if empty
        )


class Folio(Protocol):
    """Versions of the profile of every policy: drafts, expert edits and the approved one."""

    async def draft(self, policy_id: int, profile: Profile) -> int: ...

    async def latest(self, policy_id: int) -> Version: ...

    async def approve(self, policy_id: int, version: int, who: str) -> None: ...

    async def approved(self, policy_id: int) -> Reference: ...


@final
class Folios:
    """Folio in the database. A draft or an edit is always a new version; the one in force for
    reconciliation is the latest approved version, so a new draft does not take it away."""

    __slots__ = ("_clock", "_jobs", "_sessions")

    def __init__(self, sessions: Sessions, jobs: Jobs, clock: Clock) -> None:
        self._sessions: Final = sessions
        self._jobs: Final = jobs
        self._clock: Final = clock

    async def draft(self, policy_id: int, profile: Profile) -> int:
        async with self._sessions.session() as session:
            policy = await session.get(Policy, policy_id)
            if policy is None:
                raise MissingProfileError(f"Полис {policy_id} не найден")
            last = await session.scalar(
                select(PolicyProfile.version)
                .where(PolicyProfile.policy_id == policy_id)
                .order_by(PolicyProfile.version.desc())
                .limit(1)
            )
            number = (last or 0) + 1
            session.add(
                PolicyProfile(
                    policy_id=policy_id,
                    version=number,
                    body=profile.model_dump(mode="json"),
                    status="draft",
                )
            )
            policy.number = profile.number[:64] or policy.number
            policy.insured = profile.insurer[:255] or policy.insured
            await session.commit()
            return number

    async def latest(self, policy_id: int) -> Version:
        async with self._sessions.session() as session:
            row = await session.scalar(
                select(PolicyProfile)
                .where(PolicyProfile.policy_id == policy_id)
                .order_by(PolicyProfile.version.desc())
                .limit(1)
            )
        if row is None:
            raise MissingProfileError(f"У полиса {policy_id} ещё нет профиля")
        return self._version(row)

    async def approve(self, policy_id: int, version: int, who: str) -> None:
        async with self._sessions.session() as session:
            rows = (
                await session.scalars(
                    select(PolicyProfile)
                    .where(PolicyProfile.policy_id == policy_id)
                    .order_by(PolicyProfile.version.desc())
                )
            ).all()
            if not rows:
                raise MissingProfileError(f"У полиса {policy_id} ещё нет профиля")
            current = rows[0]
            if current.version != version:
                raise NotReadyError(
                    "Профиль изменён после открытия страницы, обновите её и проверьте снова"
                )
            gaps = Gaps(Profile.model_validate(current.body)).names()
            if gaps:
                raise NotReadyError(f"Подтвердить нельзя, не заполнено: {', '.join(gaps)}")
            for row in rows[1:]:
                if row.status == "approved":
                    row.status = "replaced"
            current.status = "approved"
            current.approved_by = who
            current.approved_at = self._clock.now()
            await session.commit()
        await self._jobs.release(policy_id)

    async def approved(self, policy_id: int) -> Reference:
        async with self._sessions.session() as session:
            row = await session.scalar(
                select(PolicyProfile)
                .where(PolicyProfile.policy_id == policy_id, PolicyProfile.status == "approved")
                .order_by(PolicyProfile.version.desc())
                .limit(1)
            )
        if row is None:
            raise WaitingError("Ожидает профиль полиса")
        return Approved(self._version(row).profile)

    def _version(self, row: PolicyProfile) -> Version:
        return Version(
            row.version,
            row.status,
            Profile.model_validate(row.body),
            row.approved_by,
            row.approved_at,
        )
