from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.policy.schema.profile import Sum


class Passage(BaseModel):
    """One condition that the model found in a document, under a key of the clause table.

    It holds no requisite of the document: amendment number, entry into force and scope are
    read by code, so an answer that states them fails validation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: Literal[
        "insurer",
        "number",
        "term",
        "term_extension",
        "limit",
        "object",
        "exclusions_cargo",
        "transport",
        "territory",
        "exclusions_territory",
        "beneficiary",
        "carrier_risk",
    ]
    point: str = Field(pattern=r"^(\d+(\.\d+)*\.?)?$")
    text: str
    dates: tuple[date, ...]
    amounts: tuple[Sum, ...]
    entries: tuple[str, ...]

    @field_validator("point")
    @classmethod
    def bare(cls, value: str) -> str:
        return value.rstrip(".")


class Reading(BaseModel):
    """Answer of the model about one document of a policy package."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    passages: tuple[Passage, ...]
