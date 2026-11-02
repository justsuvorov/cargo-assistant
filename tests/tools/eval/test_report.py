import random
from pathlib import Path

from hamcrest import assert_that, contains_string, equal_to

from app.domain.place import Spot
from app.domain.reason import Cause
from app.domain.remark import Note
from app.domain.status import Match, Mismatch, Review
from app.domain.verdict import Ruling
from tools.eval.gold import Folder
from tools.eval.pipeline import Result, Staged
from tools.eval.report import Excerpt, Report, Tally
from tools.eval.session import Timed


def test_report_counts_correct_answer_by_field(tmp_path: Path) -> None:
    (tmp_path / "97.csv").write_text(
        "declaration,shipment,field,status,basis,note\n97,97,sum,mismatch,D-23,\n"
        "97,97,cargo,review,fsc-note,\n",
        encoding="utf-8",
    )
    verdict = Ruling(Spot("97", "sum"), Mismatch(), Cause("sum.over_limit", "rule"), Note("", ""))
    assert_that(
        Report("x", "v1", Folder(tmp_path), (Timed("97", Result((verdict,), 0, ()), 0.5),)).text(),
        contains_string("| sum | 1 | 1 | 100.0% | 0.0% | 0 |"),
        "Report does not count a correct answer in its field",
    )


