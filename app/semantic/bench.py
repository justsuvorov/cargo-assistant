from concurrent.futures import ThreadPoolExecutor
from typing import Final, Protocol, final

from app.core.journal import Journal
from app.domain.reason import Cause
from app.domain.remark import Note
from app.domain.semantics import Question
from app.domain.status import Match, Mismatch, Review, Status
from app.domain.verdict import Ruling, Verdict
from app.llm.errors import MalformedError, TruncatedError, UnavailableError
from app.llm.model import Model
from app.llm.schema.judgement import Judgement, Judgements
from app.semantic.brief import Brief

_STATUSES: dict[str, Status] = {"match": Match(), "mismatch": Mismatch(), "review": Review()}


def _identity(question: Question) -> tuple[str, ...]:
    return (
        question.place().field(),
        " ".join(question.value().split()).casefold(),
        question.clause().text(),
        question.clause().reference(),
        question.rule(),
    )


def _failure(question: Question, code: str, comment: str) -> Verdict:
    return Ruling(
        question.place(), Review(), Cause(code, "llm"), Note(comment, question.clause().reference())
    )


class Pack(Protocol):
    """Distinct questions of one card that go to the model in one call."""

    def verdicts(self) -> tuple[Verdict, ...]: ...


@final
class Errand:
    """Pack asked in one call to the model: an answer is placed at the question with its
    number, a question without an answer and a failed call give review with their own code;
    the call is written to the journal with its card, number of questions and outcome."""

    __slots__ = ("_journal", "_model", "_questions")

    def __init__(self, model: Model, journal: Journal, questions: tuple[Question, ...]) -> None:
        self._model: Final = model
        self._journal: Final = journal
        self._questions: Final = questions

    def verdicts(self) -> tuple[Verdict, ...]:
        field = self._questions[0].place().field()
        try:
            judgements = self._model.answer(
                f"semantic.{field}", Brief().messages(self._questions), Judgements
            )
        except MalformedError:
            return self._failed(
                field, "llm.invalid_json", "ответ модели не прошёл проверку по схеме"
            )
        except TruncatedError:
            return self._failed(field, "llm.truncated", "ответ модели обрезан по пределу длины")
        except UnavailableError:
            return self._failed(field, "llm.unavailable", "модель не ответила")
        return self._placed(field, judgements)

    def _failed(self, field: str, code: str, comment: str) -> tuple[Verdict, ...]:
        self._note(field, code, len(self._questions))
        return tuple(
            _failure(question, code, f"Смысловая проверка не выполнена: {comment}")
            for question in self._questions
        )

    def _placed(self, field: str, judgements: Judgements) -> tuple[Verdict, ...]:
        found: dict[int, Judgement] = {}
        for judgement in judgements.answers:
            found.setdefault(judgement.id, judgement)
        verdicts = tuple(
            Ruling(
                question.place(),
                _STATUSES[found[index].status],
                Cause(f"{field}.{found[index].status}", "llm"),
                Note(found[index].comment, question.clause().reference()),
            )
            if index in found
            else _failure(question, "llm.unanswered", "Модель не дала ответа по этому значению")
            for index, question in enumerate(self._questions, start=1)
        )
        self._note(
            field,
            "success",
            sum(1 for index in range(1, len(self._questions) + 1) if index not in found),
        )
        return verdicts

    def _note(self, field: str, outcome: str, dropped: int) -> None:
        self._journal.info(
            f"Смысловая проверка поля {field}: вопросов {len(self._questions)}, "
            f"исход {outcome}, без ответа {dropped}",
            0,
            0,
        )


@final
class Bench:
    """Semantic judge on the model gateway: questions are grouped by card, the same value with
    the same clause and rule is asked once and its answer goes to every place; the distinct
    values of a card go in at most the given number of packs of the given size, so the number
    of calls per declaration does not grow with its rows, and values beyond them need a
    person; all packs of all cards are asked in parallel under the semaphore of the model."""

    __slots__ = ("_journal", "_model", "_packs", "_size")

    def __init__(self, model: Model, journal: Journal, packs: int, size: int) -> None:
        self._model: Final = model
        self._journal: Final = journal
        self._packs: Final = packs
        self._size: Final = size

    def verdicts(self, questions: tuple[Question, ...]) -> tuple[Verdict, ...]:
        first: dict[tuple[str, ...], Question] = {}
        for question in questions:
            first.setdefault(_identity(question), question)
        cards: dict[str, list[Question]] = {}
        for question in first.values():
            cards.setdefault(question.place().field(), []).append(question)
        packs = tuple(
            tuple(asked[start : start + self._size])
            for asked in cards.values()
            for start in range(0, min(len(asked), self._packs * self._size), self._size)
        )
        with ThreadPoolExecutor(max_workers=max(1, len(packs))) as pool:
            answered = {
                _identity(question): verdict
                for pack, judged in zip(
                    packs,
                    pool.map(
                        lambda pack: Errand(self._model, self._journal, pack).verdicts(), packs
                    ),
                    strict=True,
                )
                for question, verdict in zip(pack, judged, strict=True)
            }
        return tuple(self._placed(question, answered) for question in questions)

    def _placed(self, question: Question, answered: dict[tuple[str, ...], Verdict]) -> Verdict:
        verdict = answered.get(
            _identity(question),
            _failure(
                question,
                "llm.overflow",
                "Смысловая проверка не выполнена: в декларации больше различных значений поля, "
                "чем помещается в отведённые запросы к модели",
            ),
        )
        return Ruling(question.place(), verdict.status(), verdict.reason(), verdict.remark())
