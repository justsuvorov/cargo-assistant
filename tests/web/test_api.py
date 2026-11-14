import asyncio
import io
import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from alembic import command
from alembic.config import Config
from docx import Document
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hamcrest import assert_that, equal_to
from openpyxl import Workbook

from app.auth.identity import Identity, Person
from app.core.clock import Utc
from app.core.schema.environment import Environment
from app.core.settings import EnvSettings
from app.jobs.building import Workbench
from app.jobs.checking import Postponing
from app.jobs.database import Database
from app.jobs.folios import Folios
from app.jobs.logbook import Blank
from app.jobs.packages import Shelving
from app.jobs.queue import Queue
from app.jobs.stages import Building, Kit, Routed, Standard
from app.jobs.versions import Stamp
from app.jobs.worker import Shift
from app.llm.errors import MisconfiguredError
from app.llm.model import Model
from app.storage.disk import DiskStorage
from app.web.application import create_app

_DECLARATION = "Декларации/Июнь/508.xlsx"


class Silent:
    """Test double named silent."""

    def info(self, message: str, job_id: int, declaration_id: int) -> None:
        pass

    def warning(self, message: str, job_id: int, declaration_id: int) -> None:
        pass

    def error(self, message: str, job_id: int, declaration_id: int) -> None:
        pass


class Unreachable:
    """Test double named unreachable: a process whose model gateway is not configured."""

    def model(self, job_id: int) -> Model:
        raise MisconfiguredError(f"Для задачи {job_id} не настроен шлюз модели")


class Sender:
    """Test double named sender."""

    def __init__(self, person: Person) -> None:
        self._person = person

    def identity(self, _token: str) -> Identity:
        return self._person


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


def as_user(application: FastAPI, sub: str) -> None:
    application.state.services = replace(
        application.state.services,
        passport=Sender(Person(sub, f"name-{sub}", frozenset({"user"}), frozenset())),
    )


def declaration() -> bytes:
    book = Workbook()
    sheet = book.create_sheet("Декларация")
    for row, cells in (
        (1, {5: "Приложение № 2 к Генеральному Полису"}),
        (2, {7: "№ 0000T00GR0000 от 26.08.2026 г."}),
        (8, {0: "Декларация", 3: "№ Р-005", 4: "об отгрузке"}),
        (16, {1: "1.", 2: "Полное наименование груза", 6: "мясо, сыр"}),
        (20, {1: "4.", 2: "Страховая сумма", 6: "1000", 8: "рублей"}),
        (21, {1: "5.", 2: "Транспорт", 6: "Авто"}),
        (22, {1: "6.", 2: "Пункт отправления", 6: "г. Первый"}),
        (24, {1: "8.", 2: "Пункт назначения", 6: "г. Второй"}),
        (25, {1: "9.", 2: "Период страхования", 6: "21.09.2026", 7: "по", 8: "30.12.2026"}),
    ):
        for column, value in cells.items():
            sheet.cell(row=row, column=column + 1, value=value)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def policy() -> bytes:
    document = Document()
    document.add_paragraph("Генеральный полис страхования грузов № 0000T00GR0000")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def folder() -> list[tuple[str, tuple[str, bytes]]]:
    return [
        ("files", ("Пример/ГП.docx", policy())),
        ("files", (f"Пример/{_DECLARATION}", declaration())),
    ]


async def work(config: EnvSettings) -> int:
    database = Database(config.database())
    queue = Queue(database, Utc())
    storage = DiskStorage(config.storage())
    bench = Workbench(storage, config.soffice())
    folio = Folios(database, Utc())
    pool = ThreadPoolExecutor(2)
    kit = Kit(config.cards(), storage, Stamp("t", "c", "p", "m"), Postponing(), pool)
    pipelines = Routed(
        Standard(Silent(), folio, database, bench, kit),
        Building(bench, folio, Shelving(database, queue), Unreachable(), Silent()),
    )
    count = await Shift(queue, pipelines, config, Silent(), Blank()).drain()
    pool.shutdown()
    await database.close()
    return count


