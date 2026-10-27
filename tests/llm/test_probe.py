import io
import random

import httpx
from hamcrest import assert_that, contains_string, equal_to, raises

from app.llm.chat import Chat, JsonSchema, Prompted
from app.llm.deadline import Rhythm
from app.llm.errors import UnavailableError
from app.llm.ledger import Route
from app.llm.probe import Listing, Probe, Unlisted
from app.llm.wire import Bearer, Patient
from tests.llm.stub import Quiet, Scripted, completion, gateway


class Names:
    """Inventory double with a fixed list of models."""

    def __init__(self, names: tuple[str, ...]) -> None:
        self.entries = names

    def names(self) -> tuple[str, ...]:
        return self.entries


def report(probe: Probe) -> str:
    output = io.StringIO()
    probe.run(output)
    return output.getvalue()


def test_reports_one_distinct_answer_of_deterministic_model() -> None:
    assert_that(
        report(
            Probe(
                {"prompt": Scripted(['{"covered": true, "reason": "да"}'])},
                Names(()),
                Route("vsk", "m"),
                2,
            )
        ),
        contains_string("различных ответов 1"),
        "Deterministic model is not reported with one distinct answer",
    )


def test_reports_every_distinct_answer_of_random_model() -> None:
    assert_that(
        report(
            Probe(
                {"prompt": Scripted([f'{{"n": {index}}}' for index in range(7)])},
                Names(()),
                Route("vsk", "m"),
                2,
            )
        ),
        contains_string("различных ответов 5"),
        "Random model is not reported with five distinct answers",
    )


def test_reports_rejected_response_format() -> None:
    with gateway([(400, '{"error": "response_format is not supported"}', 0.0)]) as stub:
        endpoint = Patient(Bearer(httpx.Client(), stub.url(), "k"), Rhythm(1, 0.0), 5.0, Quiet())
        text = report(
            Probe(
                {
                    "prompt": Scripted(['{"covered": true, "reason": "да"}']),
                    "json_schema": Chat(endpoint, "m", 64, JsonSchema()),
                },
                Names(()),
                Route("vsk", "m"),
                2,
            )
        )
    assert_that(
        text,
        contains_string("json_schema: не работает: Модель отклонила запрос с кодом 400"),
        "Rejected response format is not reported",
    )


def test_reports_failures_under_parallel_load() -> None:
    with gateway([(429, "", 0.0)]) as stub:
        endpoint = Patient(Bearer(httpx.Client(), stub.url(), "k"), Rhythm(1, 0.0), 5.0, Quiet())
        text = report(
            Probe({"prompt": Chat(endpoint, "m", 64, Prompted())}, Names(()), Route("vsk", "m"), 3)
        )
    assert_that(
        text,
        contains_string("успешно 0, ошибок 3"),
        "Failures under parallel load are not counted",
    )


def test_lists_models_of_gateway() -> None:
    name = f"embed-{random.randint(1, 99)}"
    assert_that(
        report(
            Probe(
                {"prompt": Scripted(['{"covered": true, "reason": "да"}'])},
                Names(("chat-1", name)),
                Route("vsk", "m"),
                1,
            )
        ),
        contains_string(f"chat-1, {name}"),
        "Models of the gateway are not listed",
    )


def test_reads_models_from_openai_compatible_list() -> None:
    with gateway([(200, '{"object": "list", "data": [{"id": "a"}, {"id": "b"}]}', 0.0)]) as stub:
        names = Listing(httpx.Client(), f"{stub.base}/v1/models", "k").names()
    assert_that(names, equal_to(("a", "b")), "Models are not read from the list")


def test_refuses_list_of_provider_without_one() -> None:
    assert_that(
        Unlisted().names,
        raises(UnavailableError),
        "Provider without a list of models does not raise an unavailable error",
    )


def test_reports_answer_of_typical_request() -> None:
    with gateway([(200, completion('{"covered": true, "reason": "да"}', (40, 9)), 0.0)]) as stub:
        endpoint = Patient(Bearer(httpx.Client(), stub.url(), "k"), Rhythm(1, 0.0), 5.0, Quiet())
        text = report(
            Probe({"prompt": Chat(endpoint, "m", 64, Prompted())}, Names(()), Route("vsk", "m"), 1)
        )
    assert_that(
        text,
        contains_string("токенов на входе 40, на выходе 9, ответ проходит схему: да"),
        "Typical request is not reported with tokens and validity",
    )
