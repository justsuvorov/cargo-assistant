from typing import Final, final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.errors import LostError
from app.jobs.models import Job
from app.jobs.queue import Snapshot


@final
class Holding:
    """Check, inside the transaction that is about to write, that the attempt of the snapshot
    still owns the job: it is running and nobody has claimed it again since."""

    __slots__ = ("_session",)

    def __init__(self, session: AsyncSession) -> None:
        self._session: Final = session

    async def owned(self, job: Snapshot) -> None:
        row = await self._session.scalar(
            select(Job)
            .where(Job.id == job.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None or row.status != "running" or row.attempts != job.attempts:
            raise LostError(f"Попытка {job.attempts} задачи {job.id} больше не владеет задачей")
