from collections.abc import Mapping
from datetime import date

from app.declarations.declared import Numbered
from app.declarations.fields import Dating
from app.declarations.row import Row
from app.declarations.schema import Fields
from app.domain.clause import Absent, Clause
from app.domain.errors import UnreadableError
from app.domain.money import Money
from app.domain.reason import Cause
from app.domain.remark import Note
from app.domain.semantics import Question
from app.domain.shipment import Shipment
from app.domain.status import Status
from app.domain.verdict import Ruling, Verdict


class Text:
    """Policy clause with a fixed text, reference, dates, sums and items."""

    def __init__(
        self,
        reference: str,
        text: str = "",
        dates: tuple[date, ...] = (),
        amounts: tuple[Money, ...] = (),
        entries: tuple[str, ...] = (),
    ) -> None:
        self._reference = reference
        self._text = text
        self._dates = dates
        self._amounts = amounts
        self._entries = entries

    def reference(self) -> str:
        return self._reference

    def text(self) -> str:
        return self._text

    def dates(self) -> tuple[date, ...]:
        return self._dates

    def amounts(self) -> tuple[Money, ...]:
        return self._amounts

    def entries(self) -> tuple[str, ...]:
        return self._entries


class Profile:
    """Policy whose clauses do not depend on the shipment; a missing key is Absent."""

    def __init__(self, clauses: Mapping[str, Clause], conditions: tuple[str, ...] = ()) -> None:
        self._clauses = clauses
        self._conditions = conditions

    def number(self) -> str:
        return "0000"

    def clause(self, key: str, _shipment: Shipment) -> Clause:
        return self._clauses.get(key, Absent(key))

    def conditions(self) -> tuple[str, ...]:
        return self._conditions


class Doubtful:
    """Policy that cannot choose a revision of any clause and says why."""

    def __init__(self, reason: str) -> None:
        self._reason = reason

    def number(self) -> str:
        return "0000"

    def clause(self, _key: str, _shipment: Shipment) -> Clause:
        raise UnreadableError(self._reason)

    def conditions(self) -> tuple[str, ...]:
        return ()


class Unsettled:
    """Policy that cannot choose a revision of one clause and has no other clauses."""

    def __init__(self, key: str, reason: str) -> None:
        self._key = key
        self._reason = reason

    def number(self) -> str:
        return "0000"

    def clause(self, key: str, _shipment: Shipment) -> Clause:
        if key == self._key:
            raise UnreadableError(self._reason)
        return Absent(key)

    def conditions(self) -> tuple[str, ...]:
        return ()


class Listening:
    """Policy without clauses that remembers every key it was asked."""

    def __init__(self) -> None:
        self.keys: list[str] = []

    def number(self) -> str:
        return "0000"

    def clause(self, key: str, _shipment: Shipment) -> Clause:
        self.keys.append(key)
        return Absent(key)

    def conditions(self) -> tuple[str, ...]:
        return ()


class Paper:
    """Declaration of a form whose rows are cell texts per field key, read by the parser."""

    def __init__(
        self, number: str, form: str, rows: tuple[Mapping[str, tuple[str, ...]], ...]
    ) -> None:
        self._number = number
        self._form = form
        self._rows = rows

    def number(self) -> str:
        return self._number

    def form(self) -> str:
        return self._form

    def policy(self) -> str:
        return "0000"

    def shipments(self) -> tuple[Shipment, ...]:
        return tuple(
            Numbered(
                self._number,
                len(self._rows),
                Row(
                    str(index),
                    texts,
                    Fields(),
                    Dating(texts.get("period", texts.get("period_start", ()))[:1]),
                ),
            )
            for index, texts in enumerate(self._rows, start=1)
        )


class Oracle:
    """Semantic judge that gives one status to every question and remembers each batch."""

    def __init__(self, status: Status) -> None:
        self._status = status
        self.batches: list[tuple[Question, ...]] = []

    def verdicts(self, questions: tuple[Question, ...]) -> tuple[Verdict, ...]:
        self.batches.append(questions)
        return tuple(
            Ruling(
                question.place(),
                self._status,
                Cause(f"{question.place().field()}.judged", "llm"),
                Note(f"оценено: {question.value()}", question.clause().reference()),
            )
            for question in questions
        )


class Mute:
    """Semantic judge that fails a test as soon as anyone asks it."""

    def verdicts(self, questions: tuple[Question, ...]) -> tuple[Verdict, ...]:
        raise AssertionError(f"Смысловой проверке задали {len(questions)} вопросов")
