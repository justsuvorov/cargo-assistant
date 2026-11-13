from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Judgement(BaseModel):
    """Answer of the model about one declared value: its number, a status and a short comment."""

    model_config = ConfigDict(extra="forbid")

    id: int
    status: Literal["match", "mismatch", "review"]
    comment: str = Field(min_length=1, max_length=200)


class Judgements(BaseModel):
    """Answer of the model about all values of one batch, one judgement per value."""

    model_config = ConfigDict(extra="forbid")

    answers: list[Judgement]
