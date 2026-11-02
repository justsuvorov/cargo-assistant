from typing import Final, Protocol, final

from app.domain.reason import Cause
from app.domain.remark import Note
from app.domain.semantics import Question
from app.domain.status import Review
from app.domain.verdict import Ruling, Verdict


class Counted(Protocol):
    """Semantic judge that knows how many batches of questions it was asked."""

    def count(self) -> int: ...


@final
class Doubt:
    """Semantic judge of eval runs without a model: every question needs a person.

    Each batch of questions counts as one model call, the way the real judge would ask the
    model once per card and declaration; no network and no model is touched.
    """

    __slots__ = ("_batches",)

    def __init__(self) -> None:
        self._batches: Final[list[int]] = []

    def verdicts(self, questions: tuple[Question, ...]) -> tuple[Verdict, ...]:
        self._batches.append(len(questions))
        return tuple(
            Ruling(
                question.place(),
                Review(),
                Cause("eval.semantic", "llm"),
                Note("Смысловая проверка в eval не выполнялась", question.clause().reference()),
            )
            for question in questions
        )

    def count(self) -> int:
        return len(self._batches)
