from pydantic import BaseModel, Field


class Said(BaseModel):
    """Message of an OpenAI-compatible answer whose content is null when the model spent its
    whole budget on reasoning."""

    content: str | None = None


class Choice(BaseModel):
    """One variant of an OpenAI-compatible answer."""

    message: Said = Field(default_factory=Said)
    finish_reason: str | None = None


class Usage(BaseModel):
    """Token counts of an OpenAI-compatible answer."""

    prompt_tokens: int = 0
    completion_tokens: int = 0


class Completion(BaseModel):
    """Body of an OpenAI-compatible chat completions answer, as the VSK gateway and Gemini
    return it."""

    choices: list[Choice] = Field(default_factory=list)
    usage: Usage | None = None

    def text(self) -> str:
        return "".join(choice.message.content or "" for choice in self.choices[:1])

    def truncated(self) -> bool:
        return any(choice.finish_reason == "length" for choice in self.choices[:1])

    def spent(self) -> tuple[int, int]:
        usage = self.usage or Usage()
        return usage.prompt_tokens, usage.completion_tokens
