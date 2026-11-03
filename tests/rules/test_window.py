from collections.abc import Mapping
from datetime import date

from hamcrest import assert_that, equal_to, raises

from app.declarations.schema import Fields
from app.domain.errors import UnreadableError
from app.domain.place import Spot
from app.domain.policy import Policy, Vacant
from app.domain.verdict import Verdict
from app.rules.answers import Replies
from app.rules.window import Window
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


def test_end_before_the_start_needs_a_person() -> None:
    assert_that(
        _verdict(
            Window(("start", "end"), "term_extension"),
            "period",
            {"period": ("12.09.2026", "12.08.2026")},
            Vacant("1"),
        )
        .status()
        .key(),
        equal_to("review"),
        "Window does not ask for review of an end before the start",
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
