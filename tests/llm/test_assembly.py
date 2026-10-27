import json
import random
from pathlib import Path

from hamcrest import assert_that, equal_to, raises

from app.core.schema.environment import Environment
from app.llm.assembly import Configured
from app.llm.errors import MisconfiguredError
from app.llm.ledger import Memory
from app.llm.messages import User
from tests.llm.answers import Cover
from tests.llm.stub import Quiet, completion, envelope, gateway


def assembly(folder: Path, lines: str) -> Configured:
    (folder / ".env").write_text(
        "LLM_RETRY_PAUSE=0.01\nLLM_EMPTY_PAUSE=0.01\nLLM_TIMEOUT=5\n" + lines, encoding="utf-8"
    )
    return Configured(Environment(str(folder / ".env")), Quiet(), Memory())


def test_answers_through_vsk_gateway(tmp_path: Path) -> None:
    covered = random.choice([True, False])
    with gateway([(200, completion(f'{{"covered": {str(covered).lower()}}}'), 0.0)]) as stub:
        answer = (
            assembly(
                tmp_path,
                f"LLM_PROVIDER=vsk\nLLM_API_URL={stub.url()}\nLLM_API_KEY=k\nLLM_MODEL=m\n",
            )
            .model()
            .answer("cover", (User("q"),), Cover)
        )
    assert_that(answer.covered, equal_to(covered), "Answer through the VSK gateway is not read")


def test_retries_vsk_gateway_that_answered_503(tmp_path: Path) -> None:
    with gateway([(503, "", 0.0), (200, completion('{"covered": true}'), 0.0)]) as stub:
        assembly(
            tmp_path, f"LLM_API_URL={stub.url()}\nLLM_API_KEY=k\nLLM_MODEL=m\n"
        ).model().answer("cover", (User("q"),), Cover)
    assert_that(len(stub.raw), equal_to(2), "Gateway answer 503 is not retried")


def test_retries_empty_answer_of_vsk_gateway(tmp_path: Path) -> None:
    with gateway([(200, completion(""), 0.0), (200, completion('{"covered": true}'), 0.0)]) as stub:
        assembly(
            tmp_path, f"LLM_API_URL={stub.url()}\nLLM_API_KEY=k\nLLM_MODEL=m\n"
        ).model().answer("cover", (User("q"),), Cover)
    assert_that(len(stub.raw), equal_to(2), "Empty answer of the gateway is not retried")


def test_uses_response_format_chosen_in_settings(tmp_path: Path) -> None:
    with gateway([(200, completion('{"covered": true}'), 0.0)]) as stub:
        assembly(
            tmp_path,
            f"LLM_API_URL={stub.url()}\nLLM_API_KEY=k\nLLM_MODEL=m\n"
            "LLM_RESPONSE_FORMAT=guided_json\nLLM_THINKING_BUDGET=512\n",
        ).model().answer("cover", (User("q"),), Cover)
    body = json.loads(stub.raw[0])
    assert_that(
        (body["guided_json"]["type"], body["thinking_token_budget"]),
        equal_to(("object", 512)),
        "Response format and thinking budget from the settings are not used",
    )


def test_answers_through_anthropic_when_external_is_allowed(tmp_path: Path) -> None:
    with gateway([(200, envelope('{"covered": true}'), 0.0)]) as stub:
        answer = (
            assembly(
                tmp_path,
                "LLM_PROVIDER=anthropic\nLLM_ALLOW_EXTERNAL=true\n"
                f"ANTHROPIC_API_URL={stub.base}/v1/messages\nANTHROPIC_API_KEY=k\n",
            )
            .model()
            .answer("cover", (User("q"),), Cover)
        )
    assert_that(answer.covered, equal_to(True), "Answer through Anthropic is not read")


