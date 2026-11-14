import asyncio
import hashlib
import shutil
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Final, Protocol, final

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock
from app.core.journal import Journal
from app.jobs.building import Bench
from app.jobs.clients import Clients, Kept
from app.jobs.database import Sessions
from app.jobs.errors import ChoiceError, MissingWorkspaceError
from app.jobs.inventory import Inventory
from app.jobs.models import Declaration, Job, Policy, PolicyProfile, Workspace
from app.jobs.queue import Jobs
from app.storage.archive import Stored
from app.storage.disk import Storage
from app.storage.layout import Layout


@final
@dataclass(frozen=True)
class Surveyed:
    """What a look at the stored folder gives: the declarations in it and the signature of the
    files of the policy."""

    declarations: tuple[str, ...]
    signature: str
    conditions: Kept


class Workspaces(Protocol):
    """Sessions of users: the folder a user opens and the declarations the user starts."""

    async def open(
        self,
        owner: str,
        who: str,
        name: str,
        files: tuple[Stored, ...],
        special: tuple[Stored, ...] = (),
    ) -> int: ...

    async def start(
        self, owner: str, workspace_id: int, chosen: tuple[str, ...]
    ) -> tuple[int, ...]: ...


@final
class Filing:
    """Workspaces in the database and the storage. Every file lies under the owner and the
    session, and every question about a session carries the owner, so a session of another
    user does not exist for the one who asks.

    The policy of a session is told by the owner and the signature of its files: the same files
    of the same owner are one policy with one profile, built once, and a build that failed is
    queued again by the next session.
    """

    __slots__ = ("_jobs", "_notes", "_parts", "_sessions")

    def __init__(
        self,
        sessions: Sessions,
        jobs: Jobs,
        parts: tuple[Storage, Layout, Bench],
        notes: tuple[Clock, Journal],
    ) -> None:
        self._sessions: Final = sessions
        self._jobs: Final = jobs
        self._parts: Final = parts
        self._notes: Final = notes

    async def open(
        self,
        owner: str,
        who: str,
        name: str,
        files: tuple[Stored, ...],
        special: tuple[Stored, ...] = (),
    ) -> int:
        storage, layout, _ = self._parts
        keys: list[str] = []
        async with self._sessions.session() as session:
            row = Workspace(
                owner=owner,
                owner_name=who[:128],
                name=name[:255],
                found=[],
                package_sha="",
                created_at=self._notes[0].now(),
            )
            session.add(row)
            await session.flush()
            try:
                for file in files:
                    key = layout.entry(owner, row.id, file.name())
                    storage.save(key, file.data())
                    keys.append(key)
                for file in special:
                    key = layout.chosen(owner, row.id, file.name())
                    storage.save(key, file.data())
                    keys.append(key)
                surveyed = await asyncio.to_thread(
                    self._survey, layout.folder(owner, row.id), layout.special(owner, row.id)
                )
                row.found = list(surveyed.declarations)
                row.package_sha = surveyed.signature
                row.client_file = surveyed.conditions.file()
                row.client_chosen = surveyed.conditions.chosen()
                row.client_lines = list(surveyed.conditions.lines())
                row.client_problems = list(surveyed.conditions.problems())
                await session.commit()
            except Exception:
                for key in keys:
                    storage.remove(key)
                raise
            return row.id

    async def start(
        self, owner: str, workspace_id: int, chosen: tuple[str, ...]
    ) -> tuple[int, ...]:
        async with self._sessions.session() as session:
            row = await session.scalar(
                select(Workspace)
                .where(Workspace.id == workspace_id, Workspace.owner == owner)
                .with_for_update()
            )
            if row is None:
                raise MissingWorkspaceError(f"Сессия {workspace_id} не найдена")
            self._checked(row, chosen)
            policy = await self._policy(session, row)
            row.policy_id = policy.id
            await self._built(session, policy, row)
            ids = [await self._declared(session, row, path) for path in chosen]
            row.started_at = self._notes[0].now()
            await session.commit()
            self._notes[1].info(f"Сессия {row.id}: запущено деклараций — {len(ids)}", 0, 0)
            return tuple(ids)

    def _checked(self, row: Workspace, chosen: tuple[str, ...]) -> None:
        if row.started_at is not None:
            raise ChoiceError(f"Сессия {row.id} уже запущена")
        if not chosen:
            raise ChoiceError("Не выбрано ни одной декларации")
        missing = [path for path in chosen if path not in row.found]
        if missing:
            raise ChoiceError(f"В папке нет декларации {missing[0]}")

    def _survey(self, prefix: str, chosen: str) -> Surveyed:
        folder = self._parts[2].unpack(prefix)
        own = self._parts[2].unpack(chosen)
        try:
            inventory = Inventory(folder)
            return Surveyed(
                inventory.declarations(),
                inventory.signature(),
                Kept(Clients(folder, own)),
            )
        finally:
            shutil.rmtree(folder, ignore_errors=True)
            shutil.rmtree(own, ignore_errors=True)

    async def _policy(self, session: AsyncSession, row: Workspace) -> Policy:
        query = select(Policy).where(
            Policy.owner == row.owner, Policy.package_sha == row.package_sha
        )
        found = await session.scalar(query)
        if found is not None:
            return found
        created = Policy(owner=row.owner, package_sha=row.package_sha)
        try:
            async with session.begin_nested():
                session.add(created)
        except IntegrityError:
            return (await session.scalars(query)).one()
        return created

    async def _built(self, session: AsyncSession, policy: Policy, row: Workspace) -> None:
        if await session.scalar(
            select(PolicyProfile.id).where(PolicyProfile.policy_id == policy.id).limit(1)
        ):
            return
        build = await session.get(Job, policy.job_id) if policy.job_id is not None else None
        if build is not None and build.status not in {"done", "failed"}:
            return
        policy.package_key = self._parts[1].folder(row.owner, row.id)
        policy.job_id = await self._jobs.add(session, "profile_build", {"policy_id": policy.id})
        await self._signed(session, policy.job_id, row, "")

    async def _declared(self, session: AsyncSession, row: Workspace, path: str) -> int:
        storage, layout, _ = self._parts
        key = layout.entry(row.owner, row.id, path)
        declaration = Declaration(
            owner=row.owner,
            workspace_id=row.id,
            file_name=PurePosixPath(path).name,
            file_key=key,
            created_at=self._notes[0].now(),
        )
        session.add(declaration)
        await session.flush()
        declaration.job_id = await self._jobs.add(
            session, "reconcile", {"declaration_id": declaration.id}
        )
        await self._signed(
            session, declaration.job_id, row, hashlib.sha256(storage.read(key)).hexdigest()
        )
        self._notes[1].info(
            f"Сессия {row.id}: декларация поставлена в очередь", declaration.job_id, declaration.id
        )
        return declaration.id

    async def _signed(self, session: AsyncSession, job_id: int, row: Workspace, sha: str) -> None:
        job = await session.get(Job, job_id)
        if job is not None:
            job.uploaded_by = row.owner_name
            job.file_sha256 = sha
