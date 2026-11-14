import random

from hamcrest import assert_that, equal_to

from app.declarations.schema import Fields
from app.domain.clause import Clause
from app.domain.field import Field
from app.domain.place import Spot
from app.domain.policy import Policy, Unbound, Vacant
from app.domain.shipment import Shipment
from app.domain.status import Match, Mismatch, Review
from app.domain.verdict import Verdict
from app.rules.answers import Replies
from app.rules.outcome import Finding, Outcome
from app.rules.probe import Accepted, Constant, Doubted, Emptied, Grounded, Probe
from app.rules.wording import Comments
from tests.rules.fakes import Doubtful, Paper, Profile, Text


class _Echo:
    """Measure that answers with the reference of the clause it got."""

    def outcome(
        self, _field: Field, clause: Clause, _shipment: Shipment, _policy: Policy
    ) -> Outcome:
        return Finding(Match(), "measured", {"reference": clause.reference()})


def _verdict(probe: Probe, key: str, texts: tuple[str, ...], policy: Policy) -> Verdict:
    shipment = Paper("9", "vertical", ({key: texts},)).shipments()[0]
    return probe.outcome(Fields().field(key, texts), shipment, policy).verdict(
        Spot("9", key), Comments({"match": "", "mismatch": "", "review": ""}), Replies((), ())
    )


def test_blank_word_gives_the_status_of_the_card() -> None:
    assert_that(
        _verdict(
            Emptied(("нет", "-"), Mismatch(), Constant(Match(), "filled")),
            "beneficiary",
            (random.choice(("Нет", " нет.", "-")),),
            Vacant("1"),
        )
        .reason()
        .code(),
        equal_to("beneficiary.empty"),
        "Emptied does not treat a blank word as an empty field",
    )


def test_missing_field_gives_the_status_of_the_card() -> None:
    assert_that(
        _verdict(Emptied((), Review(), Constant(Match(), "filled")), "beneficiary", (), Vacant("1"))
        .status()
        .key(),
        equal_to("review"),
        "Emptied does not give the if_empty status to a missing field",
    )


def test_filled_field_runs_the_inner_probe() -> None:
    assert_that(
        _verdict(
            Emptied(("нет",), Mismatch(), Constant(Match(), "filled")),
            "beneficiary",
            ("ООО «Нетто»",),
            Vacant("1"),
        )
        .reason()
        .code(),
        equal_to("beneficiary.filled"),
        "Emptied does not run the inner probe for a filled field",
    )


def test_value_accepted_by_special_conditions_matches() -> None:
    verdict = _verdict(
        Accepted("transport", Constant(Mismatch(), "unlisted")),
        "transport",
        ("В соответствии с п.8 ГП",),
        Profile(
            {"accepted.transport": Text("Особые условия", entries=("в соответствии с п. 8 ГП",))}
        ),
    )
    assert_that(
        (verdict.status().key(), verdict.reason().code(), verdict.remark().reference()),
        equal_to(("match", "transport.accepted", "Особые условия")),
        "Accepted does not match a value from the special conditions",
    )


def test_other_value_goes_to_the_inner_probe() -> None:
    assert_that(
        _verdict(
            Accepted("transport", Constant(Mismatch(), "unlisted")),
            "transport",
            ("Авто",),
            Profile(
                {"accepted.transport": Text("Особые условия", entries=("по решению перевозчика",))}
            ),
        )
        .reason()
        .code(),
        equal_to("transport.unlisted"),
        "Accepted does not leave other values to the inner probe",
    )


def test_absent_clause_needs_a_person() -> None:
    assert_that(
        _verdict(Grounded("limit", _Echo()), "sum", ("100", "RUB"), Vacant("1")).reason().code(),
        equal_to("clause.absent"),
        "Grounded does not ask for review when the clause is absent",
    )


def test_stated_clause_reaches_the_measure() -> None:
    assert_that(
        _verdict(
            Grounded("limit", _Echo()),
            "sum",
            ("100", "RUB"),
            Profile({"limit": Text("ГП п. 12", "лимит")}),
        )
        .remark()
        .reference(),
        equal_to("ГП п. 12"),
        "Grounded does not hand the stated clause to the measure",
    )


def test_doubted_probe_keeps_the_outcome_of_the_inner_probe() -> None:
    assert_that(
        _verdict(Doubted(Constant(Match(), "filled")), "beneficiary", ("ООО",), Vacant("1"))
        .reason()
        .code(),
        equal_to("beneficiary.filled"),
        "Doubted does not keep the outcome of the inner probe",
    )


def test_doubted_probe_asks_a_person_when_the_policy_cannot_choose() -> None:
    verdict = _verdict(
        Doubted(Grounded("limit", _Echo())), "sum", ("1 000",), Doubtful("редакция не выбрана")
    )
    assert_that(
        (verdict.status().key(), verdict.reason().code(), verdict.reason().source()),
        equal_to(("review", "clause.unsettled", "rule")),
        "Doubted does not ask a person when the policy cannot choose",
    )


def test_doubted_probe_explains_why_the_policy_cannot_choose() -> None:
    reason = f"причина {random.randint(1, 999)}"
    assert_that(
        _verdict(Doubted(Grounded("limit", _Echo())), "sum", ("1 000",), Doubtful(reason))
        .remark()
        .comment(),
        equal_to(reason),
        "Doubted does not explain why the policy cannot choose",
    )


def test_doubted_probe_asks_a_person_when_the_declaration_is_bound_to_no_policy() -> None:
    reason = random.choice(("missing", "unreadable", "unknown", "ambiguous"))
    verdict = _verdict(
        Doubted(Grounded("limit", _Echo())), "sum", ("1 000",), Unbound(f"policy_{reason}", "1")
    )
    assert_that(
        (verdict.status().key(), verdict.reason().code()),
        equal_to(("review", f"policy.{reason}")),
        "Doubted does not ask a person when the declaration is bound to no policy",
    )


def test_accepted_probe_runs_the_inner_probe_for_a_declaration_bound_to_no_policy() -> None:
    assert_that(
        _verdict(
            Accepted("document", Constant(Match(), "filled")),
            "document",
            ("Накладная",),
            Unbound("policy_unknown", "1"),
        )
        .reason()
        .code(),
        equal_to("document.filled"),
        "Accepted does not run the inner probe when the declaration is bound to no policy",
    )
