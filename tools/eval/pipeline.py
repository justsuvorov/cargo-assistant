from typing import Final, Protocol, final

from app.domain.reason import Cause
from app.domain.remark import Note
from app.domain.status import Status
from app.domain.verdict import Ruling, Verdict
from tools.eval.gold import Gold


class Outcome(Protocol):
    """Verdicts a pipeline produced for one declaration and the model calls it spent on them."""

    def verdicts(self) -> tuple[Verdict, ...]: ...

    def calls(self) -> int: ...


class Pipeline(Protocol):
    """Reconciliation of one gold declaration, the boundary that eval measures."""

    def reconcile(self, declaration: str) -> Outcome: ...


@final
class Result:
    """Outcome assembled from ready verdicts and a count of model calls."""

    __slots__ = ("_calls", "_verdicts")

    def __init__(self, verdicts: tuple[Verdict, ...], calls: int) -> None:
        self._verdicts: Final = verdicts
        self._calls: Final = calls

    def verdicts(self) -> tuple[Verdict, ...]:
        return self._verdicts

    def calls(self) -> int:
        return self._calls


@final
class Uniform:
    """Stub pipeline that gives one status in every gold place and never calls the model."""

    __slots__ = ("_gold", "_status")

    def __init__(self, gold: Gold, status: Status) -> None:
        self._gold: Final = gold
        self._status: Final = status

    def reconcile(self, declaration: str) -> Outcome:
        return Result(
            tuple(
                Ruling(
                    sample.place(),
                    self._status,
                    Cause("eval.stub", "rule"),
                    Note("Заглушка конвейера", ""),
                )
                for sample in self._gold.samples()
                if sample.declaration() == declaration
            ),
            0,
        )
