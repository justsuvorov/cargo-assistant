from hamcrest import assert_that, equal_to, raises

from app.domain.status import Match
from app.rules.card import Ruled
from app.rules.errors import CardError
from app.rules.probe import Constant
from app.rules.rows import Rowwise
from app.rules.wording import Comments
from tests.rules.fakes import Mute


def _card() -> Ruled:
    return Ruled(
        "packaging",
        {"vertical": "Род упаковки"},
        "НЕ СВЕРЯЕТСЯ",
        Rowwise("packaging", Constant(Match(), "filled"), Comments({"match": ""}), Mute()),
    )


def test_card_covers_only_its_forms() -> None:
    assert_that(
        (_card().covers("vertical"), _card().covers("psg")),
        equal_to((True, False)),
        "Ruled does not cover exactly the forms of its titles",
    )


def test_card_gives_the_title_of_the_form() -> None:
    assert_that(
        _card().title("vertical"),
        equal_to("Род упаковки"),
        "Ruled does not give the title of the form",
    )


def test_title_of_another_form_fails_loudly() -> None:
    assert_that(
        lambda: _card().title("psg"),
        raises(CardError),
        "Ruled does not fail for a form it does not cover",
    )
