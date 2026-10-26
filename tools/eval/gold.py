import csv
import io
from pathlib import Path
from typing import Final, Protocol, final

from app.domain.gold import Expectation, GoldCase
from app.domain.place import Place, Spot
from app.domain.status import Match, Mismatch, Review, Status
from app.domain.verdict import Verdict


class Sample(GoldCase, Protocol):
    """Gold case together with the declaration it belongs to and the status it expects."""

    def declaration(self) -> str: ...

    def status(self) -> Status: ...


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


@final
class Case:
    """Gold line that expects one status in one shipment row and field of a declaration."""

    __slots__ = ("_declaration", "_place", "_status")

    def __init__(self, declaration: str, place: Place, status: Status) -> None:
        self._declaration: Final = declaration
        self._place: Final = place
        self._status: Final = status

    def place(self) -> Place:
        return self._place

    def agrees(self, verdict: Verdict) -> bool:
        return Expectation(self._place, self._status).agrees(verdict)

    def declaration(self) -> str:
        return self._declaration

    def status(self) -> Status:
        return self._status


@final
class Folder:
    """Gold kept as CSV files, one per declaration, with a header row of column names."""

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
                Spot(row["shipment"], row["field"]),
                Scale().status(row["status"]),
            )
            for path in files
            for row in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8")))
        )
