import json
import logging
import random
import threading
import time
import uuid
from collections.abc import Mapping
from datetime import date
from pathlib import Path

from hamcrest import (
    assert_that,
    contains_string,
    equal_to,
    less_than_or_equal_to,
    only_contains,
)
from pydantic import BaseModel

from app.core.journal import LogJournal
from app.domain.place import Spot
from app.domain.policy import Policy
from app.domain.semantics import Inquiry, Question
from app.llm.errors import TruncatedError, UnavailableError
from app.llm.fake import FakeModel
from app.llm.messages import Message
from app.llm.model import Model, Throttled
from app.rules.cards import Cards
from app.semantic.bench import Bench
from tests.rules.fakes import Paper, Profile, Text


class Recording:
    """Model double that remembers every conversation and passes it to another model."""

    def __init__(self, model: Model) -> None:
        self.model = model
        self.asked: list[tuple[str, tuple[Message, ...]]] = []
        self.lock = threading.Lock()

    def answer[T: BaseModel](
        self, purpose: str, messages: tuple[Message, ...], schema: type[T]
    ) -> T:
        with self.lock:
            self.asked.append((purpose, messages))
        return self.model.answer(purpose, messages, schema)


class Silent:
    """Model double whose gateway never answers."""

    def answer[T: BaseModel](
        self, purpose: str, _messages: tuple[Message, ...], _schema: type[T]
    ) -> T:
        raise UnavailableError(f"шлюз не ответил на запрос {purpose}")


class Meeting:
    """Model double that answers only when all expected callers are inside at once."""

    def __init__(self, parties: int) -> None:
        self.barrier = threading.Barrier(parties, timeout=2.0)
        self.met: list[bool] = []

    def answer[T: BaseModel](
        self, _purpose: str, _messages: tuple[Message, ...], schema: type[T]
    ) -> T:
        try:
            self.barrier.wait()
            self.met.append(True)
        except threading.BrokenBarrierError:
            self.met.append(False)
        return schema.model_validate_json('{"answers": []}')


class Crowd:
    """Model double that sleeps inside the call and remembers the largest crowd of callers."""

    def __init__(self) -> None:
        self.inside = 0
        self.most = 0
        self.lock = threading.Lock()

    def answer[T: BaseModel](
        self, _purpose: str, _messages: tuple[Message, ...], schema: type[T]
    ) -> T:
        with self.lock:
            self.inside += 1
            self.most = max(self.most, self.inside)
        time.sleep(0.05)
        with self.lock:
            self.inside -= 1
        return schema.model_validate_json('{"answers": []}')


def _journal() -> LogJournal:
    return LogJournal(logging.getLogger("semantic"))


def _question(row: int, field: str, value: str) -> Question:
    return Inquiry(
        Spot(f"7/{row}", field),
        value,
        Text("ГП п. 5", "Грузы общего назначения, кроме меха"),
        "Позиция из исключений не совпадает",
    )


def _answers(*pairs: tuple[int, str]) -> str:
    return json.dumps(
        {"answers": [{"id": key, "status": status, "comment": "ответ"} for key, status in pairs]}
    )


def _folder() -> Path:
    return Path(__file__).resolve().parents[2] / "cards"


def _policy() -> Policy:
    return Profile(
        {
            "insurer": Text("ГП, преамбула", "ООО «Страхователь-Тест»"),
            "number": Text("ГП, преамбула", "9999T99GR9999", dates=(date(2026, 8, 26),)),
            "term": Text("ГП п. 6", "срок", dates=(date(2026, 1, 1), date(2026, 12, 31))),
            "object": Text("ГП п. 5", "грузы общего назначения"),
            "transport": Text("ГП п. 8", "автомобильным транспортом"),
            "territory": Text("ГП п. 9", "РФ"),
        }
    )


def _row(cargo: str, beneficiary: str) -> Mapping[str, tuple[str, ...]]:
    return {
        "insurer": ("ООО «Страхователь-Тест»",),
        "policy": ("№ 9999T99GR9999 от 26.08.2026 г.",),
        "period_start": ("14.09.2026",),
        "period_end": ("30.09.2026",),
        "cargo": (cargo,),
        "beneficiary": (beneficiary,),
        "document_number": ("77777-1/Р",),
        "document_date": ("14.09.2026",),
        "transport": ("Авто",),
        "departure": ("г. Первый",),
        "destination": ("г. Второй",),
        "sum": ("1 000 000", "RUB"),
    }


def _calls(rows: int) -> int:
    model = FakeModel(
        {
            "semantic.cargo": '{"answers": []}',
            "semantic.departure": '{"answers": []}',
            "semantic.destination": '{"answers": []}',
        }
    )
    paper = Paper(
        "17",
        "psg",
        tuple(_row(uuid.uuid4().hex, "ООО «Получатель»") for _ in range(rows)),
    )
    for card in Cards(_folder(), Bench(model, _journal(), 1, 100)).cards("psg"):
        card.verdicts(paper, _policy())
    return model.count()


