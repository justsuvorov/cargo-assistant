from hamcrest import assert_that, equal_to, raises

from app.storage.errors import EscapeError
from app.storage.relative import Relative


def test_turns_backslashes_into_slashes() -> None:
    assert_that(
        Relative("ДС\\ДС 1\\a.doc").path(),
        equal_to("ДС/ДС 1/a.doc"),
        "Relative does not turn backslashes into slashes",
    )


def test_refuses_parent_segment() -> None:
    assert_that(
        lambda: Relative("ДС/../../x.doc").path(),
        raises(EscapeError),
        "Relative does not refuse a parent segment",
    )


def test_refuses_absolute_path() -> None:
    assert_that(
        lambda: Relative("/etc/x.doc").path(),
        raises(EscapeError),
        "Relative does not refuse an absolute path",
    )


def test_refuses_drive_letter() -> None:
    assert_that(
        lambda: Relative("C:\\x.doc").path(),
        raises(EscapeError),
        "Relative does not refuse a drive letter",
    )


def test_marks_thumbnail_inside_folder_as_service() -> None:
    assert_that(
        Relative("ДС/Thumbs.db").service(),
        equal_to(True),
        "Relative does not mark a thumbnail file as service",
    )


def test_keeps_ordinary_document_out_of_service_files() -> None:
    assert_that(
        Relative("ДС/ДС 1.doc").service(),
        equal_to(False),
        "Relative does not let an ordinary document pass",
    )
