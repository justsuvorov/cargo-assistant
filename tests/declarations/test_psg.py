import random
from datetime import date

from hamcrest import assert_that, contains_exactly, equal_to

from app.declarations.psg import Psg
from app.ingest.book import Page, Series, Written


def _page(*lines: dict[int, str]) -> Page:
    return Page(
        "sheet",
        tuple(
            Series(number, tuple(Written(column, text) for column, text in line.items()))
            for number, line in enumerate(lines, start=1)
        ),
    )


def _russian() -> Page:
    return _page(
        {9: "Приложение № 1 к Генеральному полису"},
        {9: "№ 0000T00GR0000 от 26.08.2026 г."},
        {0: "Ежедневная декларация №", 4: "29", 5: "перевозок начавшихся", 9: "17.09.2026"},
        {0: "Страхователь", 3: 'ООО "Тест"'},
        {0: "Страховщик", 3: 'САО "Страховщик"'},
        {
            0: "№ п/п",
            1: "Период страхования",
            3: "Наименование груза",
            5: "Выгодоприобретатель",
            6: "Номер товарно-транспортного документа (накладной)",
            7: "Дата товарно-транспортного документа (накладной)",
            8: "Вид транспорта / Перевозчик",
            9: "Маршрут",
            12: "Страховая сумма",
            13: "Валюта",
            14: "Объем транспортного средства",
        },
        {
            1: "начало",
            2: "окончание",
            9: "Пункт отправления",
            10: "Пункт перегрузки",
            11: "Пункт назначения",
        },
        {
            0: "1",
            1: "17.09.2026",
            2: "46290",
            3: "Мясо, сыр",
            5: "ООО «Получатель»",
            6: "11753, 11840",
            7: "10.09, 11.09.2026",
            8: "Авто / ООО «Перевозчик»",
            9: "г. Первый",
            10: "Нет",
            11: "г. Второй",
            12: "1757029.96",
            13: "рублей",
            14: "82",
        },
        {0: "2", 1: "17.09.2026", 2: "02.10.2026", 3: "Масло", 12: "100", 13: "евро"},
        {11: "ИТОГО:", 12: "1757129.96", 13: "рублей"},
        {12: "5000"},
        {1: "СТРАХОВЩИК", 10: "СТРАХОВАТЕЛЬ"},
    )


def _english() -> Page:
    return _page(
        {9: "Appendix 1 to the Open Cover"},
        {9: "No. 0000T00GR0000 dated 26.08.2026"},
        {0: "Daily declaration No. 3", 9: "17.09.2026"},
        {0: "Insurer", 3: "Test LLC"},
        {
            0: "Item No.",
            1: "Insurance period",
            3: "Cargo description",
            5: "Beneficiary",
            6: "Transport document number",
            7: "Transport document date",
            8: "Mode of transport",
            9: "Route",
            12: "Sum insured",
            13: "Currency",
        },
        {
            1: "Start",
            2: "End",
            9: "Point of departure",
            10: "Point of transshipment",
            11: "Point of destination",
        },
        {
            0: "1",
            1: "17.09.2026",
            2: "20.09.2026",
            3: "meat",
            5: "Receiver LLC",
            6: "AB-1",
            7: "17.09.2026",
            8: "truck",
            9: "Town A",
            11: "Town B",
            12: "1500,50",
            13: "euro",
        },
    )


def test_psg_finds_columns_by_russian_labels_not_by_letters() -> None:
    first = Psg(_russian()).records()[0]
    assert_that(
        (
            first.field("cargo").entries(),
            first.field("beneficiary").text(),
            first.field("document_number").entries(),
            first.field("document_date").dates(),
            first.field("transport").entries(),
            first.field("departure").text(),
            first.field("transshipment").text(),
            first.field("destination").text(),
        ),
        equal_to(
            (
                ("Мясо", "сыр"),
                "ООО «Получатель»",
                ("11753", "11840"),
                (date(2026, 9, 10), date(2026, 9, 11)),
                ("Авто", "ООО «Перевозчик»"),
                "г. Первый",
                "Нет",
                "г. Второй",
            )
        ),
        "Psg does not find the columns by their Russian labels",
    )