def test_report_counts_missing_answer(tmp_path: Path) -> None:
    (tmp_path / "97.csv").write_text(
        "declaration,shipment,field,status,basis,note\n97,97,cargo,review,fsc-note,\n",
        encoding="utf-8",
    )
    assert_that(
        Report("x", "v1", Folder(tmp_path), (Timed("97", Result((), 0, ()), 0.5),)).text(),
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
        Report("x", "v1", Folder(tmp_path), (Timed("274", Result((), calls, ()), 2.0),)).text(),
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
        Report("x", "v1", Folder(tmp_path), (Timed("97", Result((verdict,), 0, ()), 0.1),)).text(),
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
        Report("x", "v1", Folder(tmp_path), (Timed("97", Result((), 0, ()), 0.1),)).text(),
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
        Report("x", "v1", Folder(tmp_path), (Timed("97", Result(verdicts, 0, ()), 0.1),)).text(),
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


def test_tally_spreads_found_and_extra_answers_by_status(tmp_path: Path) -> None:
    (tmp_path / "35.csv").write_text(
        "declaration,shipment,field,status\n35,35/1,sum,match\n35,35/2,sum,mismatch\n"
        "35,35/3,sum,mismatch\n35,35/4,sum,review\n",
        encoding="utf-8",
    )
    answers = {
        "35": tuple(
            Ruling(Spot(shipment, "sum"), status, Cause("x", "rule"), Note("", ""))
            for shipment, status in (
                ("35/1", Mismatch()),
                ("35/2", Mismatch()),
                ("35/3", Match()),
                ("35/4", Review()),
            )
        )
    }
    assert_that(
        Tally(Folder(tmp_path).samples(), answers).spread(),
        equal_to("0/1 | 1 | 1/2 | 1 | 1/1 | 0 |"),
        "Tally does not spread found and extra answers by status",
    )


def test_report_leaves_disputed_lines_out_of_score(tmp_path: Path) -> None:
    (tmp_path / "35.csv").write_text(
        "declaration,shipment,field,status,confidence\n35,35,sum,match,sure\n"
        "35,35,cargo,match,disputed\n",
        encoding="utf-8",
    )
    assert_that(
        Report("x", "v1", Folder(tmp_path), (Timed("35", Result((), 0, ()), 0.1),)).text(),
        contains_string("В расчёте: случаев 1, деклараций 1; спорных строк вне расчёта 1."),
        "Report does not leave disputed lines out of the score",
    )


def test_report_shows_edition_of_gold(tmp_path: Path) -> None:
    (tmp_path / "35.csv").write_text(
        "declaration,shipment,field,status\n35,35,sum,match\n", encoding="utf-8"
    )
    version = f"v{random.randint(2, 99)}, часть dev"
    assert_that(
        Report("x", version, Folder(tmp_path), (Timed("35", Result((), 0, ()), 0.1),)).text(),
        contains_string(f"Эталон: {version}."),
        "Report does not show the version of the gold",
    )


def test_report_lists_answers_beyond_gold(tmp_path: Path) -> None:
    (tmp_path / "35.csv").write_text(
        "declaration,shipment,field,status\n35,35/1,sum,match\n", encoding="utf-8"
    )
    verdicts = tuple(
        Ruling(Spot(shipment, "sum"), Review(), Cause("x", "rule"), Note("", ""))
        for shipment in ("035/1", "035/2")
    )
    assert_that(
        Report("x", "v1", Folder(tmp_path), (Timed("35", Result(verdicts, 0, ()), 0.1),)).text(),
        contains_string("- 35: лишних (1): 035/2 × sum"),
        "Report does not list an answer in a place beyond the gold",
    )


def test_report_lists_faults_of_declaration(tmp_path: Path) -> None:
    (tmp_path / "35.csv").write_text(
        "declaration,shipment,field,status\n35,35,sum,match\n", encoding="utf-8"
    )
    assert_that(
        Report(
            "x", "v1", Folder(tmp_path), (Timed("35", Result((), 0, ("Файл не найден",)), 0.1),)
        ).text(),
        contains_string("- 35: причина: Файл не найден"),
        "Report does not list the faults met on a declaration",
    )


def test_report_crosses_expected_and_given_status_by_field(tmp_path: Path) -> None:
    (tmp_path / "97.csv").write_text(
        "declaration,shipment,field,status\n97,97/1,sum,mismatch\n97,97/2,sum,mismatch\n"
        "97,97/3,sum,mismatch\n",
        encoding="utf-8",
    )
    verdicts = tuple(
        Ruling(Spot(shipment, "sum"), status, Cause("x", "rule"), Note("", ""))
        for shipment, status in (("97/1", Match()), ("97/2", Review()))
    )
    assert_that(
        Report("x", "v1", Folder(tmp_path), (Timed("97", Result(verdicts, 0, ()), 0.1),)).text(),
        contains_string("| sum | не совпадает | 3 | 1 | 0 | 1 | 1 |"),
        "Report does not cross the expected and the given status of a field",
    )


def test_report_counts_reason_codes_by_field(tmp_path: Path) -> None:
    (tmp_path / "97.csv").write_text(
        "declaration,shipment,field,status\n97,97/1,sum,review\n97,97/2,sum,match\n",
        encoding="utf-8",
    )
    verdicts = tuple(
        Ruling(Spot(shipment, "sum"), Review(), Cause("clause.absent", "rule"), Note("", ""))
        for shipment in ("97/1", "97/2")
    )
    assert_that(
        Report("x", "v1", Folder(tmp_path), (Timed("97", Result(verdicts, 0, ()), 0.1),)).text(),
        contains_string("| sum | clause.absent | 2 | 1 |"),
        "Report does not count the reason codes of the answers in a field",
    )


def test_report_shows_stage_seconds_of_declaration(tmp_path: Path) -> None:
    (tmp_path / "97.csv").write_text(
        "declaration,shipment,field,status\n97,97,sum,match\n", encoding="utf-8"
    )
    outcome = Staged(Result((), 0, ()), {"разбор": 0.25, "проверки": 0.125})
    assert_that(
        Report("x", "v1", Folder(tmp_path), (Timed("97", outcome, 0.4),)).text(),
        contains_string("| 0.400 | 0 | разбор 0.250, проверки 0.125 |"),
        "Report does not show the stage seconds of a declaration",
    )


def test_report_sums_up_each_stage(tmp_path: Path) -> None:
    (tmp_path / "97.csv").write_text(
        "declaration,shipment,field,status\n97,97,sum,match\n35,35,sum,match\n", encoding="utf-8"
    )
    laps = (
        Timed("97", Staged(Result((), 0, ()), {"разбор": 0.5}), 0.5),
        Timed("35", Staged(Result((), 0, ()), {"разбор": 1.5}), 1.5),
    )
    assert_that(
        Report("x", "v1", Folder(tmp_path), laps).text(),
        contains_string("Стадия «разбор»: среднее 1.000 с, максимум 1.500 с (декл. 35)."),
        "Report does not sum up the seconds of each stage",
    )


def test_excerpt_scores_only_its_fields(tmp_path: Path) -> None:
    (tmp_path / "97.csv").write_text(
        "declaration,shipment,field,status\n97,97,sum,match\n97,97,cargo,match\n",
        encoding="utf-8",
    )
    verdict = Ruling(Spot("97", "sum"), Match(), Cause("x", "rule"), Note("", ""))
    assert_that(
        Excerpt(
            "Поля без полиса",
            frozenset({"sum"}),
            Folder(tmp_path),
            (Timed("97", Result((verdict,), 0, ()), 0.1),),
        ).text(),
        contains_string("| **Итого** | 1 | 1 | 100.0% | 0.0% | 0 |"),
        "Excerpt does not score only the fields it was given",
    )


def test_excerpt_names_its_fields(tmp_path: Path) -> None:
    (tmp_path / "97.csv").write_text(
        "declaration,shipment,field,status\n97,97,sum,match\n", encoding="utf-8"
    )
    assert_that(
        Excerpt(
            "Поля без полиса",
            frozenset({"sum", "sealing"}),
            Folder(tmp_path),
            (Timed("97", Result((), 0, ()), 0.1),),
        ).text(),
        contains_string("## Поля без полиса\n\nПоля: sealing, sum."),
        "Excerpt does not name the fields it scores",
    )


def test_report_says_when_places_agree(tmp_path: Path) -> None:
    (tmp_path / "35.csv").write_text(
        "declaration,shipment,field,status\n35,35,sum,match\n", encoding="utf-8"
    )
    verdict = Ruling(Spot("35", "sum"), Review(), Cause("x", "rule"), Note("", ""))
    assert_that(
        Report("x", "v1", Folder(tmp_path), (Timed("35", Result((verdict,), 0, ()), 0.1),)).text(),
        contains_string("Расхождений мест нет."),
        "Report does not say that the places of gold and answer agree",
    )
