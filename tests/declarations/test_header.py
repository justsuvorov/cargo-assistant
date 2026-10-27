from hamcrest import assert_that, equal_to, raises

from app.declarations.header import Title
from app.domain.errors import UnreadableError
from app.ingest.book import Page, Series, Written


def _page(*lines: tuple[str, ...]) -> Page:
    return Page(
        "sheet",
        tuple(
            Series(number, tuple(Written(column, text) for column, text in enumerate(texts)))
            for number, texts in enumerate(lines, start=1)
        ),
    )


def test_number_is_read_from_a_separate_cell_next_to_the_title_word() -> None:
    assert_that(
        Title(_page(("Декларация", "", "", "№ 0315", "об отгрузке"))).number(),
        equal_to("0315"),
        "Title does not read the number from the cell next to the title word",
    )


def test_number_drops_the_letter_prefix() -> None:
    assert_that(
        Title(_page(("Декларация", "", "", "№ Р-005", "об отгрузке"))).number(),
        equal_to("005"),
        "Title does not drop the letter prefix of the declaration number",
    )


def test_number_keeps_leading_zeros_from_the_text_of_the_title() -> None:
    assert_that(
        Title(_page(("Декларация № 070 об отгрузке по Генеральному полису",))).number(),
        equal_to("070"),
        "Title does not keep the leading zero of a number written inside the title",
    )


def test_number_is_read_from_the_cell_after_the_number_sign() -> None:
    assert_that(
        Title(_page(("Ежедневная декларация №", "", "", "", "29"))).number(),
        equal_to("29"),
        "Title does not read the number from the cell after the number sign",
    )


def test_number_is_read_from_a_long_daily_title() -> None:
    assert_that(
        Title(_page(("Ежедневная декларация от отгрузках № 274", "перевезённых"))).number(),
        equal_to("274"),
        "Title does not read the number from a long daily title",
    )


def test_number_is_read_from_an_english_title() -> None:
    assert_that(
        Title(_page(("Daily declaration No. 12 of shipments",))).number(),
        equal_to("12"),
        "Title does not read the number from an English title",
    )


def test_number_is_not_taken_from_the_notice_that_follows_the_title() -> None:
    assert_that(
        Title(
            _page(
                ("Декларация", "№ 164"),
                ("Настоящим сообщает, что груз по декларации", "№ 1649"),
            )
        ).number(),
        equal_to("164"),
        "Title does not take the number from the title",
    )


def test_number_is_unreadable_without_a_title() -> None:
    assert_that(
        lambda: Title(_page(("Приложение № 2 к Генеральному полису",))).number(),
        raises(UnreadableError, "не найден номер декларации"),
        "Title does not refuse a sheet without a declaration number",
    )


def test_policy_is_read_with_its_number_and_date() -> None:
    title = Title(
        _page(("Приложение", "", "№ 0000X00GR0001 от 14.07.2026 г."), ("Декларация № 1",))
    )
    assert_that(
        (title.policy(), title.citation()),
        equal_to(("0000X00GR0001", "№ 0000X00GR0001 от 14.07.2026 г.")),
        "Title does not read the policy number and the citation",
    )


def test_policy_without_number_sign_is_read() -> None:
    assert_that(
        Title(_page(("0000T00GR0002 от 26.08.2026 г.",))).policy(),
        equal_to("0000T00GR0002"),
        "Title does not read a policy number written without the number sign",
    )


def test_absent_policy_is_empty() -> None:
    assert_that(
        Title(_page(("Декларация № 1",))).policy(),
        equal_to(""),
        "Title invents a policy number that the sheet does not cite",
    )


def test_number_drops_a_spaced_letter_prefix() -> None:
    assert_that(
        Title(_page(("Декларация", "", "", "№ р 050", "об отгрузке"))).number(),
        equal_to("050"),
        "Title does not drop a letter prefix separated by a space",
    )
