import random
import time

from hamcrest import assert_that, close_to, equal_to

from app.llm.deadline import Countdown, Rhythm


def test_leaves_whole_time_right_after_start() -> None:
    seconds = random.uniform(100, 200)
    assert_that(
        Countdown(seconds).left(),
        close_to(seconds, 1.0),
        "Fresh deadline does not leave the whole time",
    )


def test_leaves_no_time_after_it_passes() -> None:
    deadline = Countdown(0.01)
    time.sleep(0.03)
    assert_that(deadline.left(), equal_to(0.0), "Passed deadline does not leave zero time")


def test_tells_attempts_and_pause_it_was_given() -> None:
    attempts, pause = random.randint(1, 9), random.uniform(0.1, 9.0)
    rhythm = Rhythm(attempts, pause)
    assert_that(
        (rhythm.attempts(), rhythm.pause()),
        equal_to((attempts, pause)),
        "Rhythm does not tell the attempts and the pause it was given",
    )
