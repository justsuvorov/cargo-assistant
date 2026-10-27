import json
import random

import httpx
from hamcrest import assert_that, equal_to, starts_with

from app.llm.claude import Claude
from app.llm.deadline import Countdown, Rhythm
from app.llm.messages import System, User
from app.llm.schema.shape import Shape
from app.llm.wire import Keyed, Patient
from tests.llm.answers import Journey
from tests.llm.stub import Quiet, envelope, gateway


def endpoint(url: str) -> Patient:
    return Patient(Keyed(httpx.Client(), url, "k"), Rhythm(1, 0.0), 5.0, Quiet())


def test_constrains_answer_by_structured_output() -> None:
    with gateway([(200, envelope("{}"), 0.0)]) as stub:
        Claude(endpoint(stub.url()), "claude-x", 256, {}).reply(
            (User("q"),), Shape(Journey), Countdown(5.0)
        )
    assert_that(
        json.loads(stub.raw[0])["output_config"],
        equal_to({"format": {"type": "json_schema", "schema": Shape(Journey).strict()}}),
        "Answer is not constrained by output_config format",
    )


def test_sends_no_temperature_to_anthropic() -> None:
    with gateway([(200, envelope("{}"), 0.0)]) as stub:
        Claude(endpoint(stub.url()), "claude-x", 256, {}).reply(
            (User("q"),), Shape(Journey), Countdown(5.0)
        )
    assert_that(
        "temperature" in json.loads(stub.raw[0]),
        equal_to(False),
        "Request does not leave out the temperature that current Claude models reject",
    )


def test_moves_system_messages_into_system_field() -> None:
    role = f"роль {random.randint(1, 999)}"
    with gateway([(200, envelope("{}"), 0.0)]) as stub:
        Claude(endpoint(stub.url()), "claude-x", 256, {}).reply(
            (System(role), User("вопрос")), Shape(Journey), Countdown(5.0)
        )
    assert_that(
        (json.loads(stub.raw[0])["system"], stub.roles(0)),
        equal_to((f"{Shape(Journey).instruction()}\n\n{role}", ["user"])),
        "System messages are not moved into the system field",
    )


def test_passes_effort_from_settings() -> None:
    with gateway([(200, envelope("{}"), 0.0)]) as stub:
        Claude(endpoint(stub.url()), "claude-x", 256, {"effort": "low"}).reply(
            (User("q"),), Shape(Journey), Countdown(5.0)
        )
    assert_that(
        json.loads(stub.raw[0])["output_config"]["effort"],
        equal_to("low"),
        "Effort from the settings is not passed",
    )


def test_reads_text_blocks_and_tokens() -> None:
    text = json.dumps({"departure": "Москва", "arrival": f"Город {random.randint(1, 99)}"})
    with gateway([(200, envelope(text, (21, 8)), 0.0)]) as stub:
        reply = Claude(endpoint(stub.url()), "claude-x", 256, {}).reply(
            (User("q"),), Shape(Journey), Countdown(5.0)
        )
    assert_that(
        (reply.text(), reply.spent()),
        equal_to((text, (21, 8))),
        "Text blocks and tokens of the Anthropic answer are not read",
    )


def test_posts_to_messages_endpoint_with_model() -> None:
    with gateway([(200, envelope("{}"), 0.0)]) as stub:
        Claude(endpoint(f"{stub.base}/v1/messages"), "claude-y", 256, {}).reply(
            (User("q"),), Shape(Journey), Countdown(5.0)
        )
    assert_that(
        (stub.paths[0], json.loads(stub.raw[0])["model"]),
        equal_to(("/v1/messages", "claude-y")),
        "Request does not go to the messages endpoint with the model",
    )


def test_keeps_instruction_first_in_system_field() -> None:
    with gateway([(200, envelope("{}"), 0.0)]) as stub:
        Claude(endpoint(stub.url()), "claude-x", 256, {}).reply(
            (User("q"),), Shape(Journey), Countdown(5.0)
        )
    assert_that(
        json.loads(stub.raw[0])["system"],
        starts_with("Ответь одним JSON-объектом"),
        "Schema instruction does not open the system field",
    )
