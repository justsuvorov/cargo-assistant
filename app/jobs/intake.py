from dataclasses import dataclass
from typing import Final, Protocol, final

from app.core.clock import Clock
from app.jobs.database import Sessions
from app.jobs.models import Declaration
from app.jobs.queue import Jobs
from app.storage.disk import Storage
from app.storage.layout import Layout


@final
@dataclass(frozen=True)
class Receipt:
    """Identifiers of the declaration and the job created for an uploaded file."""

    declaration_id: int
    job_id: int


class Reception(Protocol):
    """Place where an uploaded declaration file turns into a stored file and a queued job."""

    async def receive(self, name: str, data: bytes, group: str) -> Receipt: ...


@final
class Intake:
    """Reception that saves the file and queues the reconcile job in one transaction."""

    __slots__ = ("_clock", "_jobs", "_layout", "_sessions", "_storage")

    def __init__(
        self, sessions: Sessions, jobs: Jobs, storage: Storage, layout: Layout, clock: Clock
    ) -> None:
        self._sessions: Final = sessions
        self._jobs: Final = jobs
        self._storage: Final = storage
        self._layout: Final = layout
        self._clock: Final = clock

    async def receive(self, name: str, data: bytes, group: str) -> Receipt:
        async with self._sessions.session() as session:
            declaration = Declaration(
                access_group=group, file_name=name, created_at=self._clock.now()
            )
            session.add(declaration)
            await session.flush()
            key = self._layout.source(declaration.id, name)
            self._storage.save(key, data)
            try:
                declaration.file_key = key
                declaration.job_id = await self._jobs.add(
                    session, "reconcile", {"declaration_id": declaration.id}
                )
                await session.commit()
            except Exception:
                self._storage.remove(key)
                raise
            return Receipt(declaration.id, declaration.job_id)
