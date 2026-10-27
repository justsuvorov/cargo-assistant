from typing import final


@final
class UnavailableError(Exception):
    """Model that gave no usable answer: the network failed, retries ran out or it refused."""

    __slots__ = ()


@final
class MalformedError(Exception):
    """Answer of the model that twice failed validation against the expected JSON schema."""

    __slots__ = ()


@final
class MisconfiguredError(Exception):
    """Settings of the model client that cannot work, found when the client is assembled."""

    __slots__ = ()


@final
class TransientError(Exception):
    """Failure of one request to the model that is worth repeating after a pause."""

    __slots__ = ()
