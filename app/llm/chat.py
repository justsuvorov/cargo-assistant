from typing import Final, Protocol, final

from pydantic import ValidationError

from app.llm.deadline import Deadline
from app.llm.errors import UnavailableError
from app.llm.messages import Message, System
from app.llm.provider import Answered, Cut, Reply
from app.llm.schema.completion import Completion
from app.llm.schema.shape import Shape
from app.llm.wire import Endpoint


class Form(Protocol):
    """Way to ask an OpenAI-compatible endpoint for JSON: the messages and extra body fields."""

    def body(self, shape: Shape, messages: tuple[Message, ...]) -> dict[str, object]: ...


class Transcript(Protocol):
    """Conversation ready to be put into a request body."""

    def wire(self) -> list[dict[str, str]]: ...


@final
class Instructed:
    """Conversation in OpenAI wire format that opens with the instruction to answer in JSON."""

    __slots__ = ("_messages", "_shape")

    def __init__(self, shape: Shape, messages: tuple[Message, ...]) -> None:
        self._shape: Final = shape
        self._messages: Final = messages

    def wire(self) -> list[dict[str, str]]:
        return [
            {"role": message.role(), "content": message.text()}
            for message in (System(self._shape.instruction()), *self._messages)
        ]


@final
class Prompted:
    """Form that only puts the schema into the prompt, for endpoints without constrained output."""

    __slots__ = ()

    def body(self, shape: Shape, messages: tuple[Message, ...]) -> dict[str, object]:
        return {"messages": Instructed(shape, messages).wire()}


@final
class JsonObject:
    """Form that asks for any valid JSON object through response_format json_object."""

    __slots__ = ()

    def body(self, shape: Shape, messages: tuple[Message, ...]) -> dict[str, object]:
        return {
            "messages": Instructed(shape, messages).wire(),
            "response_format": {"type": "json_object"},
        }


@final
class JsonSchema:
    """Form that constrains the answer by response_format json_schema in OpenAI style."""

    __slots__ = ()

    def body(self, shape: Shape, messages: tuple[Message, ...]) -> dict[str, object]:
        return {
            "messages": Instructed(shape, messages).wire(),
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": shape.name(), "schema": shape.strict(), "strict": True},
            },
        }


@final
class GuidedJson:
    """Form that constrains the answer by the guided_json field of vLLM based gateways."""

    __slots__ = ()

    def body(self, shape: Shape, messages: tuple[Message, ...]) -> dict[str, object]:
        return {"messages": Instructed(shape, messages).wire(), "guided_json": shape.strict()}


@final
class Budget:
    """Form that also limits reasoning by the thinking_token_budget field of the VSK gateway."""

    __slots__ = ("_form", "_tokens")

    def __init__(self, tokens: int, form: Form) -> None:
        self._tokens: Final = tokens
        self._form: Final = form

    def body(self, shape: Shape, messages: tuple[Message, ...]) -> dict[str, object]:
        return {**self._form.body(shape, messages), "thinking_token_budget": self._tokens}


@final
class GoogleBudget:
    """Form that also limits reasoning by the thinking budget of the Gemini compatible endpoint."""

    __slots__ = ("_form", "_tokens")

    def __init__(self, tokens: int, form: Form) -> None:
        self._tokens: Final = tokens
        self._form: Final = form

    def body(self, shape: Shape, messages: tuple[Message, ...]) -> dict[str, object]:
        return {
            **self._form.body(shape, messages),
            "extra_body": {"google": {"thinking_config": {"thinking_budget": self._tokens}}},
        }


@final
class Chat:
    """Backend behind an OpenAI-compatible chat completions endpoint with temperature zero."""

    __slots__ = ("_endpoint", "_form", "_model", "_tokens")

    def __init__(self, endpoint: Endpoint, model: str, tokens: int, form: Form) -> None:
        self._endpoint: Final = endpoint
        self._model: Final = model
        self._tokens: Final = tokens
        self._form: Final = form

    def reply(self, messages: tuple[Message, ...], shape: Shape, deadline: Deadline) -> Reply:
        text = self._endpoint.post(
            {
                "model": self._model,
                "max_tokens": self._tokens,
                "temperature": 0,
                **self._form.body(shape, messages),
            },
            deadline,
        )
        try:
            completion = Completion.model_validate_json(text)
        except ValidationError as error:
            raise UnavailableError(
                f"Шлюз вернул ответ не в формате chat completions: {text[:300]}"
            ) from error
        return (Cut if completion.truncated() else Answered)(completion.text(), completion.spent())
