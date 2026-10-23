import uuid

from hamcrest import assert_that, equal_to

from app.domain.reason import Cause


def test_cause_keeps_its_code() -> None:
    code = f"period.{uuid.uuid4().hex}"
    assert_that(Cause(code, "rule").code(), equal_to(code), "Cause does not keep its code")


def test_cause_keeps_its_source() -> None:
    assert_that(
        Cause(uuid.uuid4().hex, "llm").source(), equal_to("llm"), "Cause does not keep its source"
    )
