from typing import Final, Protocol, final


class Place(Protocol):
    """Cell of the result: one shipment row, such as 200 or 200/3, and one field."""

    def shipment(self) -> str: ...

    def field(self) -> str: ...

    def same(self, other: "Place") -> bool: ...


@final
class Spot:
    """Shipment row number and field key that together locate a check."""

    __slots__ = ("_field", "_shipment")

    def __init__(self, shipment: str, field: str) -> None:
        self._shipment: Final = shipment
        self._field: Final = field

    def shipment(self) -> str:
        return self._shipment

    def field(self) -> str:
        return self._field

    def same(self, other: Place) -> bool:
        return other.shipment() == self._shipment and other.field() == self._field