def test_makes_one_model_call_per_semantic_card_whatever_the_number_of_rows() -> None:
    assert_that(
        (_calls(2), _calls(random.randint(40, 80))),
        equal_to((3, 3)),
        "Bench does not keep one model call per semantic card and declaration",
    )


def test_asks_the_same_value_once() -> None:
    value = uuid.uuid4().hex
    model = Recording(FakeModel({"semantic.cargo": _answers((1, "match"), (2, "match"))}))
    Bench(model, _journal(), 1, 100).verdicts(
        (
            *(_question(row, "cargo", value) for row in range(1, 6)),
            _question(6, "cargo", f" {value.upper()}  "),
            _question(7, "cargo", "мех"),
        )
    )
    assert_that(
        len(json.loads(model.asked[0][1][-1].text())["значения"]),
        equal_to(2),
        "Bench does not ask the same value only once",
    )


def test_gives_the_answer_to_every_place_with_the_same_value() -> None:
    value = uuid.uuid4().hex
    rows = random.randint(2, 9)
    verdicts = Bench(
        FakeModel({"semantic.cargo": _answers((1, "mismatch"), (2, "match"))}), _journal(), 1, 100
    ).verdicts(
        (
            *(_question(row, "cargo", "мех") for row in range(1, rows)),
            _question(rows, "cargo", value),
        )
    )
    assert_that(
        tuple((verdict.place().shipment(), verdict.status().key()) for verdict in verdicts),
        equal_to((*((f"7/{row}", "mismatch") for row in range(1, rows)), (f"7/{rows}", "match"))),
        "Bench does not hand the answer to every place with the same value",
    )


def test_model_verdict_cites_the_clause_and_names_the_model_as_source() -> None:
    verdict = Bench(
        FakeModel({"semantic.cargo": _answers((1, "mismatch"))}), _journal(), 1, 100
    ).verdicts((_question(1, "cargo", "мех"),))[0]
    assert_that(
        (
            verdict.status().key(),
            verdict.reason().code(),
            verdict.reason().source(),
            verdict.remark().reference(),
            verdict.remark().comment(),
        ),
        equal_to(("mismatch", "cargo.mismatch", "llm", "ГП п. 5", "ответ")),
        "Bench does not word the model verdict with the clause reference and the llm source",
    )


def test_unsure_model_gives_review() -> None:
    verdict = Bench(
        FakeModel({"semantic.departure": _answers((1, "review"))}), _journal(), 1, 100
    ).verdicts((_question(1, "departure", "СПБ"),))[0]
    assert_that(
        (verdict.status().key(), verdict.reason().code()),
        equal_to(("review", "departure.review")),
        "Bench does not turn an unsure model answer into review",
    )


def test_invalid_json_gives_review_with_its_code() -> None:
    verdicts = Bench(
        FakeModel({"semantic.cargo": '{"answers": "не знаю"}'}), _journal(), 1, 100
    ).verdicts(tuple(_question(row, "cargo", uuid.uuid4().hex) for row in range(1, 4)))
    assert_that(
        tuple(
            (verdict.status().key(), verdict.reason().code(), verdict.reason().source())
            for verdict in verdicts
        ),
        only_contains(("review", "llm.invalid_json", "llm")),
        "Bench does not turn an invalid model answer into review with llm.invalid_json",
    )


def test_silent_gateway_gives_review_with_its_code() -> None:
    verdicts = Bench(Silent(), _journal(), 1, 100).verdicts(
        tuple(_question(row, "destination", uuid.uuid4().hex) for row in range(1, 4))
    )
    assert_that(
        tuple((verdict.status().key(), verdict.reason().code()) for verdict in verdicts),
        only_contains(("review", "llm.unavailable")),
        "Bench does not turn a silent gateway into review with llm.unavailable",
    )


def test_value_the_model_left_without_answer_gives_review() -> None:
    verdicts = Bench(
        FakeModel({"semantic.cargo": _answers((1, "match"), (9, "mismatch"))}), _journal(), 1, 100
    ).verdicts((_question(1, "cargo", "бумага"), _question(2, "cargo", "мех")))
    assert_that(
        tuple((verdict.status().key(), verdict.reason().code()) for verdict in verdicts),
        equal_to((("match", "cargo.match"), ("review", "llm.unanswered"))),
        "Bench does not give review to a value the model left without answer",
    )


def test_one_failed_card_leaves_other_cards_judged() -> None:
    verdicts = Bench(
        FakeModel(
            {"semantic.cargo": '{"answers": 1}', "semantic.departure": _answers((1, "match"))}
        ),
        _journal(),
        1,
        100,
    ).verdicts((_question(1, "cargo", "мех"), _question(1, "departure", "Москва")))
    assert_that(
        tuple(verdict.reason().code() for verdict in verdicts),
        equal_to(("llm.invalid_json", "departure.match")),
        "Bench does not keep judging other cards after one card failed",
    )


