import uuid
from pathlib import Path

from hamcrest import assert_that, contains_exactly, contains_string, equal_to, raises

from tools.eval.entry import Dropped, Open, Settled
from tools.eval.mask import Anonymity
from tools.eval.paper import Cases, Questions, Summary
from tools.eval.sheet import Line


def test_cases_write_one_file_per_declaration(tmp_path: Path) -> None:
    Cases(tmp_path, Anonymity((), ())).write(
        (
            Settled(
                Line("97", ("97", "С", "", "совпадает", "", "верно")), "sum", ("match", "a", "")
            ),
            Settled(
                Line("35", ("35", "С", "", "совпадает", "", "верно")), "sum", ("match", "a", "")
            ),
            Open(Line("35", ("35", "Г", "", "совпадает", "", "x")), "cargo", "y", ""),
        )
    )
    assert_that(
        sorted(path.name for path in tmp_path.iterdir()),
        contains_exactly("35.csv", "97.csv"),
        "Cases do not write exactly one file per declaration with gold lines",
    )


def test_cases_mask_notes(tmp_path: Path) -> None:
    Cases(tmp_path, Anonymity((), ())).write(
        (
            Settled(
                Line("97", ("97", "С", "", "совпадает", "", "верно")),
                "sum",
                ("match", "fsc-note", "по ГП 9999013G00022"),
            ),
        )
    )
    assert_that(
        "9999013G00022" in (tmp_path / "97.csv").read_text(encoding="utf-8"),
        equal_to(False),
        "Cases do not mask a policy number in a note",
    )


def test_cases_refuse_two_lines_for_one_place(tmp_path: Path) -> None:
    line = Line("97", ("97", "С", "", "совпадает", "", "верно"))
    assert_that(
        lambda: Cases(tmp_path, Anonymity((), ())).write(
            (
                Settled(line, "sum", ("match", "a", "")),
                Settled(line, "sum", ("mismatch", "b", "")),
            )
        ),
        raises(ValueError),
        "Cases do not refuse two gold lines for one place",
    )


def test_questions_count_identical_rows(tmp_path: Path) -> None:
    line = Line("114", ("114/4", "Сумма", "", "не совпадает", "", "без комментария"))
    Questions(tmp_path / "q.md", Anonymity((), ())).write(
        (Open(line, "sum", "Ф-19", ""), Open(line, "sum", "Ф-19", ""))
    )
    assert_that(
        (tmp_path / "q.md").read_text(encoding="utf-8"),
        contains_string(
            "| В-1 | 114 | 114/4 | sum | не совпадает | без комментария | Ф-19 | — | 2 |"
        ),
        "Questions do not merge identical rows with their count",
    )


def test_questions_mask_remark(tmp_path: Path) -> None:
    name = f"ООО «{uuid.uuid4().hex}»"
    Questions(tmp_path / "q.md", Anonymity((), ())).write(
        (Open(Line("35", ("35", "Г", "", "совпадает", "", f"а {name}")), "cargo", "y", ""),)
    )
    assert_that(
        name in (tmp_path / "q.md").read_text(encoding="utf-8"),
        equal_to(False),
        "Questions do not mask a company name in a remark",
    )


def test_summary_counts_gold_questions_and_exclusions(tmp_path: Path) -> None:
    Summary(tmp_path / "s.md").write(
        (
            Settled(
                Line("35", ("35", "С", "", "совпадает", "", "верно")), "sum", ("match", "a", "")
            ),
            Open(Line("35", ("35", "Г", "", "совпадает", "", "")), "cargo", "y", ""),
            Dropped(Line("35", ("35", "П", "", "совпадает", "", "x")), "sealing", "D-14"),
        )
    )
    assert_that(
        (tmp_path / "s.md").read_text(encoding="utf-8"),
        contains_string("| 35 | 3 | 2 | 1 | 1 | 1 |"),
        "Summary does not count rows, marks, gold lines, questions and exclusions",
    )
