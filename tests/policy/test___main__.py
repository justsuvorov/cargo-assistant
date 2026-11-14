import io
import json
from pathlib import Path

from docx import Document
from hamcrest import assert_that, contains_string, equal_to

from app.llm.fake import FakeModel
from app.policy.__main__ import build, main


def write(path: Path, *lines: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = Document()
    for line in lines:
        document.add_paragraph(line)
    document.save(str(path))


def policy(folder: Path) -> None:
    write(folder / "ГП" / "полис.docx", "Генеральный полис № 5 страхования грузов", "г. Город")


def test_writes_draft_profile_into_the_given_file(tmp_path: Path) -> None:
    policy(tmp_path / "p")
    model = FakeModel({"profile.policy": json.dumps({"passages": []})})
    build(tmp_path / "p", model, tmp_path / "out.json", io.StringIO())
    assert_that(
        sorted(json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))),
        equal_to(
            ["clauses", "conditions", "insurer", "issued", "number", "problems", "schema_version"]
        ),
        "Command does not write the draft profile into the file",
    )


def test_prints_problems_of_the_draft(tmp_path: Path) -> None:
    policy(tmp_path / "p")
    model = FakeModel({"profile.policy": json.dumps({"passages": []})})
    report = io.StringIO()
    build(tmp_path / "p", model, tmp_path / "out.json", report)
    assert_that(report.getvalue(), contains_string("Проблем:"), "Command does not list problems")


def test_reports_folder_without_policy(tmp_path: Path) -> None:
    (tmp_path / "p").mkdir()
    report = io.StringIO()
    code = build(tmp_path / "p", FakeModel({}), tmp_path / "out.json", report)
    assert_that(
        (code, "ГП" in report.getvalue() or "полис" in report.getvalue().lower()),
        equal_to((1, True)),
        "Command does not report a folder without the policy",
    )


def test_refuses_external_provider_without_permission(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("LLM_PROVIDER=anthropic\n", encoding="utf-8")
    assert_that(
        main(["build", str(tmp_path), "--env", str(tmp_path / ".env")]),
        equal_to(2),
        "Command does not stop an external provider without LLM_ALLOW_EXTERNAL",
    )
