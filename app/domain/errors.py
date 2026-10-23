from typing import final


@final
class UnreadableError(Exception):
    """Declared value that the system cannot turn into a date, sum or list."""

    __slots__ = ()


@final
class IncomparableError(Exception):
    """Pair of values that cannot be compared without extra data, such as a currency rate."""

    __slots__ = ()
