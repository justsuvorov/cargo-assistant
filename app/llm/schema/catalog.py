from pydantic import BaseModel, Field


class Entry(BaseModel):
    """One model in an OpenAI-compatible list of models."""

    id: str


class Catalog(BaseModel):
    """Body of an OpenAI-compatible answer to the request for the list of models."""

    data: list[Entry] = Field(default_factory=list)

    def names(self) -> tuple[str, ...]:
        return tuple(entry.id for entry in self.data)
