import contextlib
import random

import httpx
from hamcrest import assert_that, equal_to, has_entries, less_than, raises

from app.llm.deadline import Countdown, Rhythm
from app.llm.errors import UnavailableError
from app.llm.wire import Bearer, Keyed, Patient
from tests.llm.stub import Quiet, client, gateway, refusal


def test_returns_answer_after_retrying_unavailable_gateway() -> None:
    with gateway([(503, "", 0.0), (504, "", 0.0), (200, '{"ok": 1}', 0.0)]) as stub:
        text = Patient(Bearer(client(), stub.url(), "k"), Rhythm(5, 0.01), 5.0, Quiet()).post(
            {"model": "m"}, Countdown(10.0)
        )
    assert_that(text, equal_to('{"ok": 1}'), "Answer after transient failures is not returned")


def test_retries_rate_limited_request() -> None:
    with gateway([(429, "", 0.0), (200, "{}", 0.0)]) as stub:
        Patient(Bearer(client(), stub.url(), "k"), Rhythm(5, 0.01), 5.0, Quiet()).post(
            {}, Countdown(10.0)
        )
    assert_that(len(stub.raw), equal_to(2), "Rate limited request is not repeated")


def test_retries_internal_server_error() -> None:
    with gateway([(500, "", 0.0), (200, "{}", 0.0)]) as stub:
        Patient(Bearer(client(), stub.url(), "k"), Rhythm(5, 0.01), 5.0, Quiet()).post(
            {}, Countdown(10.0)
        )
    assert_that(len(stub.raw), equal_to(2), "Answer 500 is not repeated")


def test_retries_request_that_timed_out() -> None:
    with gateway([(200, "{}", 5.0), (200, '{"late": 0}', 0.0)]) as stub:
        text = Patient(Bearer(client(), stub.url(), "k"), Rhythm(3, 0.01), 0.5, Quiet()).post(
            {}, Countdown(10.0)
        )
    assert_that(text, equal_to('{"late": 0}'), "Timed out request is not repeated")


def test_retries_refused_connection_until_attempts_run_out() -> None:
    patient = Patient(
        Bearer(
            httpx.Client(transport=httpx.MockTransport(refusal)),
            f"http://127.0.0.1:{random.randint(1024, 65535)}/v1/chat/completions",
            "k",
        ),
        Rhythm(2, 0.01),
        1.0,
        Quiet(),
    )
    assert_that(
        lambda: patient.post({}, Countdown(10.0)),
        raises(UnavailableError, "сетевая ошибка"),
        "Refused connection does not end in an unavailable model error",
    )


def test_fails_at_once_on_rejected_request() -> None:
    with (
        gateway([(400, '{"error": "bad"}', 0.0), (200, "{}", 0.0)]) as stub,
        contextlib.suppress(UnavailableError),
    ):
        Patient(Bearer(client(), stub.url(), "k"), Rhythm(5, 0.01), 5.0, Quiet()).post(
            {}, Countdown(10.0)
        )
    assert_that(len(stub.raw), equal_to(1), "Rejected request does not fail at once")


def test_gives_up_after_all_attempts() -> None:
    attempts = random.randint(2, 4)
    with gateway([(503, "", 0.0)]) as stub, contextlib.suppress(UnavailableError):
        Patient(Bearer(client(), stub.url(), "k"), Rhythm(attempts, 0.01), 5.0, Quiet()).post(
            {}, Countdown(10.0)
        )
    assert_that(len(stub.raw), equal_to(attempts), "Retries do not stop after the attempts")


def test_stops_retrying_when_total_time_runs_out() -> None:
    with gateway([(503, "", 0.0)]) as stub, contextlib.suppress(UnavailableError):
        Patient(Bearer(client(), stub.url(), "k"), Rhythm(50, 0.05), 5.0, Quiet()).post(
            {}, Countdown(0.3)
        )
    assert_that(len(stub.raw), less_than(10), "Retries do not stop when the total time runs out")


def test_sends_bearer_key_to_chat_endpoint() -> None:
    key = f"key-{random.randint(1000, 9999)}"
    with gateway([(200, "{}", 0.0)]) as stub:
        Bearer(client(), stub.url(), key).send({}, 5.0)
    assert_that(
        stub.headers[0],
        has_entries({"Authorization": f"Bearer {key}"}),
        "Bearer key is not sent in the authorization header",
    )


def test_sends_api_key_and_version_to_anthropic() -> None:
    key = f"key-{random.randint(1000, 9999)}"
    with gateway([(200, "{}", 0.0)]) as stub:
        Keyed(client(), stub.url(), key).send({}, 5.0)
    assert_that(
        stub.headers[0],
        has_entries({"x-api-key": key, "anthropic-version": "2026-10-21"}),
        "Anthropic key and version headers are not sent",
    )