def test_answers_through_gemini_when_external_is_allowed(tmp_path: Path) -> None:
    with gateway([(200, completion('{"covered": false}'), 0.0)]) as stub:
        assembly(
            tmp_path,
            "LLM_PROVIDER=gemini\nLLM_ALLOW_EXTERNAL=true\n"
            f"GEMINI_API_URL={stub.url()}\nGEMINI_API_KEY=k\nGEMINI_MODEL=g\n",
        ).model().answer("cover", (User("q"),), Cover)
    body = json.loads(stub.raw[0])
    assert_that(
        (body["model"], body["response_format"]["type"]),
        equal_to(("g", "json_schema")),
        "Gemini is not asked with its model and a JSON schema",
    )


def test_refuses_anthropic_unless_external_is_allowed(tmp_path: Path) -> None:
    configured = assembly(tmp_path, "LLM_PROVIDER=anthropic\nANTHROPIC_API_KEY=k\n")
    assert_that(
        configured.model,
        raises(MisconfiguredError, "LLM_ALLOW_EXTERNAL"),
        "External provider is not refused without explicit permission",
    )


def test_refuses_gemini_unless_external_is_allowed(tmp_path: Path) -> None:
    configured = assembly(tmp_path, "LLM_PROVIDER=gemini\nGEMINI_API_KEY=k\nGEMINI_MODEL=g\n")
    assert_that(
        configured.model,
        raises(MisconfiguredError, "LLM_ALLOW_EXTERNAL"),
        "External provider is not refused without explicit permission",
    )


def test_refuses_unknown_provider(tmp_path: Path) -> None:
    assert_that(
        assembly(tmp_path, "LLM_PROVIDER=openai\n").model,
        raises(MisconfiguredError, "LLM_PROVIDER"),
        "Unknown provider is not refused",
    )


def test_refuses_unknown_response_format(tmp_path: Path) -> None:
    configured = assembly(
        tmp_path,
        "LLM_API_URL=http://127.0.0.1:9/v1/chat/completions\nLLM_API_KEY=k\n"
        "LLM_MODEL=m\nLLM_RESPONSE_FORMAT=yaml\n",
    )
    assert_that(
        configured.model,
        raises(MisconfiguredError, "LLM_RESPONSE_FORMAT"),
        "Unknown response format is not refused",
    )


def test_names_missing_gateway_address(tmp_path: Path) -> None:
    assert_that(
        assembly(tmp_path, "LLM_API_URL=\nLLM_API_KEY=k\nLLM_MODEL=m\n").model,
        raises(MisconfiguredError, "LLM_API_URL"),
        "Missing gateway address is not named",
    )


def test_names_missing_gemini_model(tmp_path: Path) -> None:
    configured = assembly(
        tmp_path,
        "LLM_PROVIDER=gemini\nLLM_ALLOW_EXTERNAL=true\nGEMINI_API_KEY=k\nGEMINI_MODEL=\n",
    )
    assert_that(
        configured.model,
        raises(MisconfiguredError, "GEMINI_MODEL"),
        "Missing Gemini model is not named",
    )


def test_refuses_missing_certificate_file(tmp_path: Path) -> None:
    configured = assembly(
        tmp_path,
        "LLM_API_URL=http://127.0.0.1:9/v1/chat/completions\nLLM_API_KEY=k\n"
        f"LLM_MODEL=m\nLLM_CA_BUNDLE={(tmp_path / 'absent.pem').as_posix()}\n",
    )
    assert_that(
        configured.model,
        raises(MisconfiguredError, "LLM_CA_BUNDLE"),
        "Missing certificate file is not refused",
    )


def test_writes_report_of_probe(tmp_path: Path) -> None:
    report = tmp_path / "report.txt"
    with (
        gateway([(200, completion('{"covered": true, "reason": "да"}'), 0.0)]) as stub,
        report.open("w", encoding="utf-8") as output,
    ):
        assembly(tmp_path, f"LLM_API_URL={stub.url()}\nLLM_API_KEY=k\nLLM_MODEL=m\n").probe(2).run(
            output
        )
    assert_that(
        report.read_text(encoding="utf-8").count("prompt:"),
        equal_to(1),
        "Probe report does not list the response formats",
    )
