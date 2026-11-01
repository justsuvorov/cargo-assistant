from hamcrest import assert_that, equal_to

from app.declarations.schema import Fields
from app.domain.place import Spot
from app.domain.policy import Vacant
from app.rules.answers import Replies
from app.rules.modes import Conveyance, Modes
from app.rules.wording import Comments
from tests.rules.fakes import Paper, Text


def _modes() -> Modes:
    return Modes(
        {
            "auto": ("авто", "truck"),
            "rail": ("ж/д", "rail"),
            "air": ("авиа", "air"),
            "mixed": ("смешанный", "mixed"),
        }
    )


def _code(transport: str, allowed: str) -> str:
    return (
        Conveyance(_modes())
        .outcome(
            Fields().field("transport", (transport,)),
            Text("ГП п. 8", allowed),
            Paper("3", "psg", ({"transport": (transport,)},)).shipments()[0],
            Vacant("1"),
        )
        .verdict(
            Spot("3", "transport"),
            Comments({"match": "", "mismatch": "{entry}", "review": ""}),
            Replies((), ()),
        )
        .reason()
        .code()
    )


def test_several_modes_make_a_mixed_carriage() -> None:
    assert_that(
        _modes().mixed("Авто+авиа+авто"),
        equal_to(True),
        "Modes does not see a mixed carriage in several modes",
    )


def test_transshipment_on_the_border_is_only_road() -> None:
    assert_that(
        _modes().mixed("Авто с перегрузом на границе"),
        equal_to(False),
        "Modes does not read a road carriage with a transshipment as one mode",
    )


def test_mixed_word_makes_a_mixed_carriage() -> None:
    assert_that(
        _modes().mixed("Mixed"),
        equal_to(True),
        "Modes does not take the word mixed for a mixed carriage",
    )


def test_mode_is_read_inside_a_longer_word() -> None:
    assert_that(
        _modes().kinds("Автотранспорт, ж/д"),
        equal_to(frozenset({"auto", "rail"})),
        "Modes does not read modes at the start of longer words",
    )


def test_allowed_mode_is_listed() -> None:
    assert_that(
        _code("Truck", "автомобильным и ж/д транспортом"),
        equal_to("transport.listed"),
        "Conveyance does not accept a mode that the clause allows",
    )


def test_forbidden_mode_is_unlisted() -> None:
    assert_that(
        _code("Авто+авиа", "автомобильным транспортом"),
        equal_to("transport.unlisted"),
        "Conveyance does not reject a mode that the clause omits",
    )


def test_unknown_mode_needs_a_person() -> None:
    assert_that(
        _code("КАМАЗ А000АА", "автомобильным транспортом"),
        equal_to("transport.unrecognized"),
        "Conveyance does not ask for review when no mode is recognised",
    )


def test_mismatch_names_the_entry_with_the_forbidden_mode() -> None:
    assert_that(
        Conveyance(_modes())
        .outcome(
            Fields().field("transport", ("Авто+авиа",)),
            Text("ГП п. 8", "авто"),
            Paper("3", "psg", ({"transport": ("Авто+авиа",)},)).shipments()[0],
            Vacant("1"),
        )
        .verdict(
            Spot("3", "transport"),
            Comments({"mismatch": "{entry}"}),
            Replies((), ()),
        )
        .remark()
        .comment(),
        equal_to("авиа"),
        "Conveyance does not name the entry with the forbidden mode",
    )
