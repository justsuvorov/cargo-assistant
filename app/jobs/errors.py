from typing import final


@final
class WaitingError(Exception):
    """Job that cannot go on until something happens outside it, such as an approved profile."""

    __slots__ = ()


@final
class MissingProfileError(Exception):
    """Policy that has no profile yet or does not exist."""

    __slots__ = ()


@final
class NotReadyError(Exception):
    """Profile that cannot be approved because requisites are missing or it is out of date."""

    __slots__ = ()