def test_psg_reads_period_columns_and_sum_with_currency_column() -> None:
    first = Psg(_russian()).records()[0]
    assert_that(
        (
            first.field("period_start").dates(),
            first.field("period_end").dates(),
            first.field("sum").amounts()[0].text(),
            first.start(),
        ),
        equal_to(
            (
                (date(2026, 9, 17),),
                (date(2026, 9, 25),),
                "1 757 029,96 RUB",
                date(2026, 9, 17),
            )
        ),
        "Psg does not read the period columns or the sum with the currency column",
    )


def test_psg_skips_total_rows_and_rows_without_a_number() -> None:
    assert_that(
        tuple(record.label() for record in Psg(_russian()).records()),
        contains_exactly("1", "2"),
        "Psg does not skip a total row or a row without a number",
    )


def test_psg_leaves_columns_that_a_row_does_not_fill_blank() -> None:
    assert_that(
        Psg(_russian()).records()[1].field("beneficiary").filled(),
        equal_to(False),
        "Psg does not leave an empty cell blank",
    )


def test_psg_ignores_columns_that_contracts_do_not_know() -> None:
    assert_that(
        Psg(_russian()).records()[0].field("volume").filled(),
        equal_to(False),
        "Psg exposes a column that no contract key names",
    )


def test_psg_takes_insurer_and_policy_from_the_header() -> None:
    first = Psg(_russian()).records()[0]
    assert_that(
        (first.field("insurer").text(), first.field("policy").dates()),
        equal_to(('ООО "Тест"', (date(2026, 8, 26),))),
        "Psg does not take the insurer and the policy from the header",
    )


def test_psg_reports_form_number_and_policy() -> None:
    layout = Psg(_russian())
    assert_that(
        (layout.form(), layout.number(), layout.policy()),
        equal_to(("psg", "29", "0000T00GR0000")),
        "Psg does not report its form, number and policy",
    )


def test_psg_reads_english_labels() -> None:
    first = Psg(_english()).records()[0]
    assert_that(
        (
            first.field("cargo").text(),
            first.field("beneficiary").text(),
            first.field("document_number").entries(),
            first.field("transport").text(),
            first.field("destination").text(),
            first.field("sum").amounts()[0].text(),
            first.field("period_end").dates(),
            first.field("insurer").text(),
            Psg(_english()).number(),
        ),
        equal_to(
            (
                "meat",
                "Receiver LLC",
                ("AB-1",),
                "truck",
                "Town B",
                "1 500,50 EUR",
                (date(2026, 9, 20),),
                "Test LLC",
                "3",
            )
        ),
        "Psg does not read the English labels of the table",
    )


def test_psg_scores_vertical_sheet_lower_than_table() -> None:
    vertical = _page(
        {1: "1.", 2: "Полное наименование груза", 6: "мясо"},
        {1: "4.", 2: "Страховая сумма", 6: "100", 8: "рублей"},
    )
    assert_that(
        Psg(vertical).score() < Psg(_russian()).score(),
        equal_to(True),
        "Psg does not score a vertical sheet lower than a table",
    )


def test_psg_follows_the_columns_when_they_move() -> None:
    shift = random.randint(1, 5)
    moved = _page(
        {shift + 0: "№ п/п", shift + 1: "Период страхования", shift + 3: "Наименование груза"},
        {
            shift + 1: "начало",
            shift + 2: "окончание",
            shift + 6: "Страховая сумма",
            shift + 7: "Валюта",
        },
        {
            shift + 0: "1",
            shift + 1: "17.09.2026",
            shift + 3: "Мясо",
            shift + 6: "10",
            shift + 7: "евро",
        },
    )
    assert_that(
        Psg(moved).records()[0].field("cargo").text(),
        equal_to("Мясо"),
        "Psg does not follow the columns when they move to other letters",
    )
