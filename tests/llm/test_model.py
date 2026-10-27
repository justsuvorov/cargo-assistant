import contextlib
import json
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from hamcrest import assert_that, equal_to, less_than_or_equal_to, raises
from pydantic import BaseModel

from app.llm.errors import MalformedError, UnavailableError
from app.llm.ledger import Memory, Route
from app.llm.messages import Message, User
from app.llm.model import Strict, Throttled
from tests.llm.answers import Sum
from tests.llm.stub import Scripted


class Crowd:
    """Model double that sleeps inside the call and remembers the largest crowd of callers."""

    def __init__(self) -> None:
        self.inside = 0
        self.most = 0
        self.lock = threading.Lock()

    def answer[T: BaseModel](
        self, purpose: str, messages: tuple[Message, ...], schema: type[T]
    ) -> T:
        with self.lock:
            self.inside += 1
            self.most = max(self.most, self.inside)
        time.sleep(0.05)
        with self.lock:
            self.inside -= 1
        return schema.model_validate_json(json.dumps({"total": len(messages) + len(purpose)}))


def test_returns_answer_as_schema_instance() -> None:
    total = random.randint(1, 10**6)
    assert_that(
        Strict(Scripted([f'{{"total": {total}}}']), Route("vsk", "m"), Memory(), 5.0)
        .answer("sum", (User("q"),), Sum)
        .total,
        equal_to(total),
        "Answer does not come back as an instance of the schema",
    )


def test_reads_answer_after_reasoning_and_fence() -> None:
    total = random.randint(1, 999)
    assert_that(
        Strict(
            Scripted([f'<think>считаю</think>\n```json\n{{"total": {total}}}\n```']),
            Route("vsk", "m"),
            Memory(),
            5.0,
        )
        .answer("sum", (User("q"),), Sum)
        .total,
        equal_to(total),
        "Answer wrapped in reasoning and a fence is not read",
    )


def test_asks_once_more_after_invalid_answer() -> None:
    assert_that(
        Strict(Scripted(["Сумма равна семи", '{"total": 7}']), Route("vsk", "m"), Memory(), 5.0)
        .answer("sum", (User("q"),), Sum)
        .total,
        equal_to(7),
        "Invalid answer is not asked once more",
    )


def test_shows_invalid_answer_to_model_when_asking_again() -> None:
    backend = Scripted(['{"total": "семь"}', '{"total": 7}'])
    Strict(backend, Route("vsk", "m"), Memory(), 5.0).answer("sum", (User("q"),), Sum)
    assert_that(
        [message.role() for message in backend.conversations[1]],
        equal_to(["user", "assistant", "user"]),
        "Second request does not show the invalid answer and the correction",
    )


def test_fails_after_second_invalid_answer() -> None:
    model = Strict(Scripted(["нет JSON"]), Route("vsk", "m"), Memory(), 5.0)
    assert_that(
        lambda: model.answer("sum", (User("q"),), Sum),
        raises(MalformedError),
        "Second invalid answer does not raise a malformed answer error",
    )


def test_makes_no_more_than_two_requests_for_invalid_answers() -> None:
    backend = Scripted(["нет JSON"])
    with contextlib.suppress(MalformedError):
        Strict(backend, Route("vsk", "m"), Memory(), 5.0).answer("sum", (User("q"),), Sum)
    assert_that(backend.calls, equal_to(2), "Invalid answers do not stop after two requests")


def test_records_each_request_with_its_validity() -> None:
    ledger = Memory()
    Strict(Scripted(["{}", '{"total": 1}']), Route("vsk", "m"), ledger, 5.0).answer(
        "sum", (User("q"),), Sum
    )
    assert_that(
        [call.outcome().valid() for call in ledger.calls()],
        equal_to([False, True]),
        "Requests are not recorded with the result of the schema check",
    )


def test_records_purpose_provider_and_tokens() -> None:
    ledger = Memory()
    purpose = f"purpose-{random.randint(1, 999)}"
    Strict(Scripted(['{"total": 1}']), Route("gemini", "g-1"), ledger, 5.0).answer(
        purpose, (User("q"),), Sum
    )
    call = ledger.calls()[0]
    assert_that(
        (call.purpose(), call.origin().provider(), call.origin().model(), call.outcome().spent()),
        equal_to((purpose, "gemini", "g-1", (3, 2))),
        "Purpose, provider, model and tokens are not recorded",
    )


def test_gives_same_digest_to_same_prompt() -> None:
    ledger = Memory()
    model = Strict(Scripted(['{"total": 1}']), Route("vsk", "m"), ledger, 5.0)
    model.answer("sum", (User("один и тот же вопрос"),), Sum)
    model.answer("sum", (User("один и тот же вопрос"),), Sum)
    assert_that(
        len({call.digest() for call in ledger.calls()}),
        equal_to(1),
        "Same prompt does not get the same digest",
    )


def test_records_failed_request_as_invalid() -> None:
    ledger = Memory()
    with contextlib.suppress(UnavailableError):
        Strict(Scripted(["{}"]), Route("vsk", "m"), ledger, 0.0).answer("sum", (User("q"),), Sum)
    assert_that(
        [call.outcome().valid() for call in ledger.calls()],
        equal_to([False]),
        "Failed request is not recorded as invalid",
    )


def test_lets_no_more_calls_run_at_once_than_semaphore_allows() -> None:
    limit = random.randint(1, 3)
    crowd = Crowd()
    model = Throttled(crowd, threading.BoundedSemaphore(limit))
    with ThreadPoolExecutor(max_workers=8) as pool:
        tuple(pool.map(lambda _: model.answer("sum", (), Sum), range(8), timeout=5))
    assert_that(
        crowd.most, less_than_or_equal_to(limit), "Semaphore does not hold back extra calls"
    )
