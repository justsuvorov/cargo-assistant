import asyncio
import random
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from hamcrest import assert_that, equal_to

from app.core.clock import Utc
from app.core.schema.environment import Environment
from app.core.settings import EnvSettings
from app.jobs.database import Database
from app.jobs.queue import Queue
from app.jobs.stages import Standard
from app.jobs.worker import Shift
from app.web.application import create_app


class Silent:
    """Test double named silent."""

    def info(self, message: str, job_id: int, declaration_id: int) -> None:
        pass

    def warning(self, message: str, job_id: int, declaration_id: int) -> None:
        pass

    def error(self, message: str, job_id: int, declaration_id: int) -> None:
        pass


def settings(folder: Path, extra: str = "AUTH_DEV_MODE=true") -> EnvSettings:
    url = f"sqlite+aiosqlite:///{folder / 'web.db'}"
    (folder / ".env").write_text(
        f"DATABASE_URL={url}\nSTORAGE_DIR={folder / 'files'}\nWORKER_POLL_INTERVAL=0.05\n{extra}\n",
        encoding="utf-8",
    )
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    return EnvSettings(Environment(str(folder / ".env")))


def test_accepts_several_files_and_returns_job_per_file(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        response = client.post(
            "/api/declarations",
            files=[
                ("files", ("a.xlsx", random.randbytes(8))),
                ("files", ("b.xlsx", random.randbytes(8))),
            ],
        )
    assert_that(
        [(item["file"], item["job_id"]) for item in response.json()],
        equal_to([("a.xlsx", 1), ("b.xlsx", 2)]),
        "Upload does not return a job for every file",
    )


def test_reports_queued_status_right_after_upload(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        client.post("/api/declarations", files=[("files", ("a.xlsx", b"x"))])
        response = client.get("/api/jobs/1")
    assert_that(
        (response.json()["status"], response.json()["progress"]),
        equal_to(("queued", 0)),
        "Fresh job is not reported as queued with zero progress",
    )


async def work(config: EnvSettings) -> int:
    database = Database(config.database())
    count = await Shift(Queue(database, Utc()), Standard(Silent()), config, Silent()).drain()
    await database.close()
    return count


def test_reports_done_status_after_worker_ran(tmp_path: Path) -> None:
    config = settings(tmp_path)
    with TestClient(create_app(config)) as client:
        client.post("/api/declarations", files=[("files", ("a.xlsx", b"x"))])
        asyncio.run(asyncio.wait_for(work(config), 30))
        response = client.get("/api/jobs/1")
    assert_that(
        (response.json()["status"], response.json()["progress"], len(response.json()["timings"])),
        equal_to(("done", 100, 7)),
        "Worker does not carry the job through all stages",
    )


def test_answers_not_found_for_unknown_job(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        response = client.get(f"/api/jobs/{random.randint(100, 999)}")
    assert_that(response.status_code, equal_to(404), "Unknown job is not reported as missing")


def test_strips_directories_from_uploaded_file_name(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        response = client.post("/api/declarations", files=[("files", ("..\\..\\evil.xlsx", b"x"))])
    assert_that(
        response.json()[0]["file"],
        equal_to("evil.xlsx"),
        "Directories are not stripped from the uploaded file name",
    )


def test_refuses_upload_without_token_when_keycloak_is_on(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path, "KEYCLOAK_URL=http://kc.invalid"))) as client:
        response = client.post("/api/declarations", files=[("files", ("a.xlsx", b"x"))])
    assert_that(response.status_code, equal_to(401), "Upload without a token is not refused")
