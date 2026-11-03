from typing import final


@final
class EscapeError(Exception):
    """Storage key or file name that would leave the place it is meant to stay in."""

    __slots__ = ()


@final
class BrokenError(Exception):
    """Uploaded archive that cannot be opened or is too large to unpack safely."""

    __slots__ = ()
