import time
from collections.abc import Mapping
from pathlib import Path
from typing import Final, Protocol, final

from app.declarations.declared import Declared
from app.domain.declaration import Declaration
from app.domain.errors import UnreadableError
from app.domain.place import Spot
from app.domain.policy import Vacant
from app.domain.reason import Cause
from app.domain.remark import Note
from app.domain.shipment import Shipment
from app.domain.status import Review, Status
from app.domain.verdict import Ruling, Verdict
from app.ingest.source import Source
from app.rules.cards import Cards
from tools.eval.fields import Forms
from tools.eval.gold import Gold
from tools.eval.semantics import Doubt
from tools.eval.shelf import AbsentError, Library


class Outcome(Protocol):
    """Verdicts a pipeline produced for one declaration, its model calls, what went wrong and
    the seconds of its named stages, if it measures any."""

    def verdicts(self) -> tuple[Verdict, ...]: ...

    def calls(self) -> int: ...

    def faults(self) -> tuple[str, ...]: ...

    def stages(self) -> Mapping[str, float]: ...


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

    def stages(self) -> Mapping[str, float]:
        return {}


@final
class Staged:
    """Outcome of another pipeline together with the seconds of the stages it went through."""

    __slots__ = ("_outcome", "_stages")

    def __init__(self, outcome: Outcome, stages: Mapping[str, float]) -> None:
        self._outcome: Final = outcome
        self._stages: Final = stages

    def verdicts(self) -> tuple[Verdict, ...]:
        return self._outcome.verdicts()

    def calls(self) -> int:
        return self._outcome.calls()

    def faults(self) -> tuple[str, ...]:
        return self._outcome.faults()

    def stages(self) -> Mapping[str, float]:
        return self._stages


@final
class Kept:
    """Declaration whose header and shipment rows were read once and are kept in memory, so
    that every rule card sees the same rows without reading the file again."""

    __slots__ = ("_form", "_number", "_policy", "_shipments")

    def __init__(
        self, number: str, form: str, policy: str, shipments: tuple[Shipment, ...]
    ) -> None:
        self._number: Final = number
        self._form: Final = form
        self._policy: Final = policy
        self._shipments: Final = shipments

    def number(self) -> str:
        return self._number

    def form(self) -> str:
        return self._form

    def policy(self) -> str:
        return self._policy

    def shipments(self) -> tuple[Shipment, ...]:
        return self._shipments


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


@final
class Checked:
    """Pipeline that reads the declaration with the real parser and checks it by the rule cards.

    No policy profile is loaded yet, so every card sees a vacant policy under the number of
    the header and every semantic question goes to the eval stub, which counts each batch as
    one model call. A failure in parsing or in the checks of one declaration becomes a fault of
    its outcome, so that the run goes on. The pipeline never sees the gold.
    """

    __slots__ = ("_folder", "_library")

    def __init__(self, library: Library, folder: Path) -> None:
        self._library: Final = library
        self._folder: Final = folder

    def reconcile(self, declaration: str) -> Outcome:
        start = time.perf_counter()
        try:
            read = Declared(Source(self._library.path(declaration)))
            kept = Kept(read.number(), read.form(), read.policy(), read.shipments())
        except Exception as error:
            return Staged(
                Result((), 0, (f"Разбор ({error.__class__.__name__}): {error}",)),
                {"разбор": time.perf_counter() - start},
            )
        return self._checked(kept, time.perf_counter() - start)

    def _checked(self, declaration: Declaration, parsed: float) -> Outcome:
        judge = Doubt()
        start = time.perf_counter()
        try:
            verdicts = tuple(
                verdict
                for card in Cards(self._folder, judge).cards(declaration.form())
                for verdict in card.verdicts(declaration, Vacant(declaration.policy()))
            )
        except Exception as error:
            return Staged(
                Result((), judge.count(), (f"Проверки ({error.__class__.__name__}): {error}",)),
                {"разбор": parsed, "проверки": time.perf_counter() - start},
            )
        return Staged(
            Result(verdicts, judge.count(), ()),
            {"разбор": parsed, "проверки": time.perf_counter() - start},
        )
