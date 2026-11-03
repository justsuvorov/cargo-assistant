import random
from contextlib import suppress
from pathlib import Path

from hamcrest import assert_that, equal_to, raises

from app.storage.disk import DiskStorage
from app.storage.errors import EscapeError


def test_returns_saved_bytes_by_key(tmp_path: Path) -> None:
    storage = DiskStorage(tmp_path)
    data = random.randbytes(32)
    storage.save("declarations/7/source/a.xlsx", data)
    assert_that(
        storage.read("declarations/7/source/a.xlsx"),
        equal_to(data),
        "Saved bytes are not returned by the same key",
    )


def test_refuses_key_with_parent_segments(tmp_path: Path) -> None:
    assert_that(
        lambda: DiskStorage(tmp_path / "root").save("policies/../../outside.txt", b"x"),
        raises(EscapeError),
        "Key leaving the root is not refused",
    )


def test_leaves_no_file_outside_root_after_refusal(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    with suppress(EscapeError):
        DiskStorage(root).save("../outside.txt", b"x")
    assert_that(
        (tmp_path / "outside.txt").exists(),
        equal_to(False),
        "File does not stay inside the storage root",
    )


def test_refuses_absolute_key(tmp_path: Path) -> None:
    outside = tmp_path / "other" / "file.txt"
    assert_that(
        lambda: DiskStorage(tmp_path / "root").read(str(outside)),
        raises(EscapeError),
        "Absolute key is not refused",
    )


def test_refuses_backslash_traversal(tmp_path: Path) -> None:
    assert_that(
        lambda: DiskStorage(tmp_path).read("a\\..\\..\\b.txt"),
        raises(EscapeError),
        "Backslash traversal is not refused",
    )


def test_refuses_key_equal_to_root(tmp_path: Path) -> None:
    assert_that(
        lambda: DiskStorage(tmp_path).read("."),
        raises(EscapeError),
        "Key pointing at the root itself is not refused",
    )


def test_reports_removed_file_as_missing(tmp_path: Path) -> None:
    storage = DiskStorage(tmp_path)
    storage.save("k/a.txt", b"x")
    storage.remove("k/a.txt")
    assert_that(
        storage.exists("k/a.txt"),
        equal_to(False),
        "Removed file is not reported as missing",
    )


def test_exports_files_under_prefix_with_relative_paths(tmp_path: Path) -> None:
    storage = DiskStorage(tmp_path / "root")
    data = random.randbytes(16)
    storage.save("policies/1/documents/ДС/1/a.doc", data)
    storage.save("policies/2/documents/b.doc", b"x")
    storage.export("policies/1/documents", tmp_path / "out")
    assert_that(
        (tmp_path / "out" / "ДС" / "1" / "a.doc").read_bytes(),
        equal_to(data),
        "Export does not keep the relative path of a file",
    )
