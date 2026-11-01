from typing import Final, Protocol, final

from app.domain.semantics import Question
from app.domain.verdict import Verdict


class Batch(Protocol):
    """Questions of one card and one declaration, each asked once."""

    def questions(self) -> tuple[Question, ...]: ...


class Answers(Protocol):
    """Verdicts that a semantic judge gave to a batch, found again by question."""

    def reply(self, question: Question) -> tuple[Verdict, ...]: ...


def _identity(question: Question) -> tuple[str, ...]:
    clause = question.clause()
    return (question.value(), clause.text(), clause.reference(), question.rule())


@final
class Distinct:
    """Batch that keeps the first of the questions with the same value, clause and rule."""

    __slots__ = ("_questions",)

    def __init__(self, questions: tuple[Question, ...]) -> None:
        self._questions: Final = questions

    def questions(self) -> tuple[Question, ...]:
        first: dict[tuple[str, ...], Question] = {}
        for question in self._questions:
            first.setdefault(_identity(question), question)
        return tuple(first.values())


@final
class Replies:
    """Answers to distinct questions: a question gets the verdict placed at its first twin."""

    __slots__ = ("_questions", "_verdicts")

    def __init__(self, questions: tuple[Question, ...], verdicts: tuple[Verdict, ...]) -> None:
        self._questions: Final = questions
        self._verdicts: Final = verdicts

    def reply(self, question: Question) -> tuple[Verdict, ...]:
        twins = tuple(each for each in self._questions if _identity(each) == _identity(question))
        return tuple(
            verdict
            for twin in twins[:1]
            for verdict in self._verdicts
            if verdict.place().same(twin.place())
        )[:1]
