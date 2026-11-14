import asyncio
import io
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from alembic import command
from alembic.config import Config
from docx import Document
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hamcrest import assert_that, contains_string, equal_to
from openpyxl import Workbook, load_workbook

from app.auth.identity import Identity, Person
from app.core.clock import Utc
from app.core.schema.environment import Environment
from app.core.settings import EnvSettings
from app.jobs.building import Workbench
from app.jobs.checking import Judge, Judges, Postponed, Postponing
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
from app.policy.conditions import SharedFile, SpecialConditions
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


class Unreachable:
    """Test double named unreachable: a process whose model gateway is not configured."""

    def model(self, job_id: int) -> Model:
        raise MisconfiguredError(f"Для задачи {job_id} не настроен шлюз модели")


class Spying:
    """Judges that remember the notes they were asked for and then postpone every question."""

    def __init__(self) -> None:
        self.notes: list[tuple[str, ...]] = []

    def judge(self, _job_id: int, notes: tuple[str, ...]) -> Judge:
        self.notes.append(notes)
        return Postponed()


async def work(config: EnvSettings, shared: SpecialConditions, judges: Judges) -> int:
    database = Database(config.database())
    queue = Queue(database, Utc())
    bench = Workbench(DiskStorage(config.storage()), config.soffice())
    kit = Kit(
        config.cards(),
        DiskStorage(config.storage()),
        Stamp("t", "c", "p", "m"),
        judges,
        ThreadPoolExecutor(2),
        shared,
    )
    folio = Folios(database, Utc())
    pipelines = Routed(
        Standard(Silent(), folio, database, bench, kit),
        Building(bench, folio, Shelving(database, queue), Unreachable(), Silent()),
    )
    count = await Shift(queue, pipelines, config, Silent(), Blank()).drain()
    await database.close()
    return count


def run_all(folder: Path) -> FastAPI:
    return staged(folder, SharedFile(Path(""), ()), (), Postponing())


def staged(
    folder: Path,
    shared: SpecialConditions,
    special: tuple[tuple[str, tuple[str, bytes]], ...],
    judges: Judges,
) -> FastAPI:
    config = settings(folder)
    application = create_app(config)
    with TestClient(application) as client:
        client.post(
            "/sessions",
            files=[
                ("files", ("Пример/ГП.docx", policy())),
                ("files", ("Пример/Декларации/a.xlsx", declaration())),
                *special,
            ],
        )
        client.post("/sessions/1/start", data={"declaration": ["Декларации/a.xlsx"]})
        asyncio.run(asyncio.wait_for(work(config, shared, judges), 60))
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


def test_hides_result_of_another_user_as_not_found(tmp_path: Path) -> None:
    application = run_all(tmp_path)
    application.state.services = replace(application.state.services, passport=Foreign())
    with TestClient(application) as client:
        codes = [
            client.get(path).status_code for path in ("/declarations/1", "/declarations/1/file")
        ]
    assert_that(codes, equal_to([404, 404]), "Result of another user is not hidden")


def test_links_the_result_from_the_page_of_the_session_and_back(tmp_path: Path) -> None:
    application = run_all(tmp_path)
    with TestClient(application) as client:
        session = client.get("/sessions/1").text
        result = client.get("/declarations/1").text
    assert_that(
        ['href="/declarations/1"' in session, 'href="/sessions/1"' in result],
        equal_to([True, True]),
        "Session and result page do not link to each other",
    )


def test_says_on_the_result_page_that_the_profile_was_not_built(tmp_path: Path) -> None:
    application = run_all(tmp_path)
    with TestClient(application) as client:
        html = client.get("/declarations/1").text
    assert_that(
        html,
        contains_string("Профиль полиса не собран"),
        "Result page does not say that the profile is missing",
    )


class Foreign:
    """Passport of a person who owns nothing."""

    def identity(self, token: str) -> Identity:
        return Person("x", "x" + token, frozenset({"user"}))


def shared_book(folder: Path, number: str, text: str) -> SpecialConditions:
    book = Workbook()
    sheet = book.create_sheet("ГП")
    sheet.append(("№ Генерального полиса", "Особые условия"))
    sheet.append((number, text))
    book.remove(book.worksheets[0])
    book.save(folder / "fsc.xlsx")
    return SharedFile(folder / "fsc.xlsx", ("№",))


def test_shows_special_conditions_of_both_files_on_the_result_page(tmp_path: Path) -> None:
    application = staged(
        tmp_path,
        shared_book(tmp_path, "0000T00GR0000", "Общее условие"),
        (("conditions", ("условия.txt", "Условие клиента\n".encode())),),
        Postponing(),
    )
    with TestClient(application) as client:
        html = client.get("/declarations/1").text
    assert_that(
        ("Условие клиента" in html, "Общее условие" in html, "выше" in html),
        equal_to((True, True, True)),
        "Result page does not show the special conditions of the client and of the shared file",
    )


def test_writes_special_conditions_with_source_and_priority_to_the_report(tmp_path: Path) -> None:
    application = staged(
        tmp_path,
        shared_book(tmp_path, "0000T00GR0000", "Общее условие"),
        (("conditions", ("условия.txt", "Условие клиента\n".encode())),),
        Postponing(),
    )
    with TestClient(application) as client:
        data = client.get("/declarations/1/file").content
    sheet = load_workbook(io.BytesIO(data))["Особые условия"]
    assert_that(
        tuple(sheet.iter_rows(min_row=2, values_only=True)),
        equal_to(
            (
                ("Условие клиента", "файл клиента", "выше"),
                (
                    "Общее условие",
                    "общий файл fsc.xlsx, лист «ГП», строка 2",
                    "обычный",
                ),
            )
        ),
        "Report does not list the conditions of both files with their source and priority",
    )


def test_tells_on_the_page_and_in_the_report_why_there_are_no_conditions(tmp_path: Path) -> None:
    application = run_all(tmp_path)
    with TestClient(application) as client:
        html = client.get("/declarations/1").text
        data = client.get("/declarations/1/file").content
    sheet = load_workbook(io.BytesIO(data))["Особые условия"]
    assert_that(
        (
            "путь к общему файлу особых условий не задан" in html,
            "путь к общему файлу особых условий не задан" in str(sheet["A2"].value),
        ),
        equal_to((True, True)),
        "Page and report do not tell the reasons why no special conditions were found",
    )


def test_shows_the_chosen_file_on_the_page_of_the_session(tmp_path: Path) -> None:
    application = staged(
        tmp_path,
        SharedFile(Path(""), ()),
        (("conditions", ("условия.txt", "Условие клиента\n".encode())),),
        Postponing(),
    )
    with TestClient(application) as client:
        html = client.get("/sessions/1").text
    assert_that(
        ("условия.txt" in html, "выбран отдельно от папки" in html),
        equal_to((True, True)),
        "Session page does not show which special conditions file was taken",
    )


def test_gives_the_found_conditions_to_the_semantic_judge_as_notes_once(tmp_path: Path) -> None:
    spy = Spying()
    staged(
        tmp_path,
        shared_book(tmp_path, "0000T00GR0000", "Общее условие"),
        (("conditions", ("условия.txt", "Условие клиента".encode())),),
        spy,
    )
    assert_that(
        spy.notes,
        equal_to(
            [
                (
                    "Условие клиента (источник: файл клиента; приоритет: выше)",
                    "Общее условие (источник: общий файл fsc.xlsx, лист «ГП», строка 2; "
                    "приоритет: обычный)",
                )
            ]
        ),
        "Semantic judge does not get the found conditions once with source and priority",
    )
