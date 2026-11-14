import random
import uuid

from hamcrest import assert_that, equal_to, raises

from app.storage.errors import EscapeError
from app.storage.layout import Keys


def test_places_folder_of_session_under_owner() -> None:
    owner = uuid.uuid4().hex
    session = random.randint(1, 999)
    assert_that(
        Keys().folder(owner, session),
        equal_to(f"{owner}/{session}/folder"),
        "Folder key does not start with the owner",
    )


def test_keeps_relative_folders_in_key_of_a_file_of_the_folder() -> None:
    owner = uuid.uuid4().hex
    session = random.randint(1, 999)
    assert_that(
        Keys().entry(owner, session, r"Декларации\Июнь\508.xls"),
        equal_to(f"{owner}/{session}/folder/Декларации/Июнь/508.xls"),
        "Key of a file does not keep the folders of the session folder",
    )


def test_refuses_file_path_leading_out_of_the_folder() -> None:
    assert_that(
        lambda: Keys().entry("owner", 1, "../x.doc"),
        raises(EscapeError),
        "Path leading out of the folder is not refused",
    )


def test_names_result_after_declaration_number_under_owner() -> None:
    owner = uuid.uuid4().hex
    session = random.randint(1, 999)
    declaration = random.randint(1, 999)
    assert_that(
        Keys().result(owner, session, declaration, "200/3"),
        equal_to(f"{owner}/{session}/results/{declaration}/200_3 – результат проверки.xlsx"),
        "Result key does not carry the owner and the declaration number",
    )


def test_refuses_owner_that_leads_out_of_the_root() -> None:
    assert_that(
        lambda: Keys().folder("../other", 1),
        raises(EscapeError),
        "Owner with a path is not refused",
    )


def test_refuses_empty_owner() -> None:
    assert_that(
        lambda: Keys().folder("", 1),
        raises(EscapeError),
        "Empty owner is not refused",
    )


def test_places_knowledge_source_under_ruleset() -> None:
    ruleset = random.randint(1, 999)
    assert_that(
        Keys().knowledge(ruleset, "base.docx"),
        equal_to(f"knowledge/{ruleset}/source/base.docx"),
        "Knowledge key does not follow the layout",
    )


def test_places_the_chosen_conditions_file_of_a_session_under_the_owner() -> None:
    owner = uuid.uuid4().hex
    session = random.randint(1, 999)
    assert_that(
        Keys().chosen(owner, session, "условия.docx"),
        equal_to(f"{owner}/{session}/conditions/условия.docx"),
        "Key of the chosen conditions file does not lie under the owner and the session",
    )


def test_refuses_chosen_conditions_file_with_a_path() -> None:
    assert_that(
        lambda: Keys().chosen("o", 1, "../x.docx"),
        raises(EscapeError),
        "Keys does not refuse a name of the chosen conditions file with a path",
    )
