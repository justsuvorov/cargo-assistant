import random

from hamcrest import assert_that, equal_to

from app.core.journal import LogJournal


class Lines:
    """Test double named lines."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def info(self, msg: str, *args: object) -> None:
        self.lines.append(msg % args)

    def error(self, msg: str, *args: object) -> None:
        self.lines.append(msg % args)


def test_writes_job_and_declaration_into_info_line() -> None:
    sink = Lines()
    job, declaration = random.randint(1, 999), random.randint(1000, 9999)
    LogJournal(sink).info("Стадия завершена", job, declaration)
    assert_that(
        sink.lines,
        equal_to([f"Стадия завершена, job_id={job}, declaration_id={declaration}"]),
        "Info line does not name the job and the declaration",
    )


def test_writes_job_and_declaration_into_error_line() -> None:
    sink = Lines()
    job = random.randint(1, 999)
    LogJournal(sink).error("Задача упала", job, 0)
    assert_that(
        sink.lines,
        equal_to([f"Задача упала, job_id={job}, declaration_id=0"]),
        "Error line does not name the job and the declaration",
    )
