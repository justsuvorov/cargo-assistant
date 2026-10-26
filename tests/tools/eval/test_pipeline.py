import random
from pathlib import Path

from hamcrest import assert_that, equal_to, has_length

from app.domain.status import Match, Review
from tools.eval.gold import Folder
from tools.eval.pipeline import Result, Uniform


def test_uniform_answers_every_gold_place_of_declaration(tmp_path: Path) -> None:
    (tmp_path / "113.csv").write_text(
        "declaration,shipment,field,status,basis,note\n"
        "113,113/1,sum,match,fsc-ok,\n113,113/2,sum,mismatch,fsc-ok,\n114,114/1,sum,match,fsc-ok,\n",
        encoding="utf-8",
    )
    assert_that(
        Uniform(Folder(tmp_path), Review()).reconcile("113").verdicts(),
        has_length(2),
        "Uniform does not answer exactly the places of the declaration",
    )


def test_uniform_gives_its_status(tmp_path: Path) -> None:
    (tmp_path / "97.csv").write_text(
        "declaration,shipment,field,status,basis,note\n97,97,sum,mismatch,D-23,\n",
        encoding="utf-8",
    )
    assert_that(
        Uniform(Folder(tmp_path), Match()).reconcile("97").verdicts()[0].status().key(),
        equal_to("match"),
        "Uniform does not give its status",
    )


def test_uniform_never_calls_model(tmp_path: Path) -> None:
    (tmp_path / "97.csv").write_text(
        "declaration,shipment,field,status,basis,note\n97,97,sum,mismatch,D-23,\n",
        encoding="utf-8",
    )
    assert_that(
        Uniform(Folder(tmp_path), Review()).reconcile("97").calls(),
        equal_to(0),
        "Uniform does not report zero model calls",
    )


def test_result_keeps_model_calls() -> None:
    calls = random.randint(1, 50)
    assert_that(Result((), calls).calls(), equal_to(calls), "Result does not keep model calls")
