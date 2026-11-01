import uuid
from pathlib import Path

from hamcrest import assert_that, equal_to, raises

from tools.eval.fields import Absent, Cards, Deck, Key, Unmapped
from tools.eval.sheet import Line


def test_key_keeps_mvp_status_when_remark_says_right() -> None:
    assert_that(
        Key("sum").default(Line("97", ("97", "Сумма", "", "не совпадает", "", "Верно. "))).cells(),
        equal_to(("97", "97", "sum", "mismatch", "fsc-ok", "")),
        "Key does not keep the MVP status of a row marked right",
    )


def test_key_asks_about_remark_without_ruling() -> None:
    assert_that(
        Key("sum").default(Line("97", ("97", "Сумма", "", "совпадает", "", "некорректно"))).kind(),
        equal_to("question"),
        "Key does not ask about a remark that is not a plain right",
    )


def test_key_asks_about_row_without_remark() -> None:
    assert_that(
        Key("sum").default(Line("114", ("114/1", "Сумма", "", "совпадает", "", ""))).cells()[5],
        equal_to("Нет отметки ФСЦ"),
        "Key does not ask about a row without a remark",
    )


def test_key_settles_ruling() -> None:
    assert_that(
        Key("sum")
        .settle(Line("97", ("97", "Сумма", "", "совпадает", "", "x")), ("mismatch", "D-23", "n"))
        .cells()[3],
        equal_to("mismatch"),
        "Key does not settle a ruling",
    )


def test_absent_drops_row() -> None:
    assert_that(
        Absent("sealing", "D-14")
        .default(Line("35", ("35", "Пломбирование", "", "не совпадает", "", "нет поля")))
        .kind(),
        equal_to("excluded"),
        "Absent does not drop the row",
    )


def test_absent_refuses_ruling() -> None:
    assert_that(
        lambda: Absent("sealing", "D-14").settle(
            Line("35", ("35", "Пломбирование", "", "совпадает", "", "x")), ("match", "x", "")
        ),
        raises(ValueError),
        "Absent does not refuse a ruling for a field outside the form",
    )


def test_unmapped_asks_with_its_reason() -> None:
    reason = uuid.uuid4().hex
    assert_that(
        Unmapped("Период страхования", reason)
        .default(Line("35", ("35", "Период страхования", "", "совпадает", "", "Верно")))
        .cells()[5],
        equal_to(reason),
        "Unmapped does not ask with its reason",
    )


def test_cards_find_key_by_title_of_form() -> None:
    assert_that(
        Cards(
            {"sum": {"vertical": "Страховая сумма", "psg": "Страховая сумма"}},
            {"forms": {"97": "vertical"}, "unmapped": {}},
        )
        .target(Line("97", ("97", "Страховая сумма", "", "совпадает", "", "")))
        .field(),
        equal_to("sum"),
        "Cards do not find the key by the title of the form",
    )


def test_cards_match_title_spread_over_lines() -> None:
    assert_that(
        Cards(
            {"departure": {"psg": "Маршрут\nПункт отправления"}},
            {"forms": {"113": "psg"}, "unmapped": {}},
        )
        .target(Line("113", ("113/1", "Маршрут\\nПункт отправления", "", "совпадает", "", "")))
        .field(),
        equal_to("departure"),
        "Cards do not match a title spread over two lines",
    )


def test_cards_accept_title_of_other_form_for_covered_key() -> None:
    assert_that(
        Cards(
            {"cargo": {"vertical": "Полное наименование груза", "psg": "Наименование груза"}},
            {"forms": {"35": "psg"}, "unmapped": {}},
        )
        .target(Line("35", ("35", "Полное наименование груза", "", "совпадает", "", "")))
        .field(),
        equal_to("cargo"),
        "Cards do not accept a title of another form for a key the form has",
    )


def test_cards_ask_about_key_with_counterparts() -> None:
    assert_that(
        Cards(
            {"period": {"vertical": "Период страхования"}},
            {"forms": {"35": "psg"}, "unmapped": {"period": "два ключа"}},
        )
        .target(Line("35", ("35", "Период страхования", "", "совпадает", "", "")))
        .field(),
        equal_to("Период страхования"),
        "Cards do not leave a label with several keys unmapped",
    )


def test_cards_drop_key_missing_from_form() -> None:
    assert_that(
        Cards(
            {"sealing": {"vertical": "Пломбирование"}},
            {"forms": {"35": "psg"}, "unmapped": {}},
        )
        .target(Line("35", ("35", "Пломбирование", "", "совпадает", "", "x")))
        .default(Line("35", ("35", "Пломбирование", "", "совпадает", "", "x")))
        .kind(),
        equal_to("excluded"),
        "Cards do not drop a field missing from the form",
    )


def test_cards_leave_unknown_label_unmapped() -> None:
    label = uuid.uuid4().hex
    assert_that(
        Cards({"sum": {"psg": "Страховая сумма"}}, {"forms": {"114": "psg"}, "unmapped": {}})
        .target(Line("114", ("114/4", label, "", "совпадает", "", "")))
        .field(),
        equal_to(label),
        "Cards do not leave an unknown label unmapped",
    )


def test_deck_reads_titles_of_card_forms(tmp_path: Path) -> None:
    (tmp_path / "sum.yaml").write_text(
        'field: sum\nforms:\n  vertical: {order: 6, title: "Страховая сумма"}\n'
        '  psg: {order: 13, title: "Страховая сумма"}\n',
        encoding="utf-8",
    )
    assert_that(
        Deck(tmp_path).titles(),
        equal_to({"sum": {"vertical": "Страховая сумма", "psg": "Страховая сумма"}}),
        "Deck does not read the titles of card forms",
    )


def test_deck_orders_fields_of_form_by_card_order(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text(
        "field: sum\nforms:\n  psg: {order: 13, title: Страховая сумма}\n", encoding="utf-8"
    )
    (tmp_path / "b.yaml").write_text(
        "field: insurer\nforms:\n  psg: {order: 1, title: Страхователь}\n", encoding="utf-8"
    )
    (tmp_path / "c.yaml").write_text(
        "field: sealing\nforms:\n  vertical: {order: 14, title: Пломбирование}\n", encoding="utf-8"
    )
    assert_that(
        Deck(tmp_path).fields("psg"),
        equal_to((("insurer", "Страхователь"), ("sum", "Страховая сумма"))),
        "Deck does not order the fields of a form by the order of cards",
    )


def test_deck_refuses_form_without_fields(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text(
        "field: sum\nforms:\n  psg: {order: 13, title: Страховая сумма}\n", encoding="utf-8"
    )
    assert_that(
        lambda: Deck(tmp_path).fields("vertical"),
        raises(ValueError),
        "Deck does not refuse a form that no card has",
    )
