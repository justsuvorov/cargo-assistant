import random
import uuid

from hamcrest import assert_that, equal_to

from app.domain.clause import Absent
from app.domain.place import Spot
from app.domain.reason import Cause
from app.domain.remark import Note
from app.domain.semantics import Inquiry
from app.domain.status import Match, Mismatch, Review
from app.domain.verdict import Ruling
from app.rules.answers import Replies
from app.rules.outcome import Doubt, Finding, Gap, Pending, Severed, Worst
from app.rules.wording import Comments


def test_finding_codes_its_reason_by_field_and_outcome() -> None:
    assert_that(
        Finding(Mismatch(), "over_limit", {})
        .verdict(Spot("1", "sum"), Comments({"mismatch": ""}), Replies((), ()))
        .reason()
        .code(),
        equal_to("sum.over_limit"),
        "Finding does not code its reason as field dot outcome",
    )


def test_finding_comes_from_the_rule() -> None:
    assert_that(
        Finding(Match(), "same", {})
        .verdict(Spot("1", "insurer"), Comments({"match": ""}), Replies((), ()))
        .reason()
        .source(),
        equal_to("rule"),
        "Finding does not name the rule as its source",
    )


def test_gap_needs_a_person_with_the_absent_code() -> None:
    verdict = Gap(Absent("limit")).verdict(Spot("2", "sum"), Comments({}), Replies((), ()))
    assert_that(
        (verdict.status().key(), verdict.reason().code()),
        equal_to(("review", "clause.absent")),
        "Gap does not ask for review with the code clause.absent",
    )


def test_gap_comment_names_the_missing_clause() -> None:
    assert_that(
        Gap(Absent("term"))
        .verdict(Spot("2", "period"), Comments({}), Replies((), ()))
        .remark()
        .comment(),
        equal_to(Absent("term").reference()),
        "Gap does not say which clause is missing",
    )


def test_pending_asks_its_value_at_the_place() -> None:
    value = uuid.uuid4().hex
    assert_that(
        Pending(value, Absent("object"), "правило")
        .questions(Spot("5/2", "cargo"))[0]
        .place()
        .same(Spot("5/2", "cargo")),
        equal_to(True),
        "Pending does not ask its question at the place of the field",
    )


def test_pending_takes_the_status_of_the_answer() -> None:
    question = Inquiry(Spot("5/2", "cargo"), "мех", Absent("object"), "")
    assert_that(
        Pending("мех", Absent("object"), "")
        .verdict(
            Spot("5/2", "cargo"),
            Comments({}),
            Replies(
                (question,),
                (
                    Ruling(
                        question.place(), Mismatch(), Cause("cargo.excluded", "llm"), Note("", "")
                    ),
                ),
            ),
        )
        .reason()
        .code(),
        equal_to("cargo.excluded"),
        "Pending does not keep the reason of the semantic answer",
    )


def test_unanswered_pending_needs_a_person() -> None:
    verdict = Pending("мех", Absent("object"), "").verdict(
        Spot("5/2", "cargo"), Comments({"review": ""}), Replies((), ())
    )
    assert_that(
        (verdict.status().key(), verdict.reason().code()),
        equal_to(("review", "cargo.unanswered")),
        "Pending does not ask for review when the semantic judge gives no answer",
    )


def test_worst_prefers_mismatch_to_review() -> None:
    assert_that(
        Worst(
            (
                Finding(Review(), "unreadable", {}),
                Finding(Mismatch(), "different", {}),
                Finding(Match(), "same", {}),
            )
        )
        .verdict(
            Spot("1", "policy"),
            Comments({"match": "", "mismatch": "", "review": ""}),
            Replies((), ()),
        )
        .reason()
        .code(),
        equal_to("policy.different"),
        "Worst does not pick mismatch over review and match",
    )


def test_worst_prefers_review_to_match() -> None:
    assert_that(
        Worst((Finding(Match(), "same", {}), Finding(Review(), "unreadable", {})))
        .verdict(Spot("1", "policy"), Comments({"match": "", "review": ""}), Replies((), ()))
        .status()
        .key(),
        equal_to("review"),
        "Worst does not pick review over match",
    )


def test_doubt_needs_a_person_with_the_unsettled_code() -> None:
    verdict = Doubt(uuid.uuid4().hex).verdict(Spot("2", "sum"), Comments({}), Replies((), ()))
    assert_that(
        (verdict.status().key(), verdict.reason().code(), verdict.reason().source()),
        equal_to(("review", "clause.unsettled", "rule")),
        "Doubt does not need a person with the unsettled code",
    )


def test_doubt_gives_its_reason_as_comment_and_reference() -> None:
    reason = uuid.uuid4().hex
    remark = Doubt(reason).verdict(Spot("2", "sum"), Comments({}), Replies((), ())).remark()
    assert_that(
        (remark.comment(), remark.reference()),
        equal_to((reason, reason)),
        "Doubt does not give its reason as comment and reference",
    )


def test_doubt_asks_the_semantic_judge_nothing() -> None:
    assert_that(
        Doubt(uuid.uuid4().hex).questions(Spot("2", "cargo")),
        equal_to(()),
        "Doubt does not stay away from the semantic judge",
    )


def test_severed_needs_a_person_with_the_code_of_its_binding() -> None:
    reason = random.choice(("missing", "unreadable", "unknown", "ambiguous"))
    verdict = Severed(f"policy_{reason}").verdict(Spot("3", "sum"), Comments({}), Replies((), ()))
    assert_that(
        (verdict.status().key(), verdict.reason().code(), verdict.reason().source()),
        equal_to(("review", f"policy.{reason}", "rule")),
        "Severed does not need a person with the code of its binding",
    )


def test_severed_takes_the_comment_of_its_reason_from_the_card() -> None:
    comment = uuid.uuid4().hex
    assert_that(
        Severed("policy_unknown")
        .verdict(
            Spot("3", "sum"),
            Comments({"policy_unknown": comment, "review": "Другое"}),
            Replies((), ()),
        )
        .remark()
        .comment(),
        equal_to(comment),
        "Severed does not take the comment of its reason from the card",
    )


def test_severed_asks_the_semantic_judge_nothing() -> None:
    assert_that(
        Severed("policy_missing").questions(Spot("3", "cargo")),
        equal_to(()),
        "Severed does not stay away from the semantic judge",
    )
