import json

from hamcrest import assert_that, contains_string, equal_to

from app.llm.schema.shape import Shape
from tests.llm.answers import Shipment


def test_closes_nested_objects() -> None:
    assert_that(
        json.loads(json.dumps(Shape(Shipment).strict()))["$defs"]["Place"]["additionalProperties"],
        equal_to(False),
        "Nested object is not closed against extra properties",
    )


def test_requires_every_property() -> None:
    assert_that(
        Shape(Shipment).strict()["required"],
        equal_to(["place", "pieces", "note"]),
        "Property with a default is not required",
    )


def test_drops_numeric_constraints_providers_reject() -> None:
    assert_that(
        sorted(json.loads(json.dumps(Shape(Shipment).strict()))["properties"]["pieces"]),
        equal_to(["title", "type"]),
        "Numeric constraint is not dropped from the strict schema",
    )


def test_keeps_property_named_like_constraint() -> None:
    assert_that(
        sorted(json.loads(json.dumps(Shape(Shipment).strict()))["$defs"]["Place"]["properties"]),
        equal_to(["city", "minimum"]),
        "Property named like a constraint does not survive",
    )


def test_puts_schema_into_instruction() -> None:
    assert_that(
        Shape(Shipment).instruction(),
        contains_string('"additionalProperties": false'),
        "Instruction does not carry the strict schema",
    )


def test_names_schema_after_model() -> None:
    assert_that(Shape(Shipment).name(), equal_to("Shipment"), "Schema is not named after model")
