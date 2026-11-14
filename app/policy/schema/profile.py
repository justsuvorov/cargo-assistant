from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Sum(BaseModel):
    """Amount of money in a clause: exact value and ISO currency code."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: Decimal
    currency: str


class Wording(BaseModel):
    """One revision of a clause: where it comes from, since when and for which declarations.

    The point is the number of the policy paragraph it words, such as 12.5; it replaces only
    that paragraph and those nested in it, and an empty point stands for the whole clause.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    point: str = ""
    amendment: int = 0
    effective: date
    scope: Literal["all"] | tuple[str, ...] = "all"
    text: str = ""
    dates: tuple[date, ...] = ()
    amounts: tuple[Sum, ...] = ()
    entries: tuple[str, ...] = ()


class Profile(BaseModel):
    """Policy profile as stored and approved: clauses by key, each a list of revisions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 1
    number: str
    issued: date
    insurer: str
    clauses: dict[str, tuple[Wording, ...]]
    conditions: tuple[str, ...] = ()
    problems: tuple[str, ...] = ()
