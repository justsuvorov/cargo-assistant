import random

from hamcrest import assert_that, contains_exactly, equal_to

from tools.lint.script import Code


def test_code_finds_comment_with_its_line() -> None:
    line = random.randint(2, 9)
    assert_that(
        Code("app/x.py", "x = 1\n" * (line - 1) + "y = 2  # note\n").comments(),
        contains_exactly((line, "# note")),
        "Code does not find the comment on its line",
    )


def test_code_skips_hash_inside_string() -> None:
    assert_that(
        Code("app/x.py", "x = '# not a comment'\n").comments(),
        equal_to(()),
        "Code does not tell a string from a comment",
    )


def test_code_matches_glob_across_folders() -> None:
    assert_that(
        Code("app/declarations/schema/row.py", "").matches("app/*/schema/*"),
        equal_to(True),
        "Code does not match a glob across folders",
    )


def test_code_marks_message_with_path_and_line() -> None:
    assert_that(
        Code("app/domain/status.py", "").mark(7, "плохо"),
        equal_to("app/domain/status.py:7: плохо"),
        "Code does not prefix messages with path and line",
    )


def test_code_keeps_its_path() -> None:
    assert_that(Code("tools/a.py", "").path(), equal_to("tools/a.py"), "Code does not keep path")


def test_code_splits_lines() -> None:
    assert_that(Code("a.py", "a\nb\n").lines(), equal_to(("a", "b")), "Code does not split lines")


def test_code_parses_tree() -> None:
    assert_that(len(Code("a.py", "a = 1\n").tree().body), equal_to(1), "Code does not parse")
