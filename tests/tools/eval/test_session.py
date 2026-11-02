import random
import uuid
from pathlib import Path
from typing import Final, final

from hamcrest import assert_that, contains_exactly, equal_to

from app.domain.place import Spot
from app.domain.reason import Cause
from app.domain.remark import Note
from app.domain.status import Review
from app.domain.verdict import Ruling
from tools.eval.gold import Folder
from tools.eval.pipeline import Outcome, Result, Staged, Uniform
from tools.eval.session import Session, Timed


@final
class _Fixed:
    __slots__ = ("_outcomes",)

    def __init__(self, outcomes: dict[str, Outcome]) -> None:
        self._outcomes: Final = outcomes

    def reconcile(self, declaration: str) -> Outcome:
        return self._outcomes[declaration]


def test_session_compares_shipment_numbers_by_digits(tmp_path: Path) -> None:
    (tmp_path / "70.csv").write_text(
        "declaration,shipment,field,status\n70,70,sum,review\n", encoding="utf-8"
    )
    verdict = Ruling(Spot("070", "sum"), Review(), Cause("x", "rule"), Note("", ""))
    assert_that(
        Session(Folder(tmp_path), _Fixed({"70": Result((verdict,), 0, ())}))
        .laps()[0]
        .verdicts()[0]
        .place()
        .same(Spot("70", "sum")),
        equal_to(True),
        "Session does not compare shipment numbers of verdicts by their digits",
    )


def test_session_keeps_faults_of_pipeline(tmp_path: Path) -> None:
    (tmp_path / "70.csv").write_text(
        "declaration,shipment,field,status\n70,70,sum,review\n", encoding="utf-8"
    )
    fault = uuid.uuid4().hex
    assert_that(
        Session(Folder(tmp_path), _Fixed({"70": Result((), 0, (fault,))})).laps()[0].faults(),
        equal_to((fault,)),
        "Session does not keep the faults of the pipeline",
    )


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
        Timed("274", Result((), 3, ()), seconds).seconds(),
        equal_to(seconds),
        "Timed lap does not keep the measured seconds",
    )


def test_session_keeps_stages_of_pipeline(tmp_path: Path) -> None:
    (tmp_path / "70.csv").write_text(
        "declaration,shipment,field,status\n70,70,sum,review\n", encoding="utf-8"
    )
    seconds = random.uniform(0.1, 5.0)
    assert_that(
        Session(Folder(tmp_path), _Fixed({"70": Staged(Result((), 0, ()), {"разбор": seconds})}))
        .laps()[0]
        .stages(),
        equal_to({"разбор": seconds}),
        "Session does not keep the stage seconds of the pipeline",
    )


def test_timed_lap_keeps_model_calls() -> None:
    calls = random.randint(1, 9)
    assert_that(
        Timed("274", Result((), calls, ()), 1.0).calls(),
        equal_to(calls),
        "Timed lap does not keep model calls",
    )