def test_opens_a_folder_and_lists_its_declarations(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        response = client.post("/api/sessions", files=folder())
    assert_that(
        (response.json()["id"], response.json()["found"], response.json()["started"]),
        equal_to((1, [_DECLARATION], False)),
        "Opened folder does not return its session with the declarations found",
    )


def test_starts_the_chosen_declarations_and_returns_their_numbers(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        client.post("/api/sessions", files=folder())
        response = client.post("/api/sessions/1/start", data={"declaration": [_DECLARATION]})
        session = client.get("/api/sessions/1").json()
    assert_that(
        (response.json(), session["started"], session["declarations"][0]["status"]),
        equal_to(({"declaration_ids": [1]}, True, "queued")),
        "Start does not queue the chosen declaration",
    )


def test_refuses_to_start_a_policy_file_with_a_conflict(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        client.post("/api/sessions", files=folder())
        response = client.post("/api/sessions/1/start", data={"declaration": ["ГП.docx"]})
    assert_that(response.status_code, equal_to(409), "Choice of a policy file is not refused")


def test_reports_done_status_with_every_stage_timed_after_the_worker_ran(tmp_path: Path) -> None:
    config = settings(tmp_path)
    with TestClient(create_app(config)) as client:
        client.post("/api/sessions", files=folder())
        client.post("/api/sessions/1/start", data={"declaration": [_DECLARATION]})
        asyncio.run(asyncio.wait_for(work(config), 60))
        session = client.get("/api/sessions/1").json()
        job = client.get(f"/api/jobs/{session['declarations'][0]['job_id']}").json()
    assert_that(
        (
            session["finished"],
            session["declarations"][0]["result"],
            session["profile"]["status"],
            job["status"],
            job["progress"],
            len(job["timings"]),
        ),
        equal_to((True, True, "missing", "done", 100, 8)),
        "Worker does not carry the declaration through all stages without a profile",
    )


def test_answers_not_found_for_unknown_job(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        response = client.get(f"/api/jobs/{random.randint(100, 999)}")
    assert_that(response.status_code, equal_to(404), "Unknown job is not reported as missing")


def test_refuses_the_folder_without_token_when_keycloak_is_on(tmp_path: Path) -> None:
    config = settings(tmp_path, "KEYCLOAK_URL=http://kc.invalid\nSESSION_SECRET=s3cret")
    with TestClient(create_app(config)) as client:
        response = client.post("/api/sessions", files=folder())
    assert_that(response.status_code, equal_to(401), "Folder without a token is not refused")


def test_lists_only_sessions_of_the_user_through_the_api(tmp_path: Path) -> None:
    application = create_app(settings(tmp_path))
    with TestClient(application) as client:
        as_user(application, "alice")
        client.post("/api/sessions", files=folder())
        as_user(application, "bob")
        mine = client.get("/api/sessions").json()
        as_user(application, "alice")
        hers = client.get("/api/sessions").json()
    assert_that(
        (mine, [item["id"] for item in hers]),
        equal_to(([], [1])),
        "List of sessions through the API shows a session of another user",
    )


def test_hides_the_session_of_another_user_in_every_call_of_the_api(tmp_path: Path) -> None:
    application = create_app(settings(tmp_path))
    with TestClient(application) as client:
        as_user(application, "alice")
        client.post("/api/sessions", files=folder())
        client.post("/api/sessions/1/start", data={"declaration": [_DECLARATION]})
        as_user(application, "bob")
        codes = [
            client.get("/api/sessions/1").status_code,
            client.post("/api/sessions/1/start", data={"declaration": [_DECLARATION]}).status_code,
            client.get("/api/jobs/1").status_code,
            client.get("/api/jobs/2").status_code,
        ]
    assert_that(
        codes,
        equal_to([404, 404, 404, 404]),
        "Session or job of another user is visible through the API",
    )


def test_shows_the_jobs_of_the_user_through_the_api(tmp_path: Path) -> None:
    application = create_app(settings(tmp_path))
    with TestClient(application) as client:
        as_user(application, "alice")
        client.post("/api/sessions", files=folder())
        client.post("/api/sessions/1/start", data={"declaration": [_DECLARATION]})
        codes = [client.get("/api/jobs/1").status_code, client.get("/api/jobs/2").status_code]
    assert_that(codes, equal_to([200, 200]), "User does not see the jobs of the own session")
