import random
from pathlib import Path

from hamcrest import assert_that, equal_to

from app.jobs.versions import Fingerprint, Stamp


def test_keeps_the_four_versions_it_was_given() -> None:
    parts = [str(random.random()) for _ in range(4)]
    stamp = Stamp(*parts)
    assert_that(
        [stamp.code(), stamp.cards(), stamp.prompts(), stamp.model()],
        equal_to(parts),
        "Stamp does not return the versions it was given",
    )


def test_gives_the_same_digest_for_the_same_files(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text("x", encoding="utf-8")
    assert_that(
        Fingerprint(tmp_path).hex(),
        equal_to(Fingerprint(tmp_path).hex()),
        "Digest of an unchanged folder does not stay the same",
    )


def test_changes_the_digest_when_a_file_changes(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text("x", encoding="utf-8")
    before = Fingerprint(tmp_path).hex()
    (tmp_path / "a.yaml").write_text("y", encoding="utf-8")
    assert_that(
        before == Fingerprint(tmp_path).hex(),
        equal_to(False),
        "Digest does not change when a file changes",
    )


def test_gives_empty_digest_for_missing_folder(tmp_path: Path) -> None:
    assert_that(
        Fingerprint(tmp_path / "absent").hex(),
        equal_to(""),
        "Digest of a missing folder is not empty",
    )
