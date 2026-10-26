from datetime import UTC, datetime, timedelta

from hamcrest import assert_that, equal_to

from app.core.clock import Utc


def test_reports_current_utc_time_without_zone() -> None:
    now = Utc().now()
    assert_that(
        abs(now - datetime.now(UTC).replace(tzinfo=None)) < timedelta(seconds=5)
        and now.tzinfo is None,
        equal_to(True),
        "Clock does not return current UTC time without a zone",
    )
