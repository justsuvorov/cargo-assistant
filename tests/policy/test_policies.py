from pathlib import Path

from docx import Document
from hamcrest import assert_that, contains_exactly, equal_to, raises

from app.domain.errors import UnreadableError
from app.policy.policies import Policies


def _write(path: Path, *lines: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = Document()
    for line in lines:
        document.add_paragraph(line)
    document.save(str(path))
    return path


def test_finds_policy_among_attachments_by_its_first_line(tmp_path: Path) -> None:
    attachment = _write(tmp_path / "a.docx", "Приложение № 3 к Генеральному полису № 1", "Текст")
    policy = _write(tmp_path / "b.docx", "Генеральный полис № 1 страхования грузов", "Текст")
    outcome = Policies((attachment, policy), tmp_path).survey()
    assert_that(
        ([paper.reference() for paper in outcome.items()], outcome.problems()),
        equal_to((["b.docx"], ())),
        "Policies do not find the policy among attachments by the first line",
    )


def test_finds_policy_in_subfolder(tmp_path: Path) -> None:
    policy = _write(tmp_path / "ГП" / "x.docx", "Генеральный полис № 1", "Текст")
    assert_that(
        [paper.reference() for paper in Policies((policy,), tmp_path).survey().items()],
        contains_exactly("ГП/x.docx"),
        "Policies do not find the policy that lies in the subfolder",
    )


def test_refuses_folder_without_policy_text(tmp_path: Path) -> None:
    attachment = _write(tmp_path / "a.docx", "Приложение № 3 к Генеральному полису № 1")
    assert_that(
        lambda: Policies((attachment,), tmp_path).survey(),
        raises(UnreadableError, "не найден текст Генерального полиса"),
        "Policies do not refuse a folder where no policy text was found",
    )


def test_refuses_empty_folder(tmp_path: Path) -> None:
    assert_that(
        lambda: Policies((), tmp_path).survey(),
        raises(UnreadableError, "не найден текст Генерального полиса"),
        "Policies do not refuse a folder without files",
    )


def test_error_carries_problems_of_unreadable_files(tmp_path: Path) -> None:
    broken = tmp_path / "scan.docx"
    broken.write_bytes(b"")
    assert_that(
        lambda: Policies((broken,), tmp_path).survey(),
        raises(UnreadableError, "scan.docx"),
        "Policies do not name unreadable files in the error",
    )


def test_takes_longest_of_several_candidates_and_names_all(tmp_path: Path) -> None:
    short = _write(tmp_path / "a.docx", "Генеральный полис № 1", "Коротко")
    long = _write(tmp_path / "b.docx", "Генеральный полис № 1", "Текст " * 100)
    outcome = Policies((short, long), tmp_path).survey()
    assert_that(
        (
            [paper.reference() for paper in outcome.items()],
            outcome.problems(),
        ),
        equal_to(
            (
                ["b.docx"],
                (
                    "Найдено несколько кандидатов на ГП (a.docx, b.docx),"
                    " взят самый длинный: b.docx",
                ),
            )
        ),
        "Policies do not name all candidates when several files look like the policy",
    )


def test_keeps_policy_when_other_file_is_unreadable(tmp_path: Path) -> None:
    policy = _write(tmp_path / "a.docx", "Генеральный полис № 1", "Текст")
    broken = tmp_path / "b.docx"
    broken.write_bytes(b"")
    outcome = Policies((policy, broken), tmp_path).survey()
    assert_that(
        (len(outcome.items()), "".join(outcome.problems())),
        equal_to((1, "Файл b.docx не удалось прочитать (b.docx)")),
        "Policies do not keep the policy when another file cannot be read",
    )


def test_ignores_files_that_are_not_documents(tmp_path: Path) -> None:
    policy = _write(tmp_path / "a.docx", "Генеральный полис № 1", "Текст")
    (tmp_path / "scan.pdf").write_bytes(b"%PDF")
    outcome = Policies((policy, tmp_path / "scan.pdf"), tmp_path).survey()
    assert_that(
        outcome.problems(),
        equal_to(()),
        "Policies name a scan or a sheet that cannot be the policy text",
    )


def test_error_mentions_scans_when_only_pdf_found(tmp_path: Path) -> None:
    (tmp_path / "scan.pdf").write_bytes(b"%PDF")
    assert_that(
        lambda: Policies((tmp_path / "scan.pdf",), tmp_path).survey(),
        raises(UnreadableError, "scan.pdf"),
        "Policies do not mention a scan that cannot be read",
    )
