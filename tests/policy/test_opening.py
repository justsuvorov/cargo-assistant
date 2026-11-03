import os
import random
import string
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from docx import Document
from hamcrest import assert_that, equal_to

from app.policy.opening import Opening


def _word() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=8))


@contextmanager
def _programs(folder: Path, script: str) -> Iterator[None]:
    folder.mkdir()
    if script:
        (folder / "soffice.bat").write_text(f"@echo off\n{script}\n", encoding="ascii")
        (folder / "soffice").write_text(f"#!/bin/sh\n{script}\n", encoding="ascii")
        (folder / "soffice").chmod(0o755)
    saved = os.environ["PATH"]
    os.environ["PATH"] = str(folder)
    try:
        yield
    finally:
        os.environ["PATH"] = saved


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


def test_names_legacy_doc_that_the_converter_fails_to_convert(tmp_path: Path) -> None:
    (tmp_path / "a.doc").write_bytes(b"x")
    with _programs(tmp_path / "bin", "exit 1"):
        outcome = Opening(tmp_path / "a.doc", tmp_path).survey()
    assert_that(
        (outcome.items(), outcome.problems()),
        equal_to(((), ("Файл a.doc не удалось преобразовать через LibreOffice (a.doc)",))),
        "Opening does not name a legacy doc that the converter fails to convert",
    )


def test_names_legacy_doc_when_the_converter_is_not_installed(tmp_path: Path) -> None:
    (tmp_path / "a.doc").write_bytes(b"x")
    with _programs(tmp_path / "bin", ""):
        outcome = Opening(tmp_path / "a.doc", tmp_path).survey()
    assert_that(
        (outcome.items(), outcome.problems()),
        equal_to(
            ((), ("Файл a.doc нельзя прочитать, потому что LibreOffice не установлен (a.doc)",))
        ),
        "Opening does not name a legacy doc when the converter is not installed",
    )
