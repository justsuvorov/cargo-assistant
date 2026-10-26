import random

from hamcrest import assert_that, equal_to

from app.web.uploads import safe


def test_keeps_plain_file_name() -> None:
    name = f"file{random.randint(1, 999)}.xlsx"
    assert_that(safe(name), equal_to(name), "Plain file name does not stay as it was")


def test_drops_windows_directories_from_file_name() -> None:
    assert_that(
        safe("C:\\Users\\me\\a.xlsx"),
        equal_to("a.xlsx"),
        "Windows directories are not stripped from the file name",
    )


def test_drops_parent_segments_from_file_name() -> None:
    assert_that(
        safe("../../a.xlsx"),
        equal_to("a.xlsx"),
        "Parent segments are not stripped from the file name",
    )
