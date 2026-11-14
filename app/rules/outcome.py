from collections.abc import Mapping
from typing import Final, Protocol, final

from app.domain.clause import Clause
from app.domain.place import Place
from app.domain.reason import Cause
from app.domain.remark import Note
from app.domain.semantics import Inquiry, Question
from app.domain.status import Review, Status
from app.domain.verdict import Ruling, Verdict
from app.rules.answers import Answers
from app.rules.wording import Wording

_RANK = {"match": 0, "review": 1, "mismatch": 2}


class Outcome(Protocol):
    """Result of one check of one field in one shipment, before it is placed and worded."""

    def questions(self, place: Place) -> tuple[Question, ...]: ...

    def verdict(self, place: Place, wording: Wording, answers: Answers) -> Verdict: ...


@final
class Finding:
    """Outcome decided by code: a status, the outcome name for the reason code and the values
    that fill the comment template of the outcome or, failing that, of the status."""

    __slots__ = ("_name", "_status", "_values")

    def __init__(self, status: Status, name: str, values: Mapping[str, str]) -> None:
        self._status: Final = status
        self._name: Final = name
        self._values: Final = values

    def questions(self, _place: Place) -> tuple[Question, ...]:
        return ()

    def verdict(self, place: Place, wording: Wording, _answers: Answers) -> Verdict:
        return Ruling(
            place,
            self._status,
            Cause(f"{place.field()}.{self._name}", "rule"),
            wording.remark((self._name, self._status.key()), self._values),
        )


@final
class Gap:
    """Outcome of a check whose policy clause is not in the profile: it needs a person."""

    __slots__ = ("_clause",)

    def __init__(self, clause: Clause) -> None:
        self._clause: Final = clause

    def questions(self, _place: Place) -> tuple[Question, ...]:
        return ()

    def verdict(self, place: Place, _wording: Wording, _answers: Answers) -> Verdict:
        return Ruling(
            place,
            Review(),
            Cause("clause.absent", "rule"),
            Note(self._clause.reference(), self._clause.reference()),
        )


@final
class Doubt:
    """Outcome of a check whose policy clause cannot be chosen: it needs a person, and the
    reason stands in place of the reference to a clause."""

    __slots__ = ("_reason",)

    def __init__(self, reason: str) -> None:
        self._reason: Final = reason

    def questions(self, _place: Place) -> tuple[Question, ...]:
        return ()

    def verdict(self, place: Place, _wording: Wording, _answers: Answers) -> Verdict:
        return Ruling(
            place,
            Review(),
            Cause("clause.unsettled", "rule"),
            Note(self._reason, self._reason),
        )


@final
class Severed:
    """Outcome of a check whose declaration is bound to no policy: it needs a person, the code
    is policy.<reason> and the card words the comment by the reason code of the binding."""

    __slots__ = ("_reason",)

    def __init__(self, reason: str) -> None:
        self._reason: Final = reason

    def questions(self, _place: Place) -> tuple[Question, ...]:
        return ()

    def verdict(self, place: Place, wording: Wording, _answers: Answers) -> Verdict:
        return Ruling(
            place,
            Review(),
            Cause(f"policy.{self._reason.removeprefix('policy_')}", "rule"),
            wording.remark((self._reason, "review"), {}),
        )


@final
class Pending:
    """Outcome that a semantic judge decides: a question now, its answer when it comes."""

    __slots__ = ("_clause", "_rule", "_value")

    def __init__(self, value: str, clause: Clause, rule: str) -> None:
        self._value: Final = value
        self._clause: Final = clause
        self._rule: Final = rule

    def questions(self, place: Place) -> tuple[Question, ...]:
        return (Inquiry(place, self._value, self._clause, self._rule),)

    def verdict(self, place: Place, wording: Wording, answers: Answers) -> Verdict:
        replies = answers.reply(Inquiry(place, self._value, self._clause, self._rule))
        return next(
            (Ruling(place, reply.status(), reply.reason(), reply.remark()) for reply in replies),
            Finding(
                Review(),
                "unanswered",
                {"reference": self._clause.reference(), "entry": self._value},
            ).verdict(place, wording, answers),
        )


@final
class Worst:
    """Outcome of a field of several items or parts: the worst verdict among them, where
    mismatch is worse than review and review is worse than match."""

    __slots__ = ("_outcomes",)

    def __init__(self, outcomes: tuple[Outcome, ...]) -> None:
        self._outcomes: Final = outcomes

    def questions(self, place: Place) -> tuple[Question, ...]:
        return tuple(
            question for outcome in self._outcomes for question in outcome.questions(place)
        )

    def verdict(self, place: Place, wording: Wording, answers: Answers) -> Verdict:
        return max(
            (outcome.verdict(place, wording, answers) for outcome in self._outcomes),
            key=lambda verdict: _RANK[verdict.status().key()],
        )
