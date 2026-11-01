from typing import Final, Protocol, final

from app.declarations.declared import Declared
from app.domain.errors import UnreadableError
from app.domain.place import Spot
from app.domain.reason import Cause
from app.domain.remark import Note
from app.domain.status import Review, Status
from app.domain.verdict import Ruling, Verdict
from app.ingest.source import Source
from tools.eval.fields import Forms
from tools.eval.gold import Gold
from tools.eval.shelf import AbsentError, Library


class Outcome(Protocol):
    """Verdicts a pipeline produced for one declaration, its model calls and what went wrong."""

    def verdicts(self) -> tuple[Verdict, ...]: ...

    def calls(self) -> int: ...

    def faults(self) -> tuple[str, ...]: ...


class Pipeline(Protocol):
    """Reconciliation of one gold declaration, the boundary that eval measures."""

    def reconcile(self, declaration: str) -> Outcome: ...


@final
class Result:
    """Outcome assembled from ready verdicts, a count of model calls and the faults met."""

    __slots__ = ("_calls", "_faults", "_verdicts")

    def __init__(self, verdicts: tuple[Verdict, ...], calls: int, faults: tuple[str, ...]) -> None:
        self._verdicts: Final = verdicts
        self._calls: Final = calls
        self._faults: Final = faults

    def verdicts(self) -> tuple[Verdict, ...]:
        return self._verdicts

    def calls(self) -> int:
        return self._calls

    def faults(self) -> tuple[str, ...]:
        return self._faults


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
            (),
        )


@final
class Parsed:
    """Pipeline that reads the declaration file with the real parser and answers each place.

    Every shipment row of the file gets a «требует проверки» stub in each field of its form,
    so a run shows which gold places the parser finds and which it misses. The pipeline never
    sees the gold.
    """

    __slots__ = ("_forms", "_library")

    def __init__(self, library: Library, forms: Forms) -> None:
        self._library: Final = library
        self._forms: Final = forms

    def reconcile(self, declaration: str) -> Outcome:
        # @todo #5:60min Заменить заглушку настоящими проверками карточек после T-08
        try:
            read = Declared(Source(self._library.path(declaration)))
            keys = tuple(key for key, _ in self._forms.fields(read.form()))
            verdicts = tuple(
                Ruling(
                    Spot(shipment.number(), key),
                    Review(),
                    Cause("eval.parsed", "rule"),
                    Note(
                        f"Заглушка разбора: поле {'заполнено' if field.filled() else 'пусто'}", ""
                    ),
                )
                for shipment in read.shipments()
                for key in keys
                for field in (shipment.field(key),)
            )
        except (AbsentError, UnreadableError) as error:
            return Result((), 0, (str(error),))
        return Result(verdicts, 0, ())
