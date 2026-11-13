import json
import uuid

from hamcrest import assert_that, equal_to, has_entries

from app.domain.place import Spot
from app.domain.semantics import Inquiry
from app.semantic.brief import Brief
from tests.rules.fakes import Text


def test_first_message_frames_the_task_for_the_system() -> None:
    assert_that(
        Brief()
        .messages((Inquiry(Spot("1", "cargo"), "мех", Text("ГП п. 5", "грузы"), "правило"),))[0]
        .role(),
        equal_to("system"),
        "Brief does not open the conversation with a system instruction",
    )


def test_value_refers_to_its_clause_and_rule() -> None:
    value = uuid.uuid4().hex
    clause = uuid.uuid4().hex
    rule = uuid.uuid4().hex
    payload = json.loads(
        Brief()
        .messages((Inquiry(Spot("1", "cargo"), value, Text("ГП п. 5", clause), rule),))[-1]
        .text()
    )
    assert_that(
        (payload["значения"][0], payload["пункты"][0]),
        equal_to(
            (
                {"id": 1, "пункт": 1, "значение": value},
                {"пункт": 1, "ссылка": "ГП п. 5", "текст": clause, "правило": rule},
            )
        ),
        "Brief does not tie the value to the text of its clause and the rule of its card",
    )


def test_same_clause_and_rule_is_listed_once() -> None:
    clause = Text("ГП п. 9", uuid.uuid4().hex)
    payload = json.loads(
        Brief()
        .messages(
            (
                Inquiry(Spot("1", "departure"), "Москва", clause, "правило"),
                Inquiry(Spot("2", "departure"), "Казань", clause, "правило"),
                Inquiry(Spot("3", "departure"), "Донецк", Text("ДС 2 п. 1", "иное"), "правило"),
            )
        )[-1]
        .text()
    )
    assert_that(
        (len(payload["пункты"]), payload["значения"][2]),
        equal_to((2, {"id": 3, "пункт": 2, "значение": "Донецк"})),
        "Brief does not list a shared clause once and refer each value to its own clause",
    )


def test_names_its_prompt_version() -> None:
    assert_that(
        {"version": Brief().version()},
        has_entries(version="semantic-1"),
        "Brief does not name the version of its prompt",
    )
