from datetime import date

from hamcrest import assert_that, contains_exactly, equal_to

from app.declarations.vertical import Vertical
from app.ingest.book import Page, Series, Written


def _page(*lines: dict[int, str]) -> Page:
    return Page(
        "sheet",
        tuple(
            Series(number, tuple(Written(column, text) for column, text in line.items()))
            for number, line in enumerate(lines, start=1)
        ),
    )


def _russian(insurer: str) -> Page:
    return _page(
        {0: "Приложение № 2 к Генеральному Полису"},
        {7: "№ 0000T00GR0000 от 26.08.2026 г."},
        {7: 'В САО "Страховщик"'},
        {7: insurer},
        {0: "Декларация", 3: "№ Р-005", 4: "об отгрузке по Генеральному полису"},
        {1: "1.", 2: "Полное наименование груза", 6: "мясо, сыр"},
        {
            1: "2.",
            2: "Род упаковки (в т.ч. контейнер); число мест, общий вес",
            6: "коробки, 5 мест",
        },
        {1: "3.", 2: "Выгодоприобретатель", 6: "ООО «Получатель»"},
        {1: "4.", 2: "Страховая сумма", 6: "252 000", 8: "китайских юаней"},
        {1: "5.", 2: "Транспорт", 6: "Авто+авиа+авто"},
        {1: "6.", 2: "Пункт отправления", 6: "г. Первый - г. Второй"},
        {1: "7.", 2: "Пункт перегрузки (таможенного оформления)"},
        {1: "8.", 2: "Пункт назначения", 6: "г. Третий"},
        {1: "9.", 2: "Период страхования", 6: "46286", 7: "по", 8: "20.10.2026"},
        {
            1: "10.",
            2: "Товарно-транспортная накладная №",
            6: "№550, 551",
            7: "от",
            8: "17.09.2026;",
        },
        {1: "11.", 2: "Перевозчик", 6: "ООО «Перевозчик»"},
        {1: "12.", 2: "Пломбирование (да/нет)", 6: "да"},
        {1: "13.", 2: "Прочие сведения", 6: "нет"},
        {1: "Страхователь:", 7: "21.09.2026"},
        {6: 'От САО "Страховщик"'},
    )


def _english() -> Page:
    return _page(
        {0: "Appendix 2 to the Open Cover"},
        {7: "No. 0000T00GR0000 dated 26.08.2026"},
        {7: "From Test Trading LLC"},
        {0: "Declaration", 3: "No. 12", 4: "of shipment"},
        {1: "1.", 2: "Full description of cargo", 6: "frozen meat"},
        {1: "4.", 2: "Sum insured", 6: "1500.50", 8: "euro"},
        {1: "5.", 2: "Mode of transport", 6: "Truck"},
        {1: "6.", 2: "Place of departure", 6: "Port A"},
        {1: "8.", 2: "Place of destination", 6: "Port B"},
        {1: "9.", 2: "Insurance period", 6: "21.09.2026", 7: "to", 8: "24.09.2026"},
        {1: "10.", 2: "Consignment note No.", 6: "AB-12", 7: "dated", 8: "20.09.2026"},
        {1: "11.", 2: "Carrier", 6: "Carrier Ltd"},
    )


def test_vertical_reads_russian_cargo_as_a_list() -> None:
    assert_that(
        Vertical(_russian("От ООО «Тест»")).records()[0].field("cargo").entries(),
        contains_exactly("мясо", "сыр"),
        "Vertical does not read the Russian cargo label as a list",
    )


def test_vertical_reads_sum_with_currency_from_the_next_cell() -> None:
    assert_that(
        Vertical(_russian("От ООО «Тест»")).records()[0].field("sum").amounts()[0].text(),
        equal_to("252 000,00 CNY"),
        "Vertical does not read the sum with the currency of the next cell",
    )


def test_vertical_reads_both_dates_of_the_period_and_starts_on_the_first() -> None:
    record = Vertical(_russian("От ООО «Тест»")).records()[0]
    assert_that(
        (record.field("period").dates(), record.start()),
        equal_to(((date(2026, 9, 21), date(2026, 10, 20)), date(2026, 9, 21))),
        "Vertical does not read the period or its start",
    )


def test_vertical_reads_waybill_numbers_and_date_without_link_words() -> None:
    field = Vertical(_russian("От ООО «Тест»")).records()[0].field("document")
    assert_that(
        (field.entries(), field.dates(), field.text()),
        equal_to((("550", "551"), (date(2026, 9, 17),), "№550, 551 17.09.2026;")),
        "Vertical does not read waybill numbers and date",
    )


def test_vertical_takes_insurer_from_the_line_that_begins_with_from() -> None:
    assert_that(
        Vertical(_russian("От ООО «Тест»")).records()[0].field("insurer").text(),
        equal_to("ООО «Тест»"),
        "Vertical does not take the insurer from the header line",
    )


def test_vertical_leaves_insurer_blank_when_it_is_empty_in_the_header() -> None:
    assert_that(
        Vertical(_russian("От ")).records()[0].field("insurer").filled(),
        equal_to(False),
        "Vertical does not leave the insurer blank when the header has none",
    )


def test_vertical_leaves_a_label_without_value_blank() -> None:
    assert_that(
        Vertical(_russian("От ООО «Тест»")).records()[0].field("transshipment").filled(),
        equal_to(False),
        "Vertical does not leave a label without value blank",
    )


def test_vertical_reads_policy_citation_and_its_date() -> None:
    field = Vertical(_russian("От ООО «Тест»")).records()[0].field("policy")
    assert_that(
        (field.text(), field.dates()),
        equal_to(("№ 0000T00GR0000 от 26.08.2026 г.", (date(2026, 8, 26),))),
        "Vertical does not read the policy citation and its date",
    )


def test_vertical_is_one_shipment_of_the_vertical_form() -> None:
    layout = Vertical(_russian("От ООО «Тест»"))
    assert_that(
        (layout.form(), len(layout.records()), layout.number(), layout.policy()),
        equal_to(("vertical", 1, "Р-005", "0000T00GR0000")),
        "Vertical is not one shipment of the vertical form with its number and policy",
    )


def test_vertical_reads_english_labels() -> None:
    record = Vertical(_english()).records()[0]
    assert_that(
        (
            record.field("cargo").text(),
            record.field("sum").amounts()[0].text(),
            record.field("transport").text(),
            record.field("destination").text(),
            record.field("period").dates(),
            record.field("document").entries(),
            record.field("document").dates(),
            record.field("carrier").text(),
            record.field("insurer").text(),
        ),
        equal_to(
            (
                "frozen meat",
                "1 500,50 EUR",
                "Truck",
                "Port B",
                (date(2026, 9, 21), date(2026, 9, 24)),
                ("AB-12",),
                (date(2026, 9, 20),),
                "Carrier Ltd",
                "Test Trading LLC",
            )
        ),
        "Vertical does not read the English labels of the form",
    )


def test_vertical_scores_table_header_lower_than_vertical_sheet() -> None:
    table = _page(
        {0: "№ п/п", 1: "Период страхования", 3: "Наименование груза", 5: "Выгодоприобретатель"},
        {1: "начало", 2: "окончание", 9: "Пункт отправления", 10: "Пункт назначения"},
    )
    assert_that(
        Vertical(table).score() < Vertical(_russian("От ООО «Тест»")).score(),
        equal_to(True),
        "Vertical does not score a table header lower than a vertical sheet",
    )
