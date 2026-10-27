from pydantic import BaseModel, Field


class Point(BaseModel):
    """Answer with one number."""

    n: int


class Cargo(BaseModel):
    """Answer that names a cargo and counts its pieces."""

    name: str
    pieces: int


class Journey(BaseModel):
    """Answer with the two ends of a route."""

    departure: str
    arrival: str


class Sum(BaseModel):
    """Answer with a total."""

    total: int


class Match(BaseModel):
    """Answer that tells whether two values mean the same."""

    same: bool


class Cover(BaseModel):
    """Answer that tells whether a cargo falls under a clause."""

    covered: bool


class Place(BaseModel):
    """Nested object whose property is named like a schema constraint."""

    city: str
    minimum: int = Field(default=0, ge=0)


class Shipment(BaseModel):
    """Answer with a nested object, numeric constraints and a default."""

    place: Place
    pieces: int = Field(ge=1, le=1000)
    note: str = ""
