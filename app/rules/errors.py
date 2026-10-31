from typing import final


@final
class CardError(Exception):
    """Rule card that cannot be read, does not follow the card schema or cannot serve a form."""

    __slots__ = ()
