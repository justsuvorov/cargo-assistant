import random

from hamcrest import assert_that, equal_to, raises

from app.storage.errors import EscapeError
from app.storage.layout import Keys


def test_places_policy_document_under_policy() -> None:
    policy = random.randint(1, 999)
    assert_that(
        Keys().policy(policy, "ds1.docx"),
        equal_to(f"policies/{policy}/documents/ds1.docx"),
        "Policy document key does not follow the layout",
    )


def test_places_declaration_source_under_declaration() -> None:
    declaration = random.randint(1, 999)
    assert_that(
        Keys().source(declaration, "a.xlsx"),
        equal_to(f"declarations/{declaration}/source/a.xlsx"),
        "Declaration source key does not follow the layout",
    )


def test_names_result_after_declaration_number() -> None:
    declaration = random.randint(1, 999)
    assert_that(
        Keys().result(declaration, "200/3"),
        equal_to(f"declarations/{declaration}/result/200_3 – результат проверки.xlsx"),
        "Result key does not carry the declaration number",
    )


def test_places_knowledge_source_under_ruleset() -> None:
    ruleset = random.randint(1, 999)
    assert_that(
        Keys().knowledge(ruleset, "base.docx"),
        equal_to(f"knowledge/{ruleset}/source/base.docx"),
        "Knowledge key does not follow the layout",
    )


def test_refuses_file_name_with_path() -> None:
    assert_that(
        lambda: Keys().source(random.randint(1, 99), "../../x.xlsx"),
        raises(EscapeError),
        "File name with a path is not refused",
    )


def test_keeps_relative_folders_in_policy_document_key() -> None:
    policy = random.randint(1, 999)
    assert_that(
        Keys().document(policy, r"ДС\ДС 1\a.doc"),
        equal_to(f"policies/{policy}/documents/ДС/ДС 1/a.doc"),
        "Document key does not keep the folders of the package",
    )


def test_refuses_document_path_leading_out_of_the_package() -> None:
    assert_that(
        lambda: Keys().document(1, "../x.doc"),
        raises(EscapeError),
        "Document key leading out of the package is not refused",
    )
