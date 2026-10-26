import random

from hamcrest import assert_that, equal_to

from tools.eval.mask import Anonymity


def test_mask_hides_policy_number() -> None:
    number = (
        f"{random.randint(1000, 9999)}{random.choice('0ATJP$')}{random.randint(10, 99)}"
        f"{random.choice(('G', 'GR'))}{random.randint(10000, 99999)}"
    )
    assert_that(
        number in Anonymity((), ()).hide(f"Указан № {number} от 26.08.2026"),
        equal_to(False),
        "Mask does not hide a policy number",
    )


def test_mask_gives_same_stub_to_same_policy() -> None:
    assert_that(
        Anonymity((), ()).hide("9999013G00011 и снова 9999013G00011"),
        equal_to("ГП-1 и снова ГП-1"),
        "Mask does not give one stub to one policy number",
    )


def test_mask_numbers_fragments_in_corpus_order() -> None:
    assert_that(
        Anonymity(("полис 9999013G00022",), ()).hide("9999J13GR00033, 9999013G00022"),
        equal_to("ГП-2, ГП-1"),
        "Mask does not number fragments in the order of the corpus",
    )


def test_mask_hides_company_with_nested_quotes() -> None:
    assert_that(
        Anonymity((), ()).hide("ООО «Торговый дом «Ромашка»» и ООО «ТД «РОМАШКА»»"),
        equal_to("Организация-1 и Организация-2"),
        "Mask does not hide companies with nested quotes",
    )


def test_mask_hides_company_with_unclosed_outer_quote() -> None:
    assert_that(
        Anonymity((), ()).hide("Указано АО «Издательский дом «Василёк». В п. 3"),
        equal_to("Указано Организация-1. В п. 3"),
        "Mask does not hide a company whose outer quote is left open",
    )


def test_mask_hides_company_in_straight_quotes() -> None:
    assert_that(
        Anonymity((), ()).hide('Страхователь ООО КОМПАНИЯ "ЛЮТИК".'),
        equal_to("Страхователь Организация-1."),
        "Mask does not hide a company in straight quotes",
    )


def test_mask_hides_foreign_company() -> None:
    assert_that(
        Anonymity((), ()).hide("Перевозчик Sample Harbour International Freight Co., Ltd."),
        equal_to("Перевозчик Организация-1"),
        "Mask does not hide a foreign company",
    )


def test_mask_hides_sole_trader_with_initials() -> None:
    assert_that(
        "Сидоренко" in Anonymity((), ()).hide("Указано «ИП Сидоренко П.Л.» в поле"),
        equal_to(False),
        "Mask does not hide a sole trader",
    )


def test_mask_hides_person_with_initials() -> None:
    assert_that(
        Anonymity((), ()).hide("подписал Петрова А.В."),
        equal_to("подписал Лицо-1"),
        "Mask does not hide a person with initials",
    )


def test_mask_hides_tax_number() -> None:
    number = str(random.randint(10**9, 10**10 - 1))
    assert_that(
        Anonymity((), ()).hide(f"ИНН {number}, КПП"),
        equal_to("ИНН-1, КПП"),
        "Mask does not hide a tax number",
    )


def test_mask_hides_street_address() -> None:
    assert_that(
        Anonymity((), ()).hide("Москва, ул. 2-я Полевая, д.5, к.1, эт.2"),
        equal_to("Москва, Адрес-1"),
        "Mask does not hide a street address with house parts",
    )


def test_mask_hides_named_street_before_marker() -> None:
    assert_that(
        Anonymity((), ()).hide("г.Ростов на Дону, Тихий пер. 12"),
        equal_to("г.Ростов на Дону, Адрес-1"),
        "Mask does not hide a street whose name comes before the marker",
    )


def test_mask_hides_mail_address() -> None:
    assert_that(
        Anonymity((), ()).hide("копия на someone.name@example.ru."),
        equal_to("копия на Почта-1."),
        "Mask does not hide a mail address",
    )


def test_mask_hides_glossary_name_in_any_case() -> None:
    assert_that(
        Anonymity((), ("Ромашкинс",)).hide("груз для РОМАШКИНС"),
        equal_to("груз для Название-1"),
        "Mask does not hide a glossary name written in capitals",
    )


def test_mask_keeps_plain_remark() -> None:
    assert_that(
        Anonymity((), ()).hide("некорректно, указания авто достаточно (п. 8 ГП)"),
        equal_to("некорректно, указания авто достаточно (п. 8 ГП)"),
        "Mask does not keep a remark without sensitive data",
    )
