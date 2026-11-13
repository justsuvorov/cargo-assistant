from typing import Final, Protocol, final

from app.domain.card import Card
from app.domain.declaration import Declaration
from app.domain.policy import Policy
from app.domain.verdict import Verdict
from app.rules.cards import Deck


class Findings(Protocol):
    """Verdicts of one declaration by place and how many places its form has."""

    def verdicts(self) -> tuple[Verdict, ...]: ...

    def expected(self) -> int: ...


@final
class Found:
    """Findings assembled from ready verdicts and the number of places they should fill."""

    __slots__ = ("_expected", "_verdicts")

    def __init__(self, verdicts: tuple[Verdict, ...], expected: int) -> None:
        self._verdicts: Final = verdicts
        self._expected: Final = expected

    def verdicts(self) -> tuple[Verdict, ...]:
        return self._verdicts

    def expected(self) -> int:
        return self._expected


class Reconciliation(Protocol):
    """Reconciliation of a declaration with a policy by the rule cards of its form."""

    def cards(self, form: str) -> tuple[Card, ...]: ...

    def findings(self, declaration: Declaration, policy: Policy) -> Findings: ...


@final
class Carded:
    """Reconciliation by a deck of cards: a shipment row after a shipment row, the cards in
    their order, the first verdict of a place when a card gives several.

    The semantic judge is the one the deck was built with, so the same object serves the
    application and the evaluation of the rules.
    """

    __slots__ = ("_deck",)

    def __init__(self, deck: Deck) -> None:
        self._deck: Final = deck

    def cards(self, form: str) -> tuple[Card, ...]:
        return self._deck.cards(form)

    def findings(self, declaration: Declaration, policy: Policy) -> Findings:
        cards = self._deck.cards(declaration.form())
        given = {
            card.field(): {
                verdict.place().shipment(): verdict
                for verdict in reversed(card.verdicts(declaration, policy))
            }
            for card in cards
        }
        shipments = tuple(dict.fromkeys(each.number() for each in declaration.shipments()))
        return Found(
            tuple(
                given[card.field()][shipment]
                for shipment in shipments
                for card in cards
                if shipment in given[card.field()]
            ),
            len(shipments) * len(cards),
        )
