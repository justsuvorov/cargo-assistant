import json
from typing import Final, final

from pydantic import BaseModel


def _strict(node: object) -> object:
    if isinstance(node, list):
        return [_strict(item) for item in node]
    if isinstance(node, dict):
        return _object(node)
    return node


def _named(node: object) -> object:
    if isinstance(node, dict):
        return {name: _strict(schema) for name, schema in node.items()}
    return node


def _object(node: dict[str, object]) -> dict[str, object]:
    unsupported = {
        "default",
        "exclusiveMaximum",
        "exclusiveMinimum",
        "maxItems",
        "maxLength",
        "maximum",
        "minItems",
        "minLength",
        "minimum",
        "multipleOf",
        "pattern",
    }
    result = {
        key: _named(value) if key in {"$defs", "properties"} else _strict(value)
        for key, value in node.items()
        if key not in unsupported
    }
    properties = result.get("properties")
    if result.get("type") == "object" and isinstance(properties, dict):
        result["additionalProperties"] = False
        result["required"] = list(properties)
    return result


@final
class Shape:
    """JSON schema of an expected answer in the strict form that providers accept for
    constrained output: every object closed and every property required. Constraints that
    providers reject are left out of it and are still checked by pydantic afterwards."""

    __slots__ = ("_schema",)

    def __init__(self, schema: type[BaseModel]) -> None:
        self._schema: Final = schema

    def name(self) -> str:
        return self._schema.__name__

    def strict(self) -> dict[str, object]:
        return _object(self._schema.model_json_schema())

    def instruction(self) -> str:
        return (
            "Ответь одним JSON-объектом, который проходит проверку по JSON-схеме ниже. "
            "Не добавляй пояснений, markdown и текста вне JSON.\nJSON-схема:\n"
            + json.dumps(self.strict(), ensure_ascii=False, sort_keys=True)
        )
