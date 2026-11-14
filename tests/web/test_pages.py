from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from hamcrest import assert_that, equal_to

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


def test_redirects_root_to_the_list_of_sessions(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path)), follow_redirects=False) as client:
        location = client.get("/").headers["location"]
    assert_that(location, equal_to("/sessions"), "Root does not lead to the list of sessions")


def test_answers_health_check_without_token(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        body = client.get("/health").json()
    assert_that(body, equal_to({"status": "ok"}), "Health check does not answer")


def test_does_not_keep_the_old_pages_of_upload_and_archive(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        codes = [client.get(path).status_code for path in ("/reconcile", "/archive")]
    assert_that(codes, equal_to([404, 404]), "Old pages of the upload are still served")
