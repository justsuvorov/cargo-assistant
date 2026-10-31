import asyncio
from typing import Final, final

from app.jobs.database import Sessions
from app.jobs.models import LLMCall
from app.llm.ledger import Call


@final
class Booked:
    """Ledger that writes every call of one job into the llm_calls table. The model client is
    synchronous and runs in a worker thread, so each write is handed to the event loop that owns
    the database and awaited with a timeout; a failed write raises into the calling stage."""

    __slots__ = ("_job", "_loop", "_sessions", "_timeout")

    def __init__(
        self,
        sessions: Sessions,
        loop: asyncio.AbstractEventLoop,
        job: int,
        timeout: float,
    ) -> None:
        self._sessions: Final = sessions
        self._loop: Final = loop
        self._job: Final = job
        self._timeout: Final = timeout

    def record(self, call: Call) -> None:
        asyncio.run_coroutine_threadsafe(self._write(call), self._loop).result(self._timeout)

    async def _write(self, call: Call) -> None:
        spent = call.outcome().spent()
        async with self._sessions.session() as session:
            session.add(
                LLMCall(
                    job_id=self._job,
                    purpose=call.purpose(),
                    provider=call.origin().provider(),
                    model=call.origin().model(),
                    prompt_hash=call.digest(),
                    tokens_in=spent[0],
                    tokens_out=spent[1],
                    latency=call.outcome().latency(),
                    valid=call.outcome().valid(),
                )
            )
            await session.commit()
