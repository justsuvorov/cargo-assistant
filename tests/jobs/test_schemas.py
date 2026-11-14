import random
import uuid

from hamcrest import assert_that, contains_string, equal_to, raises

from app.jobs.errors import SchemaVersionError
from app.jobs.schemas import Upgraded


class Renaming:
    """Test double named renaming: the version 0 called the insurer a holder."""

    def source(self) -> int:
        return 0

    def apply(self, body: dict[str, object]) -> dict[str, object]:
        old = dict(body)
        old["insurer"] = old.pop("holder")
        return old


def body(**extra: object) -> dict[str, object]:
    return {
        "number": uuid.uuid4().hex,
        "issued": "2026-01-01",
        "insurer": uuid.uuid4().hex,
        "clauses": {},
        **extra,
    }


def test_reads_a_profile_saved_without_a_version_as_the_first_one() -> None:
    assert_that(
        Upgraded(body()).profile().schema_version,
        equal_to(1),
        "Profile saved before the version existed is not read as version 1",
    )


def test_reads_a_profile_of_an_earlier_version_through_the_step() -> None:
    insurer = uuid.uuid4().hex
    old = {k: v for k, v in body(schema_version=0, holder=insurer).items() if k != "insurer"}
    assert_that(
        Upgraded(old, (Renaming(),)).profile().insurer,
        equal_to(insurer),
        "Profile of version 0 with the renamed field is not read after the schema change",
    )


def test_refuses_a_profile_of_a_newer_version() -> None:
    assert_that(
        lambda: Upgraded(body(schema_version=random.randint(2, 9))).profile(),
        raises(SchemaVersionError, "версии"),
        "Profile of an unknown newer version is not refused",
    )


def test_refuses_an_earlier_version_without_a_step() -> None:
    assert_that(
        lambda: Upgraded(body(schema_version=0)).profile(),
        raises(SchemaVersionError),
        "Profile of an earlier version without a step is not refused",
    )


def test_refuses_a_version_that_is_not_a_number() -> None:
    assert_that(
        lambda: Upgraded(body(schema_version="abc")).profile(),
        raises(SchemaVersionError, "не число"),
        "Version that is not a number is not refused",
    )


def test_names_the_versions_in_the_error() -> None:
    try:
        Upgraded(body(schema_version=7)).profile()
    except SchemaVersionError as error:
        message = str(error)
    assert_that(
        message,
        contains_string("7"),
        "Error does not name the unknown version",
    )
