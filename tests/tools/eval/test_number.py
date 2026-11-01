import random

from hamcrest import assert_that, equal_to

from app.domain.place import Spot
from app.domain.reason import Cause
from app.domain.remark import Note
from app.domain.status import Mismatch
from app.domain.verdict import Ruling
from tools.eval.number import Aligned, Canonical, Digits


def test_digits_drop_leading_zeros() -> None:
    number = random.randint(1, 999)
    assert_that(
        Digits(f"00{number}").text(),
        equal_to(str(number)),
        "Digits do not drop the leading zeros of a declaration number",
    )


def test_digits_drop_letter_prefix() -> None:
    assert_that(
        Digits("р-050").text(),
        equal_to("50"),
        "Digits do not drop the letter prefix of a declaration number",
    )


def test_digits_reduce_every_part_of_shipment_number() -> None:
    assert_that(
        Digits("070/03").text(),
        equal_to("70/3"),
        "Digits do not reduce each part of a shipment number",
    )


def test_digits_keep_zero() -> None:
    assert_that(Digits("000").text(), equal_to("0"), "Digits do not keep a zero number")


def test_canonical_place_matches_number_with_leading_zeros() -> None:
    assert_that(
        Canonical(Spot("70/1", "sum")).same(Spot("070/1", "sum")),
        equal_to(True),
        "Canonical place does not match a shipment number with leading zeros",
    )


def test_canonical_place_tells_fields_apart() -> None:
    assert_that(
        Canonical(Spot("70", "sum")).same(Spot("70", "cargo")),
        equal_to(False),
        "Canonical place does not tell fields apart",
    )


def test_canonical_place_keeps_written_number() -> None:
    assert_that(
        Canonical(Spot("005", "sum")).shipment(),
        equal_to("005"),
        "Canonical place does not keep the shipment number as written",
    )


def test_aligned_verdict_matches_gold_place_by_digits() -> None:
    verdict = Ruling(Spot("005", "sum"), Mismatch(), Cause("x", "rule"), Note("", ""))
    assert_that(
        Aligned(verdict).place().same(Spot("5", "sum")),
        equal_to(True),
        "Aligned verdict does not match a gold place by the digits of its number",
    )


def test_aligned_verdict_keeps_status() -> None:
    verdict = Ruling(Spot("5", "sum"), Mismatch(), Cause("x", "rule"), Note("", ""))
    assert_that(
        Aligned(verdict).status().key(),
        equal_to("mismatch"),
        "Aligned verdict does not keep the status of the pipeline",
    )
