from typing import final


@final
class DeniedError(Exception):
    """Request whose caller is unknown, expired or not allowed to do what was asked."""

    __slots__ = ()
