import uuid

from hamcrest import assert_that, equal_to

from app.jobs.conditioning import Listed
from app.policy.conditions import Found
from app.policy.outcome import Result


def test_tells_rows_notes_and_table_of_conditions_by_priority() -> None:
    text = uuid.uuid4().hex
    listed = Listed(
        Result(
            (Found(text, "файл клиента", prevails=True), Found("б", "общий", prevails=False)), ()
        ),
        (),
    )
    assert_that(
        (listed.rows(), listed.notes()[0], listed.table()[1]),
        equal_to(
            (
                ((text, "файл клиента", "выше"), ("б", "общий", "обычный")),
                f"{text} (источник: файл клиента; приоритет: выше)",
                ["б", "общий", "обычный"],
            )
        ),
        "Listed does not tell the conditions with their source and priority",
    )


def test_keeps_the_reasons_of_the_lookup_and_of_the_client_file() -> None:
    first, second = uuid.uuid4().hex, uuid.uuid4().hex
    assert_that(
        Listed(Result((), (first,)), (second,)).problems(),
        equal_to((first, second)),
        "Listed does not keep the reasons of the lookup and of the file of the client",
    )
