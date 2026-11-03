from pathlib import Path
from typing import Final, Protocol, final

from app.domain.errors import UnreadableError
from app.policy.amendments import Amendments
from app.policy.assembled import Assembled, Listed
from app.policy.layout import Layout
from app.policy.listing import Listing
from app.policy.package import Package
from app.policy.policies import Policies


class Packaged(Protocol):
    """Folder of a policy that can be read into a package."""

    def package(self) -> Package: ...


@final
class Directory:
    """Folder of one policy: the policy and attachments, a folder DS, special conditions, carriers.

    Reading needs no model. The kind of a document and the number, entry into force and scope of
    an amendment come from its text. Whatever cannot be settled is named in problems; a folder
    without the text of the general policy is an error.
    """

    __slots__ = ("_root",)

    def __init__(self, root: Path) -> None:
        self._root: Final = root

    def package(self) -> Package:
        if not self._root.is_dir():
            raise UnreadableError(f"Папка полиса {self._root.name} не найдена")
        layout = Layout(self._root)
        policy = Policies(layout.policies(), self._root).survey()
        amendments = Amendments(layout.amendments(), self._root).survey()
        conditions = Listing(layout.conditions(), self._root).survey()
        carriers = Listing(layout.carriers(), self._root).survey()
        return Assembled(
            policy.items()[0],
            amendments.items(),
            Listed(conditions.items(), carriers.items()),
            policy.problems() + amendments.problems() + conditions.problems() + carriers.problems(),
        )
