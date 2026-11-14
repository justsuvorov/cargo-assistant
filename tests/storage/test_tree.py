from hamcrest import assert_that, contains_inanyorder, equal_to, raises

from app.storage.archive import Blob
from app.storage.errors import EscapeError
from app.storage.tree import Tree


def test_cuts_the_wrapping_folder_shared_by_all_files() -> None:
    files = Tree((Blob("Пакет/ГП.doc", b"1"), Blob("Пакет/ДС/ДС 1.doc", b"2"))).files()
    assert_that(
        [file.name() for file in files],
        contains_inanyorder("ГП.doc", "ДС/ДС 1.doc"),
        "Tree does not cut the wrapping folder",
    )


def test_keeps_paths_when_files_lie_in_different_folders() -> None:
    files = Tree((Blob("ГП.doc", b"1"), Blob("ДС/ДС 1.doc", b"2"))).files()
    assert_that(
        [file.name() for file in files],
        contains_inanyorder("ГП.doc", "ДС/ДС 1.doc"),
        "Tree does not keep paths that need no cutting",
    )


def test_ignores_service_files_when_looking_for_the_wrapping_folder() -> None:
    files = Tree((Blob("Пакет/ГП.doc", b"1"), Blob("Thumbs.db", b"2"))).files()
    assert_that(
        [file.name() for file in files],
        equal_to(["ГП.doc"]),
        "Tree does not cut the folder when a service file lies outside it",
    )


def test_refuses_path_leading_out_of_the_folder() -> None:
    assert_that(
        lambda: Tree((Blob("a/../../b.doc", b"1"),)).files(),
        raises(EscapeError),
        "Tree does not refuse a path leading out",
    )


def test_names_the_wrapping_folder() -> None:
    assert_that(
        Tree((Blob("Пакет/ГП.doc", b"1"), Blob("Пакет/ДС/ДС 1.doc", b"2"))).name(),
        equal_to("Пакет"),
        "Tree does not name the wrapping folder",
    )


def test_gives_blank_name_when_there_is_no_wrapping_folder() -> None:
    assert_that(
        Tree((Blob("ГП.doc", b"1"), Blob("ДС/ДС 1.doc", b"2"))).name(),
        equal_to(""),
        "Tree names a folder that does not wrap the files",
    )