def test_asks_cards_in_parallel() -> None:
    model = Meeting(3)
    Bench(model, _journal(), 1, 100).verdicts(
        tuple(
            _question(1, field, uuid.uuid4().hex) for field in ("cargo", "departure", "destination")
        )
    )
    assert_that(model.met, only_contains(True), "Bench does not ask the cards in parallel")


def test_shared_semaphore_limits_parallel_calls() -> None:
    model = Crowd()
    Bench(Throttled(model, threading.BoundedSemaphore(1)), _journal(), 1, 100).verdicts(
        tuple(
            _question(1, field, uuid.uuid4().hex) for field in ("cargo", "departure", "destination")
        )
    )
    assert_that(model.most, equal_to(1), "Bench does not respect the shared semaphore of calls")


def _texts(beneficiary: str) -> str:
    model = Recording(
        FakeModel(
            {
                "semantic.cargo": '{"answers": []}',
                "semantic.departure": '{"answers": []}',
                "semantic.destination": '{"answers": []}',
            }
        )
    )
    paper = Paper("18", "psg", (_row("Бумага", beneficiary), _row("Мех", beneficiary)))
    for card in Cards(_folder(), Bench(model, _journal(), 1, 100)).cards("psg"):
        card.verdicts(paper, _policy())
    return "\n".join(message.text() for _, messages in model.asked for message in messages)


def test_prompt_holds_no_policy_number_insurer_or_other_fields() -> None:
    beneficiary = f"ООО «{uuid.uuid4().hex}»"
    texts = _texts(beneficiary)
    assert_that(
        tuple(
            part
            for part in ("9999T99GR9999", "Страхователь-Тест", beneficiary, "77777-1", "1 000 000")
            if part in texts
        ),
        equal_to(()),
        "Bench does not keep the policy number, the insurer and other fields out of the prompt",
    )


def test_prompt_holds_the_declared_cargo() -> None:
    model = Recording(FakeModel({"semantic.cargo": '{"answers": []}'}))
    value = uuid.uuid4().hex
    Bench(model, _journal(), 1, 100).verdicts((_question(1, "cargo", value),))
    assert_that(
        " ".join(message.text() for message in model.asked[0][1]),
        contains_string(value),
        "Bench does not send the model the declared value",
    )


class Clipped:
    """Model double whose answers are always cut by the token limit."""

    def answer[T: BaseModel](
        self, purpose: str, _messages: tuple[Message, ...], _schema: type[T]
    ) -> T:
        raise TruncatedError(f"ответ на запрос {purpose} обрезан")


def test_answer_cut_by_token_limit_gives_review_to_every_place_of_the_card() -> None:
    rows = random.randint(2, 30)
    verdicts = Bench(Clipped(), _journal(), 1, 100).verdicts(
        tuple(_question(row, "cargo", uuid.uuid4().hex) for row in range(1, rows))
    )
    assert_that(
        tuple((verdict.status().key(), verdict.reason().code()) for verdict in verdicts),
        only_contains(("review", "llm.truncated")),
        "Bench does not turn an answer cut by the token limit into review with llm.truncated",
    )


def _packed(rows: int, packs: int, size: int) -> int:
    model = FakeModel(
        {
            "semantic.cargo": '{"answers": []}',
            "semantic.departure": '{"answers": []}',
            "semantic.destination": '{"answers": []}',
        }
    )
    Bench(model, _journal(), packs, size).verdicts(
        tuple(
            _question(row, field, uuid.uuid4().hex)
            for row in range(1, rows + 1)
            for field in ("cargo", "departure", "destination")
        )
    )
    return model.count()


def test_calls_stay_within_three_cards_times_packs_whatever_the_number_of_rows() -> None:
    packs = random.randint(1, 4)
    size = random.randint(1, 20)
    assert_that(
        max(_packed(rows, packs, size) for rows in (1, size * packs, random.randint(100, 300))),
        less_than_or_equal_to(3 * packs),
        "Bench does not keep its calls within three cards times the packs per card",
    )


def test_values_beyond_the_packs_give_review_with_their_code() -> None:
    verdicts = Bench(
        FakeModel({"semantic.cargo": _answers((1, "match"), (2, "match"))}), _journal(), 1, 2
    ).verdicts(tuple(_question(row, "cargo", f"груз {row}") for row in range(1, 4)))
    assert_that(
        tuple((verdict.status().key(), verdict.reason().code()) for verdict in verdicts),
        equal_to((("match", "cargo.match"), ("match", "cargo.match"), ("review", "llm.overflow"))),
        "Bench does not give review with llm.overflow to values beyond its packs",
    )


def test_values_of_one_card_are_split_into_packs_of_the_given_size() -> None:
    model = Recording(FakeModel({"semantic.cargo": '{"answers": []}'}))
    Bench(model, _journal(), 3, 2).verdicts(
        tuple(_question(row, "cargo", f"груз {row}") for row in range(1, 6))
    )
    assert_that(
        sorted(len(json.loads(messages[-1].text())["значения"]) for _, messages in model.asked),
        equal_to([1, 2, 2]),
        "Bench does not split the values of a card into packs of the given size",
    )
