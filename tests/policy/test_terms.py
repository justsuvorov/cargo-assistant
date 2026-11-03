from datetime import date

from hamcrest import assert_that, contains_exactly, empty, equal_to

from app.policy.terms import Terms


def _text(signed: str, effective: str, declarations: str) -> str:
    return "\n".join(
        (
            "Дополнительное соглашение № 9X13GR0001-D00004",
            "к Генеральному полису страхования грузов № 9X13GR0001 от 20.10.2017 г.",
            f"г. Город\t\t\t\t{signed}",
            "Страхователь действует на основании Доверенности № 5 от «01» июля 2020 г.",
            declarations,
            f"Настоящее Дополнительное соглашение вступает в силу с {effective}",
        )
    )


def test_reads_signing_date_from_the_line_after_the_policy_reference() -> None:
    terms = Terms(
        _text("«26» ноября 2020 г.", "«27» ноября 2020 г. и действует по «03» декабря 2021 г.", "")
    )
    assert_that(
        terms.signed(),
        contains_exactly(date(2020, 11, 26)),
        "Terms does not take the signing date from the line after the policy reference",
    )


def test_reads_effective_date_before_the_words_about_validity() -> None:
    terms = Terms(
        _text("«26» ноября 2020 г.", "«27» ноября 2020 г. и действует по «03» декабря 2021 г.", "")
    )
    assert_that(
        terms.effective(),
        contains_exactly(date(2020, 11, 27)),
        "Terms does not stop reading the effective date before the words about validity",
    )


def test_reads_dotted_effective_date() -> None:
    terms = Terms(_text("«26» ноября 2020 г.", "19.11.2024 г. и действует до 18.11.2026 г.", ""))
    assert_that(
        terms.effective(),
        contains_exactly(date(2024, 11, 19)),
        "Terms does not read a dotted effective date",
    )


def test_gives_no_effective_date_when_it_is_left_blank() -> None:
    terms = Terms(
        _text("«26» ноября 2020 г.", "  .  .2026 г. и действует по «03» декабря 2021 г.", "")
    )
    assert_that(
        terms.effective(),
        empty(),
        "Terms does not leave the effective date empty when it is blank",
    )


def test_gives_no_signing_date_when_it_is_left_blank() -> None:
    terms = Terms(_text("«     »            2026 г.", "19.11.2024 г.", ""))
    assert_that(
        terms.signed(),
        empty(),
        "Terms does not leave the signing date empty when it is blank",
    )


def test_reads_one_declaration() -> None:
    terms = Terms(
        _text("«26» ноября 2020 г.", "01.01.2021", "для перевозки по декларации № 154 об отгрузке:")
    )
    assert_that(
        terms.scope(),
        contains_exactly("154"),
        "Terms does not read the declaration of the scope",
    )


def test_reads_several_declarations_with_number_signs() -> None:
    terms = Terms(
        _text(
            "«26» ноября 2020 г.",
            "01.01.2021",
            "перевозок по декларациям № 415, № 416 об отгрузке:",
        )
    )
    assert_that(
        terms.scope(),
        contains_exactly("415", "416"),
        "Terms does not read declarations written with number signs",
    )


def test_reads_declarations_after_abbreviation() -> None:
    terms = Terms(_text("«26» ноября 2020 г.", "01.01.2021", "к декл. 357,358,359 об отгрузке"))
    assert_that(
        terms.scope(),
        contains_exactly("357", "358", "359"),
        "Terms does not read declarations that follow an abbreviation",
    )


def test_reads_english_declarations() -> None:
    terms = Terms(
        _text(
            "26 November 2020", "01.01.2021", "for shipments under declarations No. 12 and No. 13:"
        )
    )
    assert_that(
        terms.scope(),
        contains_exactly("12", "13"),
        "Terms does not read English declarations",
    )


def test_scope_is_empty_when_amendment_concerns_every_declaration() -> None:
    terms = Terms(
        _text(
            "«26» ноября 2020 г.",
            "01.01.2021 и действует до окончания периода страхования по Декларации.",
            "",
        )
    )
    assert_that(
        (terms.scope(), terms.unclear()),
        equal_to(((), False)),
        "Terms reads a scope into an amendment that names no declaration",
    )


def test_marks_scope_as_unclear_when_declaration_number_is_blank() -> None:
    terms = Terms(
        _text("«26» ноября 2020 г.", "01.01.2021", "по декларации №             об отгрузке:")
    )
    assert_that(
        (terms.scope(), terms.unclear()),
        equal_to(((), True)),
        "Terms does not mark a scope as unclear when the declaration number is blank",
    )


def test_skips_mention_of_declaration_without_number_before_the_scope() -> None:
    terms = Terms(
        _text(
            "«26» ноября 2020 г.",
            "01.01.2021",
            "срок действует по Декларации. Для перевозки по декларации № 77 об отгрузке:",
        )
    )
    assert_that(
        terms.scope(),
        contains_exactly("77"),
        "Terms does not find the real scope after a mention without number",
    )


def test_reads_declaration_after_words_about_shipment() -> None:
    terms = Terms(
        _text(
            "«26» ноября 2020 г.",
            "01.01.2021",
            "для перевозки по Декларации об отгрузке № 035, пункт 12.5. принять в редакции:",
        )
    )
    assert_that(
        terms.scope(),
        contains_exactly("035"),
        "Terms does not read a declaration after the words about shipment",
    )
