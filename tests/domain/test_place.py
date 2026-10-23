import random
import uuid

from hamcrest import assert_that, equal_to

from app.domain.place import Spot


def test_spots_with_same_row_and_field_are_same() -> None:
    row = f"{random.randint(1, 999)}/{random.randint(1, 99)}"
    field = uuid.uuid4().hex
    assert_that(
        Spot(row, field).same(Spot(row, field)), equal_to(True), "Equal spots are not the same"
    )


def test_spots_with_different_fields_are_not_same() -> None:
    row = str(random.randint(1, 999))
    assert_that(
        Spot(row, uuid.uuid4().hex).same(Spot(row, uuid.uuid4().hex)),
        equal_to(False),
        "Spots of different fields are not told apart",
    )


def test_spots_with_different_rows_are_not_same() -> None:
    field = uuid.uuid4().hex
    assert_that(
        Spot("200/1", field).same(Spot("200/2", field)),
        equal_to(False),
        "Spots of different rows are not told apart",
    )
