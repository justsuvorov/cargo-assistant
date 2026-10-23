from typing import Final, Protocol, final


class Remark(Protocol):
    """Short human comment on a check and the policy clause it relied on."""

    def comment(self) -> str: ...

    def reference(self) -> str: ...


@final
class Note:
    """Comment text for the result file together with a clause reference such as п. 6 ГП."""

    __slots__ = ("_comment", "_reference")

    def __init__(self, comment: str, reference: str) -> None:
        self._comment: Final = comment
        self._reference: Final = reference

    def comment(self) -> str:
        return self._comment

    def reference(self) -> str:
        return self._reference
