from typing import final


@final
class UnreadableError(Exception):
    """Declared value that the system cannot turn into a date, sum or list."""

    __slots__ = ()


@final
class IncomparableError(Exception):
    """Pair of values that cannot be compared without extra data, such as a currency rate."""

    __slots__ = ()


@final
class UnboundError(Exception):
    """Clause asked of a declaration that is bound to no policy; the message is the reason code
    of the binding, such as policy_unknown, so that a card asks a person and names the reason."""

    __slots__ = ()
