import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from alembic import command
from alembic.config import Config
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
from app.jobs.queue import Queue
from app.jobs.stages import Kit, Standard
from app.jobs.versions import Stamp
from app.jobs.worker import Shift
from app.storage.disk import DiskStorage
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


def declaration(folder: Path) -> bytes:
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
    book.save(folder / "d.xlsx")
    return (folder / "d.xlsx").read_bytes()


async def work(config: EnvSettings) -> int:
    database = Database(config.database())
    queue = Queue(database, Utc())
    bench = Workbench(DiskStorage(config.storage()), config.soffice())
    kit = Kit(
        config.cards(),
        DiskStorage(config.storage()),
        Stamp("t", "c", "p", "m"),
        Postponing(),
        ThreadPoolExecutor(2),
    )
    pipelines = Standard(Silent(), Folios(database, Utc()), database, bench, kit)
    count = await Shift(queue, pipelines, config, Silent(), Blank()).drain()
    await database.close()
    return count


def run_all(folder: Path) -> FastAPI:
    config = settings(folder)
    application = create_app(config)
    with TestClient(application) as client:
        client.post("/api/declarations", files=[("files", ("a.xlsx", declaration(folder)))])
        asyncio.run(asyncio.wait_for(work(config), 60))
    return application


def test_shows_result_table_of_a_checked_declaration(tmp_path: Path) -> None:
    application = run_all(tmp_path)
    with TestClient(application) as client:
        html = client.get("/declarations/1").text
    assert_that(
        ("Результат проверки" in html, "требует проверки" in html, "Скачать результат" in html),
        equal_to((True, True, True)),
        "Result page does not show the table and the link to the file",
    )


def test_filters_result_table_by_status(tmp_path: Path) -> None:
    application = run_all(tmp_path)
    with TestClient(application) as client:
        html = client.get("/declarations/1", params={"status": "mismatch"}).text
    assert_that(
        '<td style="background: #fff3cd"' in html,
        equal_to(False),
        "Filter by status does not drop rows of other statuses from the page",
    )


def test_downloads_result_workbook(tmp_path: Path) -> None:
    application = run_all(tmp_path)
    with TestClient(application) as client:
        response = client.get("/declarations/1/file")
    assert_that(
        (
            response.status_code,
            response.content[:2],
            "attachment" in response.headers["content-disposition"],
        ),
        equal_to((200, b"PK", True)),
        "Result file is not downloaded as a workbook",
    )


def test_hides_result_of_another_group_as_not_found(tmp_path: Path) -> None:
    application = run_all(tmp_path)
    application.state.services = replace(application.state.services, passport=Foreign())
    with TestClient(application) as client:
        codes = [
            client.get(path).status_code for path in ("/declarations/1", "/declarations/1/file")
        ]
    assert_that(codes, equal_to([404, 404]), "Result of another group is not hidden")


def test_links_the_result_from_the_job_page_and_archive(tmp_path: Path) -> None:
    application = run_all(tmp_path)
    with TestClient(application) as client:
        pages = (client.get("/jobs/1/status").text, client.get("/archive").text)
    assert_that(
        ['href="/declarations/1"' in page for page in pages],
        equal_to([True, True]),
        "Job page and archive do not link to the result",
    )


class Foreign:
    """Passport of a person from a group that owns nothing."""

    def identity(self, token: str) -> Identity:
        return Person("x", "x" + token, frozenset({"user"}), frozenset({"other"}))
