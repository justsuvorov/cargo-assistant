import time
from typing import Final, Protocol, final

from app.domain.verdict import Verdict
from tools.eval.gold import Gold
from tools.eval.pipeline import Outcome, Pipeline, Result


class Lap(Protocol):
    """One gold declaration passed through a pipeline, with the wall time it took."""

    def declaration(self) -> str: ...

    def seconds(self) -> float: ...

    def calls(self) -> int: ...

    def verdicts(self) -> tuple[Verdict, ...]: ...


class Laps(Protocol):
    """Run of a pipeline over every declaration of the gold."""

    def laps(self) -> tuple[Lap, ...]: ...


@final
class Timed:
    """Lap that keeps the outcome of a pipeline and the seconds measured around it."""

    __slots__ = ("_declaration", "_outcome", "_seconds")

    def __init__(self, declaration: str, outcome: Outcome, seconds: float) -> None:
        self._declaration: Final = declaration
        self._outcome: Final = outcome
        self._seconds: Final = seconds

    def declaration(self) -> str:
        return self._declaration

    def seconds(self) -> float:
        return self._seconds

    def calls(self) -> int:
        return self._outcome.calls()

    def verdicts(self) -> tuple[Verdict, ...]:
        return self._outcome.verdicts()


@final
class Session:
    """Run that reconciles gold declarations one by one in the order they appear in the gold."""

    __slots__ = ("_gold", "_pipeline")

    def __init__(self, gold: Gold, pipeline: Pipeline) -> None:
        self._gold: Final = gold
        self._pipeline: Final = pipeline

    def laps(self) -> tuple[Lap, ...]:
        return tuple(
            self._lap(declaration)
            for declaration in dict.fromkeys(
                sample.declaration() for sample in self._gold.samples()
            )
        )

    def _lap(self, declaration: str) -> Lap:
        start = time.perf_counter()
        outcome = self._pipeline.reconcile(declaration)
        result = Result(outcome.verdicts(), outcome.calls())
        return Timed(declaration, result, time.perf_counter() - start)
