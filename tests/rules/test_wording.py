import uuid

from hamcrest import assert_that, equal_to

from app.rules.wording import Comments


def test_outcome_template_wins_over_status_template() -> None:
    assert_that(
        Comments({"empty": "Поле пусто", "mismatch": "Иное"})
        .remark(("empty", "mismatch"), {})
        .comment(),
        equal_to("Поле пусто"),
        "Comments does not prefer the template of the outcome",
    )


def test_status_template_serves_an_outcome_without_its_own() -> None:
    assert_that(
        Comments({"mismatch": "Иное"}).remark(("over_limit", "mismatch"), {}).comment(),
        equal_to("Иное"),
        "Comments does not fall back to the template of the status",
    )


def test_template_is_filled_with_values() -> None:
    entry = uuid.uuid4().hex
    assert_that(
        Comments({"review": "Позиция «{entry}» ({reference})"})
        .remark(("review",), {"entry": entry, "reference": "п. 5"})
        .comment(),
        equal_to(f"Позиция «{entry}» (п. 5)"),
        "Comments does not fill the placeholders",
    )


def test_unfilled_placeholder_becomes_empty() -> None:
    assert_that(
        Comments({"match": "Лимит {limit}."}).remark(("match",), {}).comment(),
        equal_to("Лимит ."),
        "Comments does not blank a placeholder that the outcome leaves unfilled",
    )


def test_reference_value_becomes_the_reference_of_the_remark() -> None:
    reference = f"ДС {uuid.uuid4().hex}"
    assert_that(
        Comments({"match": ""}).remark(("match",), {"reference": reference}).reference(),
        equal_to(reference),
        "Comments does not keep the reference of the clause",
    )
