import csv
import io
from pathlib import Path
from typing import Final, Protocol, final

from app.domain.gold import Expectation, GoldCase
from app.domain.place import Place, Spot
from app.domain.status import Match, Mismatch, Review, Status
from app.domain.verdict import Verdict
from tools.eval.number import Aligned, Canonical


class Sample(GoldCase, Protocol):
    """Gold case together with the declaration it belongs to and the status it expects."""

    def declaration(self) -> str: ...

    def status(self) -> Status: ...

    def sure(self) -> bool: ...


class Gold(Protocol):
    """Set of gold cases that a pipeline run is compared with."""

    def samples(self) -> tuple[Sample, ...]: ...


class Statuses(Protocol):
    """Lookup of a result status by its key."""

    def status(self, key: str) -> Status: ...


@final
class Scale:
    """The three statuses of the result: match, mismatch and review."""

    __slots__ = ()

    def status(self, key: str) -> Status:
        found = tuple(status for status in (Match(), Mismatch(), Review()) if status.key() == key)
        if not found:
            raise ValueError(f"Статус «{key}» не входит в match, mismatch, review")
        return found[0]


class Assurance(Protocol):
    """Lookup of whether a confidence key of a gold line counts in the accuracy."""

    def sure(self, key: str) -> bool: ...


@final
class Confidence:
    """Confidence of the expert in a gold line: sure lines are scored, disputed ones are not."""

    __slots__ = ()

    def sure(self, key: str) -> bool:
        keys = {"sure": True, "disputed": False}
        if key not in keys:
            raise ValueError(f"Уверенность «{key}» не входит в sure, disputed")
        return keys[key]


@final
class Case:
    """Gold line that expects one status in one shipment row and field of a declaration."""

    __slots__ = ("_declaration", "_place", "_status", "_sure")

    def __init__(self, declaration: str, place: Place, status: Status, *, sure: bool) -> None:
        self._declaration: Final = declaration
        self._place: Final = place
        self._status: Final = status
        self._sure: Final = sure

    def place(self) -> Place:
        return self._place

    def agrees(self, verdict: Verdict) -> bool:
        return Expectation(self._place, self._status).agrees(Aligned(verdict))

    def declaration(self) -> str:
        return self._declaration

    def status(self) -> Status:
        return self._status

    def sure(self) -> bool:
        return self._sure


@final
class Folder:
    """Gold kept as CSV files, one per declaration, with a header row of column names.

    The confidence column is optional: a file of the first draft without it holds sure lines.
    """

    __slots__ = ("_path",)

    def __init__(self, path: Path) -> None:
        self._path: Final = path

    def samples(self) -> tuple[Sample, ...]:
        files = sorted(self._path.glob("*.csv"))
        if not files:
            raise FileNotFoundError(f"В папке эталона {self._path} нет файлов csv")
        return tuple(
            Case(
                row["declaration"],
                Canonical(Spot(row["shipment"], row["field"])),
                Scale().status(row["status"]),
                sure=Confidence().sure(row.get("confidence") or "sure"),
            )
            for path in files
            for row in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8")))
        )


@final
class Held:
    """Gold read once and kept in memory, so that a run does not read its files again."""

    __slots__ = ("_samples",)

    def __init__(self, samples: tuple[Sample, ...]) -> None:
        self._samples: Final = samples

    def samples(self) -> tuple[Sample, ...]:
        return self._samples
