import random
from collections.abc import Mapping
from datetime import date

from hamcrest import assert_that, equal_to, raises

from app.declarations.schema import Fields
from app.domain.errors import UnreadableError
from app.domain.place import Spot
from app.domain.policy import Policy, Vacant
from app.domain.status import Match, Mismatch, Review, Status
from app.domain.verdict import Verdict
from app.rules.answers import Replies
from app.rules.probe import Grounded
from app.rules.window import Ordered, Window
from app.rules.wording import Comments
from tests.rules.fakes import Doubtful, Paper, Profile, Text


def _verdict(
    window: Window, key: str, row: Mapping[str, tuple[str, ...]], policy: Policy
) -> Verdict:
    return window.outcome(
        Fields().field(key, row[key]),
        Text("ГП п. 6", "срок", dates=(date(2026, 1, 1), date(2026, 9, 20))),
        Paper("11", "psg", (row,)).shipments()[0],
        policy,
    ).verdict(
        Spot("11", key),
        Comments({"match": "", "mismatch": "до {policy_end}", "review": ""}),
        Replies((), ()),
    )


def _ordered(
    bounds: tuple[str, ...],
    status: Status,
    key: str,
    row: Mapping[str, tuple[str, ...]],
    policy: Policy,
) -> Verdict:
    return (
        Ordered(bounds, status, Grounded("term", Window(bounds, "term_extension")))
        .outcome(Fields().field(key, row[key]), Paper("12", "psg", (row,)).shipments()[0], policy)
        .verdict(
            Spot("12", key),
            Comments(
                {
                    "match": "",
                    "mismatch": "",
                    "review": "",
                    "end_before_start": "окончание раньше начала",
                }
            ),
            Replies((), ()),
        )
    )


def test_period_inside_the_term_is_within() -> None:
    assert_that(
        _verdict(
            Window(("start", "end"), "term_extension"),
            "period",
            {"period": ("01.09.2026", "по", "15.09.2026")},
            Vacant("1"),
        )
        .reason()
        .code(),
        equal_to("period.within"),
        "Window does not accept a period inside the term",
    )


def test_start_after_the_term_is_after_policy_end() -> None:
    assert_that(
        _verdict(
            Window(("start",), ""),
            "period_start",
            {"period_start": ("21.09.2026",)},
            Vacant("1"),
        )
        .reason()
        .code(),
        equal_to("period_start.after_policy_end"),
        "Window does not reject a start after the term",
    )


def test_start_before_the_term_is_before_policy_start() -> None:
    assert_that(
        _verdict(
            Window(("start",), ""), "period_start", {"period_start": ("31.12.2025",)}, Vacant("1")
        )
        .reason()
        .code(),
        equal_to("period_start.before_policy_start"),
        "Window does not reject a start before the term",
    )


def test_end_past_the_term_is_extended_by_the_clause() -> None:
    assert_that(
        _verdict(
            Window(("end",), "term_extension"),
            "period_end",
            {"period_start": ("16.09.2026",), "period_end": ("21.09.2026",)},
            Profile({"term_extension": Text("ГП п. 6.2", "до окончания ответственности")}),
        )
        .reason()
        .code(),
        equal_to("period_end.extended"),
        "Window does not let the extension clause carry the end past the term",
    )


def test_end_past_the_term_without_extension_is_after_policy_end() -> None:
    assert_that(
        _verdict(
            Window(("end",), "term_extension"),
            "period_end",
            {"period_start": ("16.09.2026",), "period_end": ("21.09.2026",)},
            Vacant("1"),
        )
        .reason()
        .code(),
        equal_to("period_end.after_policy_end"),
        "Window does not reject an end past the term without extension",
    )


def test_period_ending_before_its_start_is_found_without_a_profile() -> None:
    assert_that(
        _ordered(
            ("start", "end"),
            Mismatch(),
            "period",
            {"period": ("с 12.09.2026 по 12.08.2026",)},
            Vacant("1"),
        )
        .reason()
        .code(),
        equal_to("period.end_before_start"),
        "Ordered does not find an end before the start without a policy profile",
    )


def test_period_ending_before_its_start_is_found_when_the_term_is_unsettled() -> None:
    assert_that(
        _ordered(
            ("start", "end"),
            Mismatch(),
            "period",
            {"period": ("from 12.09.2026 to 12.08.2026",)},
            Doubtful("редакция не выбрана"),
        )
        .reason()
        .code(),
        equal_to("period.end_before_start"),
        "Ordered does not find an end before the start when the term cannot be chosen",
    )


def test_end_before_the_start_of_the_row_is_found_without_a_profile() -> None:
    assert_that(
        _ordered(
            ("end",),
            Mismatch(),
            "period_end",
            {"period_start": ("12.09.2026",), "period_end": ("12.08.2026",)},
            Vacant("1"),
        )
        .reason()
        .code(),
        equal_to("period_end.end_before_start"),
        "Ordered does not find a row end before the row start without a policy profile",
    )


