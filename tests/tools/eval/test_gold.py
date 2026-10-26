import random
import uuid
from pathlib import Path

from hamcrest import assert_that, equal_to, has_length, raises

from app.domain.place import Spot
from app.domain.reason import Cause
from app.domain.remark import Note
from app.domain.status import Match, Mismatch, Review
from app.domain.verdict import Ruling
from tools.eval.gold import Case, Folder, Scale


def test_folder_reads_every_line_of_every_file(tmp_path: Path) -> None:
    header = "declaration,shipment,field,status,basis,note\n"
    (tmp_path / "97.csv").write_text(
        f"{header}97,97,sum,mismatch,D-23,\n97,97,cargo,review,fsc-note,x\n", encoding="utf-8"
    )
    (tmp_path / "113.csv").write_text(f"{header}113,113/2,sum,match,fsc-ok,\n", encoding="utf-8")
    assert_that(Folder(tmp_path).samples(), has_length(3), "Folder does not read every line")


def test_folder_keeps_expected_status(tmp_path: Path) -> None:
    (tmp_path / "70.csv").write_text(
        "declaration,shipment,field,status,basis,note\n70,70,sum,review,D-22,валюта\n",
        encoding="utf-8",
    )
    assert_that(
        Folder(tmp_path).samples()[0].status().key(),
        equal_to("review"),
        "Folder does not keep the expected status",
    )


def test_folder_refuses_folder_without_files(tmp_path: Path) -> None:
    assert_that(
        lambda: Folder(tmp_path).samples(),
        raises(FileNotFoundError),
        "Folder does not refuse an empty gold folder",
    )


def test_case_agrees_with_verdict_of_expected_status() -> None:
    shipment = f"{random.randint(1, 999)}/{random.randint(1, 9)}"
    assert_that(
        Case("113", Spot(shipment, "sum"), Mismatch()).agrees(
            Ruling(Spot(shipment, "sum"), Mismatch(), Cause("x", "rule"), Note("", ""))
        ),
        equal_to(True),
        "Case does not accept the expected status in its place",
    )


def test_case_rejects_review_when_it_expects_match() -> None:
    assert_that(
        Case("97", Spot("97", "cargo"), Match()).agrees(
            Ruling(Spot("97", "cargo"), Review(), Cause("x", "llm"), Note("", ""))
        ),
        equal_to(False),
        "Case does not reject review where match is expected",
    )


def test_case_keeps_declaration() -> None:
    declaration = uuid.uuid4().hex
    assert_that(
        Case(declaration, Spot("1", "sum"), Match()).declaration(),
        equal_to(declaration),
        "Case does not keep its declaration",
    )


def test_scale_finds_status_by_key() -> None:
    assert_that(
        Scale().status("mismatch").text(),
        equal_to("не совпадает"),
        "Scale does not find a status by its key",
    )


def test_scale_refuses_unknown_key() -> None:
    assert_that(
        lambda: Scale().status(uuid.uuid4().hex),
        raises(ValueError),
        "Scale does not refuse an unknown status key",
    )
