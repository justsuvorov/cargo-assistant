from typing import final


@final
class EscapeError(Exception):
    """Storage key or file name that would leave the place it is meant to stay in."""

    __slots__ = ()
