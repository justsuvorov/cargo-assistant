from pydantic import BaseModel, Field


class Block(BaseModel):
    """Content block of an Anthropic answer; only text blocks carry the answer."""

    type: str
    text: str = ""


class Tokens(BaseModel):
    """Token counts of an Anthropic answer."""

    input_tokens: int = 0
    output_tokens: int = 0


class Envelope(BaseModel):
    """Body of an Anthropic Messages API answer."""

    content: list[Block] = Field(default_factory=list)
    usage: Tokens = Field(default_factory=Tokens)
    stop_reason: str | None = None

    def text(self) -> str:
        return "".join(block.text for block in self.content if block.type == "text")

    def truncated(self) -> bool:
        return self.stop_reason == "max_tokens"

    def spent(self) -> tuple[int, int]:
        return self.usage.input_tokens, self.usage.output_tokens
