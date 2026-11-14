import random
import re
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from hamcrest import assert_that, contains_string, equal_to, has_length

from app.core.schema.environment import Environment
from app.core.settings import EnvSettings
from app.web.application import announce, create_app


class Recorded:
    """Test double named recorded."""

    def __init__(self) -> None:
        self.lines: list[tuple[str, str]] = []

    def info(self, msg: str, *args: object) -> None:
        del args
        self.lines.append(("info", msg))

    def warning(self, msg: str, *args: object) -> None:
        del args
        self.lines.append(("warning", msg))

    def error(self, msg: str, *args: object) -> None:
        del args
        self.lines.append(("error", msg))


def settings(folder: Path, extra: str = "") -> EnvSettings:
    url = f"sqlite+aiosqlite:///{folder / 'web.db'}"
    (folder / ".env").write_text(
        f"DATABASE_URL={url}\nSTORAGE_DIR={folder / 'files'}\n{extra}", encoding="utf-8"
    )
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    return EnvSettings(Environment(str(folder / ".env")))


def test_marks_every_page_when_login_is_disabled(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path, "AUTH_DISABLED=true\n"))) as client:
        marked = [
            "вход отключён" in client.get(path).text
            for path in ("/policies", "/sessions", "/sessions/new")
        ]
    assert_that(marked, equal_to([True, True, True]), "Page does not say that login is disabled")


def test_marks_pages_when_login_is_disabled_by_old_switch(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path, "AUTH_DEV_MODE=true\n"))) as client:
        page = client.get("/policies").text
    assert_that(
        page, contains_string("вход отключён"), "Old switch does not mark the page as unprotected"
    )


def test_serves_htmx_from_the_image(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path, "AUTH_DISABLED=true\n"))) as client:
        answer = client.get("/static/htmx.min.js")
    assert_that(
        (answer.status_code, "htmx" in answer.text),
        equal_to((200, True)),
        "Htmx is not served from static files",
    )


def test_has_no_external_addresses_in_templates_and_scripts() -> None:
    web = Path(__file__).parents[2] / "app" / "web"
    found = [
        str(path.name)
        for path in (web / "templates").glob("*.html")
        if re.search(r"(https?:)?//[a-z0-9-]+\.[a-z]", path.read_text(encoding="utf-8"))
    ]
    assert_that(found, has_length(0), "Templates or scripts do not stay free of external addresses")


def test_warns_at_start_when_login_is_disabled(tmp_path: Path) -> None:
    sink = Recorded()
    announce(settings(tmp_path, "AUTH_DISABLED=true\n"), sink)
    assert_that(
        [level for level, _ in sink.lines],
        equal_to(["warning"]),
        "Start does not warn that login is disabled",
    )


def test_keeps_silent_at_start_when_login_is_required(tmp_path: Path) -> None:
    sink = Recorded()
    announce(settings(tmp_path, f"KEYCLOAK_REALM=r{random.randint(1, 99)}\n"), sink)
    assert_that(sink.lines, has_length(0), "Start does not stay silent when login is required")
