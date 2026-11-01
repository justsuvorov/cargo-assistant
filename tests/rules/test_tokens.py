from hamcrest import assert_that, equal_to

from app.rules.tokens import Tokens


def test_case_quotes_and_order_of_the_legal_form_do_not_matter() -> None:
    assert_that(
        Tokens("«Альфа-Тест» ООО", {}).same(Tokens('ООО "альфа-тест"', {})),
        equal_to(True),
        "Tokens does not ignore case, quotes and the order of the legal form",
    )


def test_abbreviation_from_synonyms_reads_as_full_name() -> None:
    assert_that(
        Tokens("ТД «Север»", {"ТД": "Торговый дом"}).same(Tokens("Торговый Дом Север", {})),
        equal_to(True),
        "Tokens does not spell out an abbreviation from the synonyms",
    )


def test_abbreviation_inside_a_word_stays() -> None:
    assert_that(
        Tokens("ТДК Север", {"ТД": "Торговый дом"}).words(),
        equal_to(("север", "тдк")),
        "Tokens does not keep an abbreviation that is only part of a word",
    )


def test_shorter_name_lies_within_longer() -> None:
    assert_that(
        Tokens("ООО Север", {}).within(Tokens("ООО Север Логистик", {})),
        equal_to(True),
        "Tokens does not see a name contained in a longer one",
    )


def test_empty_text_is_never_the_same() -> None:
    assert_that(
        Tokens("", {}).same(Tokens("«»", {})),
        equal_to(False),
        "Tokens does not refuse to match two texts without words",
    )
