import random
import string
from pathlib import Path

from docx import Document
from hamcrest import assert_that, equal_to

from app.policy.opening import Opening


def _word() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=8))


def test_opens_document_with_reference_relative_to_the_policy_folder(tmp_path: Path) -> None:
    word = _word()
    document = Document()
    document.add_paragraph(word)
    (tmp_path / "ДС").mkdir()
    document.save(str(tmp_path / "ДС" / "a.docx"))
    paper = Opening(tmp_path / "ДС" / "a.docx", tmp_path).survey().items()[0]
    assert_that(
        (paper.reference(), paper.text()),
        equal_to(("ДС/a.docx", word)),
        "Opening does not give the reference relative to the policy folder with the text",
    )


def test_names_unreadable_file_in_problems(tmp_path: Path) -> None:
    (tmp_path / "a.docx").write_bytes(b"")
    outcome = Opening(tmp_path / "a.docx", tmp_path).survey()
    assert_that(
        (outcome.items(), outcome.problems()),
        equal_to(((), ("Файл a.docx не удалось прочитать (a.docx)",))),
        "Opening does not name an unreadable file in problems",
    )


def test_names_empty_document_in_problems(tmp_path: Path) -> None:
    Document().save(str(tmp_path / "a.docx"))
    outcome = Opening(tmp_path / "a.docx", tmp_path).survey()
    assert_that(
        (outcome.items(), outcome.problems()),
        equal_to(((), ("Документ a.docx пустой, текста нет",))),
        "Opening does not name a document without text in problems",
    )


def test_names_legacy_doc_that_cannot_be_converted(tmp_path: Path) -> None:
    (tmp_path / "a.doc").write_bytes(b"x")
    outcome = Opening(tmp_path / "a.doc", tmp_path).survey()
    assert_that(
        (outcome.items(), outcome.problems()[0].endswith("(a.doc)")),
        equal_to(((), True)),
        "Opening does not name a legacy doc that cannot be converted",
    )