def test_end_before_the_start_takes_the_status_of_the_card() -> None:
    status = random.choice((Match(), Mismatch(), Review()))
    assert_that(
        _ordered(
            ("start", "end"),
            status,
            "period",
            {"period": ("12.09.2026 - 12.08.2026",)},
            Vacant("1"),
        )
        .status()
        .key(),
        equal_to(status.key()),
        "Ordered does not give the status of the card to an end before the start",
    )


def test_end_before_the_start_takes_the_comment_of_the_card() -> None:
    assert_that(
        _ordered(
            ("end",),
            Mismatch(),
            "period_end",
            {"period_start": ("12.09.2026",), "period_end": ("12.08.2026",)},
            Doubtful("редакция не выбрана"),
        )
        .remark()
        .comment(),
        equal_to("окончание раньше начала"),
        "Ordered does not word an end before the start with the comment of the card",
    )


def test_end_on_the_day_of_the_start_is_in_order() -> None:
    assert_that(
        _ordered(
            ("start", "end"),
            Mismatch(),
            "period",
            {"period": ("12.09.2026 to 12.09.2026",)},
            Profile({"term": Text("ГП п. 6", "срок", dates=(date(2026, 1, 1), date(2026, 9, 20)))}),
        )
        .reason()
        .code(),
        equal_to("period.within"),
        "Ordered does not accept an end on the day of the start",
    )


def test_unreadable_period_is_not_taken_for_disorder() -> None:
    assert_that(
        _ordered(
            ("start", "end"),
            Mismatch(),
            "period",
            {"period": ("с сентября по 12.08.2026",)},
            Profile({"term": Text("ГП п. 6", "срок", dates=(date(2026, 1, 1), date(2026, 9, 20)))}),
        )
        .reason()
        .code(),
        equal_to("period.unreadable"),
        "Ordered does not leave an unreadable period to the review of the window",
    )


def test_unreadable_start_of_the_row_is_not_taken_for_disorder() -> None:
    assert_that(
        _ordered(
            ("end",),
            Mismatch(),
            "period_end",
            {"period_start": ("first of September",), "period_end": ("12.08.2026",)},
            Profile({"term": Text("ГП п. 6", "срок", dates=(date(2026, 1, 1), date(2026, 9, 20)))}),
        )
        .reason()
        .code(),
        equal_to("period_end.unreadable"),
        "Ordered does not leave an unreadable row start to the review of the window",
    )


def test_period_in_order_without_a_profile_still_needs_the_term() -> None:
    assert_that(
        _ordered(
            ("start", "end"),
            Mismatch(),
            "period",
            {"period": ("12.08.2026 - 12.09.2026",)},
            Vacant("1"),
        )
        .reason()
        .code(),
        equal_to("clause.absent"),
        "Ordered does not leave a period in order to the term of the policy",
    )


def test_unreadable_period_needs_a_person() -> None:
    assert_that(
        _verdict(Window(("start", "end"), ""), "period", {"period": ("с сентября",)}, Vacant("1"))
        .reason()
        .code(),
        equal_to("period.unreadable"),
        "Window does not ask for review of an unreadable period",
    )


def test_mismatch_comment_names_the_end_of_the_term() -> None:
    assert_that(
        _verdict(
            Window(("start",), ""), "period_start", {"period_start": ("21.09.2026",)}, Vacant("1")
        )
        .remark()
        .comment(),
        equal_to("до 20.09.2026"),
        "Window does not put the end of the term into the comment",
    )


def test_end_inside_the_term_needs_no_answer_about_the_extension() -> None:
    assert_that(
        _verdict(
            Window(("end",), "term_extension"),
            "period_end",
            {"period_start": ("01.09.2026",), "period_end": ("15.09.2026",)},
            Doubtful("редакция не выбрана"),
        )
        .reason()
        .code(),
        equal_to("period_end.within"),
        "Window does not leave the extension alone when the end is inside the term",
    )


def test_end_past_the_term_refuses_to_answer_when_the_extension_is_unknown() -> None:
    assert_that(
        lambda: _verdict(
            Window(("end",), "term_extension"),
            "period_end",
            {"period_start": ("01.09.2026",), "period_end": ("21.09.2026",)},
            Doubtful("редакция не выбрана"),
        ),
        raises(UnreadableError),
        "Window does not refuse to answer when the extension is unknown",
    )


def test_start_outside_the_term_needs_no_answer_about_the_extension() -> None:
    assert_that(
        _verdict(
            Window(("start", "end"), "term_extension"),
            "period",
            {"period": ("01.10.2026", "по", "15.10.2026")},
            Doubtful("редакция не выбрана"),
        )
        .reason()
        .code(),
        equal_to("period.after_policy_end"),
        "Window does not leave the extension alone when the start is outside the term",
    )
