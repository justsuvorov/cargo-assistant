import random

from hamcrest import assert_that, equal_to, same_instance

from app.llm.pool import Shared


class Open:
    """Trust double that accepts any certificate and counts how often it was asked."""

    def __init__(self) -> None:
        self.asked = 0

    def verify(self) -> bool:
        self.asked += 1
        return True


def test_hands_out_one_client_for_all_requests() -> None:
    pool = Shared(Open(), 1)
    assert_that(pool.client(), same_instance(pool.client()), "Pool does not reuse its client")


def test_opens_client_only_once() -> None:
    trust = Open()
    pool = Shared(trust, 1)
    pool.client()
    pool.client()
    assert_that(trust.asked, equal_to(1), "Pool does not open its client exactly once")


def test_hands_out_one_gate_for_all_models() -> None:
    pool = Shared(Open(), random.randint(1, 5))
    assert_that(pool.gate(), same_instance(pool.gate()), "Pool does not keep one gate")
