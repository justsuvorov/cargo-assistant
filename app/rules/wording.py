from collections.abc import Mapping
from typing import Final, Protocol, final

from app.domain.remark import Note, Remark

PLACEHOLDERS = ("reference", "entry", "amount", "limit", "policy_start", "policy_end")


class Wording(Protocol):
    """Comment templates of a card that turn an outcome and its values into a remark."""

    def remark(self, keys: tuple[str, ...], values: Mapping[str, str]) -> Remark: ...


@final
class Comments:
    """Templates of a card keyed by outcome or status; the first key found gives the text.

    Every placeholder that an outcome does not fill becomes an empty string, and the
    reference value becomes the reference of the remark.
    """

    __slots__ = ("_templates",)

    def __init__(self, templates: Mapping[str, str]) -> None:
        self._templates: Final = templates

    def remark(self, keys: tuple[str, ...], values: Mapping[str, str]) -> Remark:
        template = next((self._templates[key] for key in keys if key in self._templates), "")
        filled = {**dict.fromkeys(PLACEHOLDERS, ""), **values}
        return Note(template.format_map(filled), filled["reference"])
