import json
import random
import uuid

from hamcrest import assert_that, equal_to, raises
from pydantic import ValidationError

from app.llm.schema.shape import Shape
from app.policy.schema.extraction import Passage, Reading


def test_passage_accepts_a_key_of_the_clause_table() -> None:
    assert_that(
        Passage.model_validate(
            {"key": "limit", "point": "12.5", "text": "", "dates": [], "amounts": [], "entries": []}
        ).key,
        equal_to("limit"),
        "Passage does not accept a key of the clause table",
    )


def test_passage_rejects_a_key_outside_the_clause_table() -> None:
    body = {
        "key": uuid.uuid4().hex,
        "point": "",
        "text": "",
        "dates": [],
        "amounts": [],
        "entries": [],
    }
    assert_that(
        lambda: Passage.model_validate(body),
        raises(ValidationError),
        "Passage does not reject a key outside the clause table",
    )


def test_passage_rejects_a_point_written_with_words() -> None:
    body = {
        "key": "term",
        "point": f"п. {random.randint(1, 20)}",
        "text": "",
        "dates": [],
        "amounts": [],
        "entries": [],
    }
    assert_that(
        lambda: Passage.model_validate(body),
        raises(ValidationError),
        "Passage does not reject a point written with words",
    )


def test_passage_removes_the_point_after_the_number_of_a_clause() -> None:
    assert_that(
        Passage.model_validate(
            {
                "key": "limit",
                "point": "12.5.",
                "text": "",
                "dates": [],
                "amounts": [],
                "entries": [],
            }
        ).point,
        equal_to("12.5"),
        "Passage does not remove the point after the number of a clause",
    )


def test_passage_rejects_an_entry_into_force_from_the_model() -> None:
    body = {
        "key": "term",
        "point": "",
        "text": "",
        "dates": [],
        "amounts": [],
        "entries": [],
        "effective": "2026-01-01",
    }
    assert_that(
        lambda: Passage.model_validate(body),
        raises(ValidationError),
        "Passage does not reject an entry into force that comes from the model",
    )


def test_passage_rejects_a_scope_from_the_model() -> None:
    body = {
        "key": "term",
        "point": "",
        "text": "",
        "dates": [],
        "amounts": [],
        "entries": [],
        "scope": [str(random.randint(1, 999))],
    }
    assert_that(
        lambda: Passage.model_validate(body),
        raises(ValidationError),
        "Passage does not reject a scope that comes from the model",
    )


def test_reading_rejects_an_amendment_number_from_the_model() -> None:
    body = json.dumps({"passages": [], "amendment": random.randint(1, 30)})
    assert_that(
        lambda: Reading.model_validate_json(body),
        raises(ValidationError),
        "Reading does not reject an amendment number that comes from the model",
    )


def test_reading_gives_a_closed_schema_to_the_provider() -> None:
    assert_that(
        Shape(Reading).strict()["additionalProperties"],
        equal_to(False),
        "Reading does not give a closed schema to the provider",
    )
