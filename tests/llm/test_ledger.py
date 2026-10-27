import random
from concurrent.futures import ThreadPoolExecutor

from hamcrest import assert_that, equal_to

from app.llm.ledger import Logged, Measured, Memory, Route


def test_keeps_calls_in_order_of_recording() -> None:
    ledger = Memory()
    purposes = [f"p{random.randint(1, 999)}-{index}" for index in range(random.randint(2, 6))]
    for purpose in purposes:
        ledger.record(Logged(purpose, Route("vsk", "m"), "d", Measured((1, 1), 0.1, valid=True)))
    assert_that(
        [call.purpose() for call in ledger.calls()],
        equal_to(purposes),
        "Calls are not kept in the order of recording",
    )


def test_keeps_every_call_recorded_from_many_threads() -> None:
    ledger = Memory()
    with ThreadPoolExecutor(max_workers=8) as pool:
        for _ in range(400):
            pool.submit(
                ledger.record,
                Logged("p", Route("vsk", "m"), "d", Measured((0, 0), 0, valid=True)),
            )
    assert_that(len(ledger.calls()), equal_to(400), "Calls recorded from threads are not all kept")


def test_tells_measured_latency() -> None:
    latency = random.uniform(0.1, 9.0)
    assert_that(
        Measured((5, 6), latency, valid=False).latency(),
        equal_to(latency),
        "Measured latency is not told",
    )
