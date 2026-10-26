from hamcrest import assert_that, equal_to

from app.declarations.terms import ColumnTerms, Folded, Terms, VerticalTerms


def test_folded_drops_list_number_colon_and_spaces_around_hyphens() -> None:
    assert_that(
        Folded("  10. Товарно- транспортная   Накладная №: ").text(),
        equal_to("товарно-транспортная накладная №"),
        "Folded label does not lose list number, colon and spaces around hyphens",
    )


def test_terms_match_label_that_starts_with_a_variant() -> None:
    assert_that(
        Terms({"transport": ("вид транспорта",)}).key("Вид транспорта / Перевозчик"),
        equal_to("transport"),
        "Terms do not match a label that continues after the variant",
    )


def test_terms_refuse_variant_that_is_only_a_prefix_of_a_word() -> None:
    assert_that(
        Terms({"transport": ("транспорт",)}).key("Транспортная компания"),
        equal_to(""),
        "Terms do not refuse a label whose first word merely starts with the variant",
    )


def test_vertical_terms_know_russian_label_with_list_number() -> None:
    assert_that(
        VerticalTerms().key("7. Пункт перегрузки (таможенного оформления)"),
        equal_to("transshipment"),
        "Vertical terms do not know the Russian label of transshipment",
    )


def test_vertical_terms_know_english_label() -> None:
    assert_that(
        VerticalTerms().key("Full description of cargo"),
        equal_to("cargo"),
        "Vertical terms do not know the English label of cargo",
    )


def test_vertical_terms_tell_waybill_from_transport() -> None:
    assert_that(
        VerticalTerms().key("Transport document No."),
        equal_to("document"),
        "Vertical terms do not tell the transport document from the mode of transport",
    )


def test_vertical_terms_give_empty_key_to_unknown_label() -> None:
    assert_that(
        VerticalTerms().key("Приложение № 2 к Генеральному Полису"),
        equal_to(""),
        "Vertical terms give a key to a label that names no field",
    )


def test_column_terms_know_label_with_broken_hyphen_in_russian() -> None:
    assert_that(
        ColumnTerms().key("Номер товарно- транспортного документа"),
        equal_to("document_number"),
        "Column terms do not know the Russian label with a space after a hyphen",
    )


def test_column_terms_know_english_label_of_period_end() -> None:
    assert_that(
        ColumnTerms().key("End date"),
        equal_to("period_end"),
        "Column terms do not know the English label of the end of the period",
    )


def test_column_terms_take_transport_and_carrier_label_as_transport() -> None:
    assert_that(
        ColumnTerms().key("Вид транспорта и перевозчик"),
        equal_to("transport"),
        "Column terms do not take a combined transport and carrier label as transport",
    )
