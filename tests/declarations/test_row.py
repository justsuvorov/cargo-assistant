from datetime import date

from hamcrest import assert_that, equal_to, raises

from app.declarations.fields import Dating
from app.declarations.row import Row
from app.declarations.schema import Fields
from app.domain.errors import UnreadableError


def test_row_reads_the_field_from_the_texts_of_its_key() -> None:
    assert_that(
        Row("3", {"cargo": ("мясо, сыр",)}, Fields(), Dating(())).field("cargo").entries(),
        equal_to(("мясо", "сыр")),
        "Row does not read the field from the texts of its key",
    )


def test_row_gives_a_blank_field_for_a_key_without_texts() -> None:
    assert_that(
        Row("3", {}, Fields(), Dating(())).field("cargo").filled(),
        equal_to(False),
        "Row does not give a blank field for a key without texts",
    )


def test_row_starts_on_the_first_date_of_its_start_fact() -> None:
    assert_that(
        Row("3", {}, Fields(), Dating(("21.09.2026",))).start(),
        equal_to(date(2026, 9, 21)),
        "Row does not start on the date of its start fact",
    )


def test_row_without_a_start_date_is_unreadable() -> None:
    assert_that(
        lambda: Row("3", {}, Fields(), Dating(("скоро",))).start(),
        raises(UnreadableError, "в строке 3"),
        "Row does not refuse to start without a readable date",
    )
