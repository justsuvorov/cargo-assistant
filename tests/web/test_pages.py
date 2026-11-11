import random
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from hamcrest import assert_that, contains_string, equal_to

from app.core.schema.environment import Environment
from app.core.settings import EnvSettings
from app.web.application import create_app


def settings(folder: Path) -> EnvSettings:
    url = f"sqlite+aiosqlite:///{folder / 'web.db'}"
    (folder / ".env").write_text(
        f"DATABASE_URL={url}\nSTORAGE_DIR={folder / 'files'}\nAUTH_DEV_MODE=true\n",
        encoding="utf-8",
    )
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    return EnvSettings(Environment(str(folder / ".env")))


def test_shows_all_three_pages(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        codes = [client.get(path).status_code for path in ("/policies", "/reconcile", "/archive")]
    assert_that(codes, equal_to([200, 200, 200]), "Some page does not open")


def test_redirects_root_to_reconcile_page(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path)), follow_redirects=False) as client:
        location = client.get("/").headers["location"]
    assert_that(location, equal_to("/reconcile"), "Root does not lead to the reconcile page")


def test_answers_health_check_without_token(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        body = client.get("/health").json()
    assert_that(body, equal_to({"status": "ok"}), "Health check does not answer")


def test_uploaded_file_appears_with_polling_status(tmp_path: Path) -> None:
    name = f"decl{random.randint(1, 999)}.xlsx"
    with TestClient(create_app(settings(tmp_path))) as client:
        html = client.post("/reconcile/upload", files=[("files", (name, b"x"))]).text
    assert_that(
        html,
        contains_string('hx-trigger="every 2s"'),
        "Uploaded file is not shown with a polling status",
    )


def test_lists_uploaded_file_in_archive(tmp_path: Path) -> None:
    name = f"decl{random.randint(1, 999)}.xlsx"
    with TestClient(create_app(settings(tmp_path))) as client:
        client.post("/reconcile/upload", files=[("files", (name, b"x"))])
        html = client.get("/archive").text
    assert_that(html, contains_string(name), "Archive does not list the uploaded file")


def test_status_fragment_of_queued_job_says_queued(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        client.post("/reconcile/upload", files=[("files", ("a.xlsx", b"x"))])
        html = client.get("/jobs/1/status").text
    assert_that(html, contains_string("В очереди"), "Queued job is not shown as queued")


def test_filters_archive_by_month(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        client.post("/reconcile/upload", files=[("files", ("a.xlsx", b"x"))])
        html = client.get("/archive", params={"month": "1999-01"}).text
    assert_that(
        "a.xlsx" in html,
        equal_to(False),
        "Archive filter does not drop declarations of another month",
    )


def test_shows_why_the_declaration_has_no_policy_on_the_job_and_archive_pages(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        client.post("/reconcile/upload", files=[("files", ("a.xlsx", b"x"))])
        with sqlite3.connect(tmp_path / "web.db") as connection:
            connection.execute("UPDATE declarations SET binding = 'policy_unknown'")
        pages = (client.get("/jobs/1/status").text, client.get("/archive").text)
    assert_that(
        ["не найден среди полисов вашей группы" in page for page in pages],
        equal_to([True, True]),
        "Pages do not show why the declaration is not bound to a policy",
    )


def test_does_not_show_a_reason_for_a_bound_declaration(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        client.post("/reconcile/upload", files=[("files", ("a.xlsx", b"x"))])
        with sqlite3.connect(tmp_path / "web.db") as connection:
            connection.execute("UPDATE declarations SET binding = 'bound'")
        html = client.get("/jobs/1/status").text
    assert_that(
        "binding" in html,
        equal_to(False),
        "Page does not stay free of reasons for a declaration that is bound to a policy",
    )
