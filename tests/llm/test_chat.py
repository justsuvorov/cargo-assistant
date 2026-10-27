import json
import random

import httpx
from hamcrest import assert_that, contains_string, equal_to

from app.llm.chat import Budget, Chat, GoogleBudget, GuidedJson, JsonObject, JsonSchema, Prompted
from app.llm.deadline import Countdown, Rhythm
from app.llm.errors import UnavailableError
from app.llm.messages import System, User
from app.llm.schema.shape import Shape
from app.llm.wire import Bearer, Patient
from tests.llm.answers import Cargo
from tests.llm.stub import Quiet, completion, gateway, silence


def endpoint(url: str) -> Patient:
    return Patient(Bearer(httpx.Client(), url, "k"), Rhythm(1, 0.0), 5.0, Quiet())


def test_sends_zero_temperature_and_token_limit() -> None:
    tokens = random.randint(100, 9000)
    with gateway([(200, completion("{}"), 0.0)]) as stub:
        Chat(endpoint(stub.url()), "m-1", tokens, Prompted()).reply(
            (User("q"),), Shape(Cargo), Countdown(5.0)
        )
    body = json.loads(stub.raw[0])
    assert_that(
        (body["model"], body["temperature"], body["max_tokens"]),
        equal_to(("m-1", 0, tokens)),
        "Request does not carry zero temperature, the model and the token limit",
    )


def test_opens_conversation_with_schema_instruction() -> None:
    with gateway([(200, completion("{}"), 0.0)]) as stub:
        Chat(endpoint(stub.url()), "m", 64, Prompted()).reply(
            (System("роль"), User("вопрос")), Shape(Cargo), Countdown(5.0)
        )
    assert_that(
        stub.roles(0),
        equal_to(["system", "system", "user"]),
        "Schema instruction does not open the conversation",
    )


def test_reads_content_and_tokens_of_completion() -> None:
    content = json.dumps({"name": "Холодильник", "pieces": random.randint(1, 99)})
    with gateway([(200, completion(content, (31, 17)), 0.0)]) as stub:
        reply = Chat(endpoint(stub.url()), "m", 64, Prompted()).reply(
            (User("q"),), Shape(Cargo), Countdown(5.0)
        )
    assert_that(
        (reply.text(), reply.spent()),
        equal_to((content, (31, 17))),
        "Content and tokens of the completion are not read",
    )


def test_reads_null_content_as_empty_text() -> None:
    with gateway([(200, silence(), 0.0)]) as stub:
        reply = Chat(endpoint(stub.url()), "m", 64, Prompted()).reply(
            (User("q"),), Shape(Cargo), Countdown(5.0)
        )
    assert_that(reply.text(), equal_to(""), "Null content does not become an empty text")


def test_refuses_body_that_is_not_completion() -> None:
    failure = ""
    with gateway([(200, "<html>proxy</html>", 0.0)]) as stub:
        try:
            Chat(endpoint(stub.url()), "m", 64, Prompted()).reply(
                (User("q"),), Shape(Cargo), Countdown(5.0)
            )
        except UnavailableError as error:
            failure = str(error)
    assert_that(
        failure,
        contains_string("не в формате chat completions"),
        "Body that is not a completion does not raise an unavailable model error",
    )


def test_constrains_answer_by_json_schema() -> None:
    with gateway([(200, completion("{}"), 0.0)]) as stub:
        Chat(endpoint(stub.url()), "m", 64, JsonSchema()).reply(
            (User("q"),), Shape(Cargo), Countdown(5.0)
        )
    assert_that(
        json.loads(stub.raw[0])["response_format"],
        equal_to(
            {
                "type": "json_schema",
                "json_schema": {"name": "Cargo", "schema": Shape(Cargo).strict(), "strict": True},
            }
        ),
        "Answer is not constrained by response_format json_schema",
    )


def test_asks_for_json_object() -> None:
    with gateway([(200, completion("{}"), 0.0)]) as stub:
        Chat(endpoint(stub.url()), "m", 64, JsonObject()).reply(
            (User("q"),), Shape(Cargo), Countdown(5.0)
        )
    assert_that(
        json.loads(stub.raw[0])["response_format"],
        equal_to({"type": "json_object"}),
        "Answer is not constrained by response_format json_object",
    )


def test_constrains_answer_by_guided_json() -> None:
    with gateway([(200, completion("{}"), 0.0)]) as stub:
        Chat(endpoint(stub.url()), "m", 64, GuidedJson()).reply(
            (User("q"),), Shape(Cargo), Countdown(5.0)
        )
    assert_that(
        json.loads(stub.raw[0])["guided_json"],
        equal_to(Shape(Cargo).strict()),
        "Answer is not constrained by guided_json",
    )


def test_limits_reasoning_by_thinking_token_budget() -> None:
    budget = random.randint(100, 4000)
    with gateway([(200, completion("{}"), 0.0)]) as stub:
        Chat(endpoint(stub.url()), "m", 64, Budget(budget, Prompted())).reply(
            (User("q"),), Shape(Cargo), Countdown(5.0)
        )
    assert_that(
        json.loads(stub.raw[0])["thinking_token_budget"],
        equal_to(budget),
        "Reasoning is not limited by thinking_token_budget",
    )


def test_limits_reasoning_of_gemini_by_thinking_config() -> None:
    budget = random.randint(100, 4000)
    with gateway([(200, completion("{}"), 0.0)]) as stub:
        Chat(endpoint(stub.url()), "m", 64, GoogleBudget(budget, JsonSchema())).reply(
            (User("q"),), Shape(Cargo), Countdown(5.0)
        )
    assert_that(
        json.loads(stub.raw[0])["extra_body"],
        equal_to({"google": {"thinking_config": {"thinking_budget": budget}}}),
        "Gemini reasoning is not limited by thinking_config",
    )
