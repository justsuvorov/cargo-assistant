from datetime import date

from hamcrest import assert_that, equal_to

from app.domain.clause import Absent
from app.rules.presence import Stated
from tests.rules.fakes import Text


def test_absent_clause_does_not_exist() -> None:
    assert_that(
        Stated(Absent("term_extension")).exists(),
        equal_to(False),
        "Stated does not tell that an absent clause is missing",
    )


def test_clause_with_only_dates_exists() -> None:
    assert_that(
        Stated(Text("ГП п. 6", dates=(date(2026, 1, 1),))).exists(),
        equal_to(True),
        "Stated does not accept a clause that only holds dates",
    )
