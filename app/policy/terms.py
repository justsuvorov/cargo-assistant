import re
from datetime import date
from typing import Final, Protocol, final

from app.policy.stated import Stated

_SIGN = r"(?:№|\bNo\.?)"
_ITEM = r"[^\W_]*-?\d[\w-]*"
_LEAD = (
    r"(?:\bпо|\bк|\bна|\bunder|\bfor|\bto)\s+(?:деклараци\w*|декл\b\.?|declarations?)(?:\s+об\s+отгрузке)?\s*"
    rf"(?P<sign>{_SIGN})?\s*"
)
_SCOPE = re.compile(
    rf"{_LEAD}(?P<list>{_ITEM}(?:\s*(?:,|;|и|and)\s*(?:{_SIGN})?\s*{_ITEM})*)?",
    re.IGNORECASE,
)
_ATTACHED = re.compile(
    rf"(?:\bприложени\w*|\battachment|\bannex)\s*(?:{_SIGN})?\s*\d+\s*[-–—:]\s*"
    rf"(?:деклараци\w*|declaration)\s*{_SIGN}\s*(?P<item>{_ITEM})",
    re.IGNORECASE,
)
_EFFECT = re.compile(
    r"(?:вступает\s+в\s+силу|enters\s+into\s+force|comes\s+into\s+(?:force|effect))([^\n]*)",
    re.IGNORECASE,
)
_VALIDITY = re.compile(r"и\s+действует|действует|\band\b|\bvalid", re.IGNORECASE)
_SEPARATOR = re.compile(rf"\s*(?:,|;|и|and)\s*(?:{_SIGN})?\s*", re.IGNORECASE)


class Agreed(Protocol):
    """Dates and scope that an amendment states in its text, each read by code."""

    def signed(self) -> tuple[date, ...]: ...

    def effective(self) -> tuple[date, ...]: ...

    def scope(self) -> tuple[str, ...]: ...

    def written(self) -> tuple[str, ...]: ...

    def attached(self) -> tuple[str, ...]: ...

    def unclear(self) -> bool: ...


@final
class Terms:
    """Signing date, entry into force and declarations of an amendment read from its text.

    The signing date stands on the first line after the title that does not name the policy.
    The entry into force is the first date after the words about it, before the words about
    validity. The scope follows the words "under declarations" and joins them with the
    declarations that attachments name, once each. Whatever cannot be read stays empty: a draft has
    no dates, and a scope with a blank declaration number is unclear.
    """

    __slots__ = ("_text",)

    def __init__(self, text: str) -> None:
        self._text: Final = text

    def signed(self) -> tuple[date, ...]:
        lines = [line for line in self._text.splitlines() if line.strip()][1:3]
        return Stated(
            next((line for line in lines if not re.search("полис|polic", line, re.I)), "")
        ).dates()[:1]

    def effective(self) -> tuple[date, ...]:
        found = _EFFECT.search(self._text)
        return Stated(_VALIDITY.split(found[1], 1)[0] if found else "").dates()[:1]

    def scope(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(self.written() + self.attached()))

    def written(self) -> tuple[str, ...]:
        return tuple(
            token
            for found in self._named()
            if found["list"]
            for token in _SEPARATOR.split(found["list"])
        )

    def attached(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(found["item"] for found in _ATTACHED.finditer(self._text)))

    def unclear(self) -> bool:
        return any(not found["list"] for found in self._named())

    def _named(self) -> tuple[re.Match[str], ...]:
        return tuple(
            found for found in _SCOPE.finditer(self._text) if found["list"] or found["sign"]
        )[:1]
