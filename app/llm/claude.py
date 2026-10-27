from collections.abc import Mapping
from typing import Final, final

from pydantic import ValidationError

from app.llm.deadline import Deadline
from app.llm.errors import UnavailableError
from app.llm.messages import Message
from app.llm.provider import Answered, Reply
from app.llm.schema.envelope import Envelope
from app.llm.schema.shape import Shape
from app.llm.wire import Endpoint


@final
class Claude:
    """Backend behind the Anthropic Messages API that constrains the answer by structured
    outputs; it sends no temperature because current Claude models reject any value but the
    default."""

    __slots__ = ("_endpoint", "_model", "_settings", "_tokens")

    def __init__(
        self, endpoint: Endpoint, model: str, tokens: int, settings: Mapping[str, str]
    ) -> None:
        self._endpoint: Final = endpoint
        self._model: Final = model
        self._tokens: Final = tokens
        self._settings: Final = settings

    def reply(self, messages: tuple[Message, ...], shape: Shape, deadline: Deadline) -> Reply:
        text = self._endpoint.post(
            {
                "model": self._model,
                "max_tokens": self._tokens,
                "system": "\n\n".join(
                    (
                        shape.instruction(),
                        *(message.text() for message in messages if message.role() == "system"),
                    )
                ),
                "messages": [
                    {"role": message.role(), "content": message.text()}
                    for message in messages
                    if message.role() != "system"
                ],
                "output_config": {
                    "format": {"type": "json_schema", "schema": shape.strict()},
                    **self._settings,
                },
            },
            deadline,
        )
        try:
            envelope = Envelope.model_validate_json(text)
        except ValidationError as error:
            raise UnavailableError(
                f"Anthropic вернул ответ не в формате Messages API: {text[:300]}"
            ) from error
        return Answered(envelope.text(), envelope.spent())
