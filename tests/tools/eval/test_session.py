import random
from pathlib import Path

from hamcrest import assert_that, contains_exactly, equal_to

from app.domain.status import Review
from tools.eval.gold import Folder
from tools.eval.pipeline import Result, Uniform
from tools.eval.session import Session, Timed


def test_session_runs_every_declaration_once(tmp_path: Path) -> None:
    (tmp_path / "113.csv").write_text(
        "declaration,shipment,field,status,basis,note\n"
        "113,113/1,sum,match,fsc-ok,\n113,113/2,sum,match,fsc-ok,\n",
        encoding="utf-8",
    )
    (tmp_path / "97.csv").write_text(
        "declaration,shipment,field,status,basis,note\n97,97,sum,mismatch,D-23,\n",
        encoding="utf-8",
    )
    gold = Folder(tmp_path)
    assert_that(
        [lap.declaration() for lap in Session(gold, Uniform(gold, Review())).laps()],
        contains_exactly("113", "97"),
        "Session does not run every declaration exactly once",
    )


def test_session_keeps_verdicts_of_pipeline(tmp_path: Path) -> None:
    (tmp_path / "113.csv").write_text(
        "declaration,shipment,field,status,basis,note\n"
        "113,113/1,sum,match,fsc-ok,\n113,113/2,sum,match,fsc-ok,\n",
        encoding="utf-8",
    )
    gold = Folder(tmp_path)
    assert_that(
        len(Session(gold, Uniform(gold, Review())).laps()[0].verdicts()),
        equal_to(2),
        "Session does not keep the verdicts of the pipeline",
    )


def test_timed_lap_keeps_seconds() -> None:
    seconds = random.uniform(0.1, 30.0)
    assert_that(
        Timed("274", Result((), 3), seconds).seconds(),
        equal_to(seconds),
        "Timed lap does not keep the measured seconds",
    )


def test_timed_lap_keeps_model_calls() -> None:
    calls = random.randint(1, 9)
    assert_that(
        Timed("274", Result((), calls), 1.0).calls(),
        equal_to(calls),
        "Timed lap does not keep model calls",
    )
