from typing import Final, final

from app.domain.clause import Absent, Clause
from app.domain.errors import UnreadableError
from app.domain.revision import Revision
from app.domain.shipment import Shipment
from app.policy.schema.profile import Profile, Wording
from app.policy.wording import Edition, Quoted, Unsettled


@final
class Approved:
    """Policy that answers from a profile confirmed by an expert.

    A clause comes in the one revision that governs the shipment and that no other governing
    revision supersedes. It is absent when none governs. When the start of the shipment is
    unreadable or several revisions stay equal, the clause states no facts and a card asks a
    person. The number, the issue date and the insurer are requisites of the profile, so
    without a clause of that key they need no revision and no shipment date.
    """

    __slots__ = ("_profile",)

    def __init__(self, profile: Profile) -> None:
        self._profile: Final = profile

    def number(self) -> str:
        return self._profile.number

    def clause(self, key: str, shipment: Shipment) -> Clause:
        wordings = tuple(dict.fromkeys(self._profile.clauses.get(key, ())))
        if not wordings:
            return self._requisite(key)
        try:
            governing = tuple(
                edition
                for edition in (Edition(wording, wordings) for wording in wordings)
                if edition.governs(shipment)
            )
        except UnreadableError:
            return Unsettled(
                f"редакцию пункта «{key}» не выбрать: не прочитана дата начала перевозки"
            )
        return self._chosen(key, governing)

    def conditions(self) -> tuple[str, ...]:
        return self._profile.conditions

    def _chosen(self, key: str, governing: tuple[Revision, ...]) -> Clause:
        standing = tuple(
            each
            for each in governing
            if not any(other.supersedes(each) for other in governing if other is not each)
        )
        if not standing:
            return Absent(key)
        if len(standing) > 1:
            sources = ", ".join(each.clause().reference() for each in standing)
            return Unsettled(f"у пункта «{key}» равноправные редакции: {sources}")
        return standing[0].clause()

    def _requisite(self, key: str) -> Clause:
        profile = self._profile
        requisites = {
            "number": (profile.number, (profile.issued,)),
            "insurer": (profile.insurer, ()),
        }
        if key not in requisites:
            return Absent(key)
        text, dates = requisites[key]
        return Quoted(
            Wording(source="ГП, преамбула", effective=profile.issued, text=text, dates=dates)
        )
