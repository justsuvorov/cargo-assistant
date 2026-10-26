import random
import string

from hamcrest import assert_that, contains_exactly, equal_to

from app.ingest.book import Folder, Page, Series, Written


def _word() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=8))


def test_written_text_drops_non_breaking_spaces_and_escaped_breaks() -> None:
    word = _word()
    assert_that(
        Written(0, f" {word}\xa0{word}_x000D_\r\n").text(),
        equal_to(f"{word} {word}"),
        "Written text does not drop non-breaking spaces and escaped breaks",
    )


def test_series_hides_cells_with_empty_text() -> None:
    word = _word()
    assert_that(
        Series(3, (Written(0, "  "), Written(2, word))).text(2),
        equal_to(word),
        "Series does not return text of the filled cell",
    )


def test_series_returns_empty_text_for_absent_column() -> None:
    assert_that(
        Series(1, (Written(0, _word()),)).text(5),
        equal_to(""),
        "Series does not return empty text for a column without a cell",
    )


def test_series_lists_texts_after_a_column_in_order() -> None:
    first, second = _word(), _word()
    assert_that(
        Series(1, (Written(0, _word()), Written(4, first), Written(7, second))).after(0),
        contains_exactly(first, second),
        "Series does not list texts to the right of the column in order",
    )


def test_page_drops_lines_without_text() -> None:
    word = _word()
    assert_that(
        len(Page("x", (Series(1, (Written(0, " "),)), Series(2, (Written(0, word),)))).lines()),
        equal_to(1),
        "Page does not drop lines whose cells are all empty",
    )


def test_folder_returns_its_sheets() -> None:
    name = _word()
    assert_that(
        Folder((Page(name, ()),)).sheets()[0].name(),
        equal_to(name),
        "Folder does not return the sheet it was given",
    )
