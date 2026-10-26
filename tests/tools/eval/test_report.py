import random
from pathlib import Path

from hamcrest import assert_that, contains_string, equal_to

from app.domain.place import Spot
from app.domain.reason import Cause
from app.domain.remark import Note
from app.domain.status import Match, Mismatch, Review
from app.domain.verdict import Ruling
from tools.eval.gold import Folder
from tools.eval.pipeline import Result
from tools.eval.report import Report, Tally
from tools.eval.session import Timed


def test_report_counts_correct_answer_by_field(tmp_path: Path) -> None:
    (tmp_path / "97.csv").write_text(
        "declaration,shipment,field,status,basis,note\n97,97,sum,mismatch,D-23,\n"
        "97,97,cargo,review,fsc-note,\n",
        encoding="utf-8",
    )
    verdict = Ruling(Spot("97", "sum"), Mismatch(), Cause("sum.over_limit", "rule"), Note("", ""))
    assert_that(
        Report("x", Folder(tmp_path), (Timed("97", Result((verdict,), 0), 0.5),)).text(),
        contains_string("| sum | 1 | 1 | 100.0% | 0.0% | 0 |"),
        "Report does not count a correct answer in its field",
    )


def test_report_counts_missing_answer(tmp_path: Path) -> None:
    (tmp_path / "97.csv").write_text(
        "declaration,shipment,field,status,basis,note\n97,97,cargo,review,fsc-note,\n",
        encoding="utf-8",
    )
    assert_that(
        Report("x", Folder(tmp_path), (Timed("97", Result((), 0), 0.5),)).text(),
        contains_string("| cargo | 1 | 0 | 0.0% | 0.0% | 1 |"),
        "Report does not count a gold case without an answer",
    )


def test_report_shows_model_calls_of_declaration(tmp_path: Path) -> None:
    (tmp_path / "274.csv").write_text(
        "declaration,shipment,field,status,basis,note\n274,274/1,sum,match,fsc-ok,\n",
        encoding="utf-8",
    )
    calls = random.randint(1, 9)
    assert_that(
        Report("x", Folder(tmp_path), (Timed("274", Result((), calls), 2.0),)).text(),
        contains_string(f"| 2.000 | {calls} |"),
        "Report does not show time and model calls of a declaration",
    )


def test_report_counts_answers_outside_gold(tmp_path: Path) -> None:
    (tmp_path / "97.csv").write_text(
        "declaration,shipment,field,status,basis,note\n97,97,sum,mismatch,D-23,\n",
        encoding="utf-8",
    )
    verdict = Ruling(Spot("97", "packaging"), Match(), Cause("x", "rule"), Note("", ""))
    assert_that(
        Report("x", Folder(tmp_path), (Timed("97", Result((verdict,), 0), 0.1),)).text(),
        contains_string("Ответов вне эталона: 1."),
        "Report does not count answers for places outside the gold",
    )


def test_report_shows_expected_status_shares(tmp_path: Path) -> None:
    (tmp_path / "97.csv").write_text(
        "declaration,shipment,field,status,basis,note\n97,97,sum,mismatch,D-23,\n"
        "97,97,cargo,match,fsc-ok,\n",
        encoding="utf-8",
    )
    assert_that(
        Report("x", Folder(tmp_path), (Timed("97", Result((), 0), 0.1),)).text(),
        contains_string("«не совпадает» 1 (50.0%)"),
        "Report does not show the share of each expected status",
    )


def test_report_scores_each_expected_status(tmp_path: Path) -> None:
    (tmp_path / "97.csv").write_text(
        "declaration,shipment,field,status,basis,note\n97,97,sum,mismatch,D-23,\n"
        "97,97,cargo,match,fsc-ok,\n97,97,policy,match,fsc-ok,\n",
        encoding="utf-8",
    )
    verdicts = tuple(
        Ruling(Spot("97", field), Match(), Cause("x", "rule"), Note("", ""))
        for field in ("sum", "cargo", "policy")
    )
    assert_that(
        Report("x", Folder(tmp_path), (Timed("97", Result(verdicts, 0), 0.1),)).text(),
        contains_string("| не совпадает | 1 | 0 | 0.0% | 0.0% | 0 |"),
        "Report does not score the cases of each expected status",
    )


def test_tally_counts_review_answers(tmp_path: Path) -> None:
    (tmp_path / "35.csv").write_text(
        "declaration,shipment,field,status,basis,note\n35,35,sum,match,fsc-ok,\n"
        "35,35,cargo,review,fsc-note,\n",
        encoding="utf-8",
    )
    answers = {
        "35": tuple(
            Ruling(Spot("35", field), Review(), Cause("x", "llm"), Note("", ""))
            for field in ("sum", "cargo")
        )
    }
    assert_that(
        Tally(Folder(tmp_path).samples(), answers).doubts(),
        equal_to(2),
        "Tally does not count review answers",
    )


def test_tally_scores_review_only_where_gold_expects_it(tmp_path: Path) -> None:
    (tmp_path / "35.csv").write_text(
        "declaration,shipment,field,status,basis,note\n35,35,sum,match,fsc-ok,\n"
        "35,35,cargo,review,fsc-note,\n",
        encoding="utf-8",
    )
    answers = {
        "35": tuple(
            Ruling(Spot("35", field), Review(), Cause("x", "llm"), Note("", ""))
            for field in ("sum", "cargo")
        )
    }
    assert_that(
        Tally(Folder(tmp_path).samples(), answers).correct(),
        equal_to(1),
        "Tally does not score review only where the gold expects it",
    )
