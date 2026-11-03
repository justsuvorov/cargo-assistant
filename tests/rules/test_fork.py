from hamcrest import assert_that, equal_to, raises

from app.declarations.schema import Fields
from app.domain.errors import UnreadableError
from app.domain.place import Spot
from app.domain.policy import Policy, Vacant
from app.domain.status import Match, Mismatch
from app.rules.answers import Replies
from app.rules.fork import Flag, Fork, Mixed
from app.rules.modes import Modes
from app.rules.probe import Constant
from app.rules.wording import Comments
from tests.rules.fakes import Doubtful, Paper, Profile, Text


def test_flag_holds_when_the_profile_states_the_clause() -> None:
    assert_that(
        Flag("carrier_risk").holds(
            Paper("4", "vertical", ({},)).shipments()[0],
            Profile({"carrier_risk": Text("ГП п. 3.4.28", "риск")}),
        ),
        equal_to(True),
        "Flag does not hold for a stated clause",
    )


def test_flag_fails_without_a_profile() -> None:
    assert_that(
        Flag("carrier_risk").holds(Paper("4", "vertical", ({},)).shipments()[0], Vacant("1")),
        equal_to(False),
        "Flag does not fail for an absent clause",
    )


def test_flag_refuses_to_answer_when_the_policy_cannot_choose() -> None:
    shipment = Paper("4", "vertical", ({},)).shipments()[0]
    assert_that(
        lambda: Flag("carrier_risk").holds(shipment, Doubtful("редакция не выбрана")),
        raises(UnreadableError),
        "Flag does not refuse to answer when the policy cannot choose",
    )


def test_mixed_reads_another_field_of_the_shipment() -> None:
    assert_that(
        Mixed("transport", Modes({"auto": ("авто",), "air": ("авиа",)})).holds(
            Paper("4", "psg", ({"transport": ("Авто+авиа+авто",)},)).shipments()[0],
            Vacant("1"),
        ),
        equal_to(True),
        "Mixed does not read the transport field of the shipment",
    )


def _code(transport: str, policy: Policy) -> str:
    shipment = Paper("4", "psg", ({"transport": (transport,)},)).shipments()[0]
    return (
        Fork(
            Mixed("transport", Modes({"auto": ("авто",), "air": ("авиа",)})),
            Constant(Mismatch(), "then"),
            Constant(Match(), "otherwise"),
        )
        .outcome(Fields().field("transshipment", ()), shipment, policy)
        .verdict(
            Spot("4", "transshipment"), Comments({"match": "", "mismatch": ""}), Replies((), ())
        )
        .reason()
        .code()
    )


def test_fork_runs_the_then_probe_when_the_condition_holds() -> None:
    assert_that(
        _code("авто+авиа", Vacant("1")),
        equal_to("transshipment.then"),
        "Fork does not run the then probe when the condition holds",
    )


def test_fork_runs_the_other_probe_when_the_condition_fails() -> None:
    assert_that(
        _code("авто", Vacant("1")),
        equal_to("transshipment.otherwise"),
        "Fork does not run the other probe when the condition fails",
    )
