import asyncio
from contextvars import ContextVar
from typing import Final, final

from app.jobs.database import Sessions
from app.jobs.ledger import Booked
from app.llm.assembly import Assembly
from app.llm.ledger import Call
from app.llm.model import Model

_JOB: ContextVar[int] = ContextVar("job", default=0)


@final
class Tracked:
    """Ledger that books a call under the job that the calling thread works for."""

    __slots__ = ("_loop", "_sessions", "_timeout")

    def __init__(self, sessions: Sessions, loop: asyncio.AbstractEventLoop, timeout: float) -> None:
        self._sessions: Final = sessions
        self._loop: Final = loop
        self._timeout: Final = timeout

    def record(self, call: Call) -> None:
        Booked(self._sessions, self._loop, _JOB.get(), self._timeout).record(call)


@final
class Gateway:
    """Models of the process: one assembly, so one limit of parallel calls for all jobs.

    The model is built when a stage asks for it, so a process whose settings lack a gateway
    still reconciles, and a build job fails with the message about the missing setting.
    """

    __slots__ = ("_assembly",)

    def __init__(self, assembly: Assembly) -> None:
        self._assembly: Final = assembly

    def model(self, job_id: int) -> Model:
        _JOB.set(job_id)
        return self._assembly.model()
