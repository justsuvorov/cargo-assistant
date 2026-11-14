import asyncio
import io
import json
import random
import string
import zipfile
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
from app.jobs.building import Models, Workbench
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
from app.llm.fake import FakeModel
from app.llm.model import Model
from app.storage.disk import DiskStorage
from app.web.application import create_app

_FIRST = "Декларации/Июнь/508.xlsx"
_SECOND = "Декларации/Июнь/511.xlsx"


class Silent:
    """Test double named silent."""

    def info(self, message: str, job_id: int, declaration_id: int) -> None:
        pass

    def warning(self, message: str, job_id: int, declaration_id: int) -> None:
        pass

    def error(self, message: str, job_id: int, declaration_id: int) -> None:
        pass


class Given:
    """Test double named given."""

    def __init__(self, model: Model) -> None:
        self._model = model

    def model(self, job_id: int) -> Model:
        del job_id
        return self._model


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


def settings(folder: Path) -> EnvSettings:
    url = f"sqlite+aiosqlite:///{folder / 'web.db'}"
    (folder / ".env").write_text(
        f"DATABASE_URL={url}\nSTORAGE_DIR={folder / 'files'}\nAUTH_DEV_MODE=true\n"
        "WORKER_POLL_INTERVAL=0.05\nWORKER_JOB_TIMEOUT=120\n",
        encoding="utf-8",
    )
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    return EnvSettings(Environment(str(folder / ".env")))


def as_user(application: FastAPI, sub: str) -> FastAPI:
    application.state.services = replace(
        application.state.services,
        passport=Sender(Person(sub, f"name-{sub}", frozenset({"user"}), frozenset())),
    )
    return application


def docx(*lines: str) -> bytes:
    document = Document()
    for line in lines:
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def number() -> str:
    return "".join(random.choices(string.ascii_uppercase, k=5)) + str(random.randint(100, 999))


def declaration(policy: str, own: str) -> bytes:
    book = Workbook()
    sheet = book.create_sheet("Декларация")
    for row, cells in (
        (1, {5: "Приложение № 2 к Генеральному Полису"}),
        (2, {7: f"№ {policy} от 26.08.2026 г."}),
        (8, {0: "Декларация", 3: f"№ Р-{own}", 4: "об отгрузке"}),
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


def folder(policy: str) -> list[tuple[str, tuple[str, bytes]]]:
    files = {
        "ГП.docx": docx(f"Генеральный полис страхования грузов № {policy}", "г. Город, 20.10.2025"),
        "ДС/ДС 1/соглашение.docx": docx(
            f"Дополнительное соглашение № {policy}-D00001",
            f"к Генеральному полису страхования грузов № {policy} от 20.10.2025 г.",
            "Пункт 6 принять в следующей редакции:",
            "Настоящее Дополнительное соглашение вступает в силу с 27.11.2025 г.",
        ),
        _FIRST: declaration(policy, "508"),
        _SECOND: declaration(policy, "511"),
    }
    return [("files", (f"Пример/{name}", data)) for name, data in files.items()]


def answers(policy: str) -> dict[str, str]:
    passage = {
        "key": "number",
        "point": "",
        "text": policy,
        "dates": ["2025-10-20"],
        "amounts": [],
        "entries": [],
    }
    return {
        "profile.policy": json.dumps({"passages": [passage]}),
        "profile.amendment.1": json.dumps({"passages": []}),
    }


async def work(config: EnvSettings, models: Models) -> int:
    database = Database(config.database())
    queue = Queue(database, Utc())
    storage = DiskStorage(config.storage())
    bench = Workbench(storage, config.soffice())
    folio = Folios(database, Utc())
    pool = ThreadPoolExecutor(2)
    kit = Kit(config.cards(), storage, Stamp("t", "c", "p", "m"), Postponing(), pool)
    pipelines = Routed(
        Standard(Silent(), folio, database, bench, kit),
        Building(bench, folio, Shelving(database, queue), models, Silent()),
    )
    count = await Shift(queue, pipelines, config, Silent(), Blank()).drain()
    pool.shutdown()
    await database.close()
    return count


def started(
    client: TestClient, paths: tuple[str, ...], files: list[tuple[str, tuple[str, bytes]]]
) -> int:
    opened = client.post("/sessions", files=files, follow_redirects=False)
    number_of = int(opened.headers["location"].rsplit("/", 1)[1])
    client.post(f"/sessions/{number_of}/start", data={"declaration": list(paths)})
    return number_of


def test_opens_the_page_of_a_new_session_with_a_choice_of_a_folder(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        html = client.get("/sessions/new").text
    assert_that(html, contains_string("webkitdirectory"), "New session does not offer a folder")


def test_leads_to_the_page_of_the_session_after_the_folder_is_opened(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path)), follow_redirects=False) as client:
        response = client.post("/sessions", files=folder(number()))
    assert_that(
        (response.status_code, response.headers["location"]),
        equal_to((303, "/sessions/1")),
        "Opened folder does not lead to the page of its session",
    )


def test_lists_declarations_of_the_folder_but_not_the_policy_and_the_addenda(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        client.post("/sessions", files=folder(number()))
        html = client.get("/sessions/1").text
    assert_that(
        (_FIRST in html, _SECOND in html, "ГП.docx" in html, "соглашение.docx" in html),
        equal_to((True, True, False, False)),
        "Page of a new session does not list exactly the declarations of the folder",
    )


def test_refuses_to_open_nothing(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        response = client.post("/sessions", files=[])
    assert_that(response.status_code >= 400, equal_to(True), "Empty choice of files is accepted")


def test_refuses_a_folder_with_a_path_leading_out(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        response = client.post("/sessions", files=[("files", ("a/../../x.xlsx", b"x"))])
    assert_that(response.status_code, equal_to(400), "Path leading out of the folder is accepted")


def test_opens_a_folder_packed_into_a_zip(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        for _, (name, data) in folder(number()):
            package.writestr(name, data)
    with TestClient(create_app(settings(tmp_path))) as client:
        client.post("/sessions", files=[("files", ("Пример.zip", buffer.getvalue()))])
        html = client.get("/sessions/1").text
    assert_that(
        (_FIRST in html, "Сессия 1: Пример" in html),
        equal_to((True, True)),
        "Zip of a folder is not opened as a folder with its name",
    )


def test_asks_to_choose_declarations_when_none_was_sent(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        client.post("/sessions", files=folder(number()))
        response = client.post("/sessions/1/start", data={})
    assert_that(
        (response.status_code, "Не выбрано ни одной декларации" in response.text),
        equal_to((409, True)),
        "Start without a choice is not refused with a message",
    )


def test_refuses_a_file_that_is_not_a_declaration_of_the_folder(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        client.post("/sessions", files=folder(number()))
        response = client.post("/sessions/1/start", data={"declaration": ["ГП.docx"]})
    assert_that(response.status_code, equal_to(409), "Policy file is started as a declaration")


def test_shows_the_started_declarations_with_their_state(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        started(client, (_FIRST,), folder(number()))
        html = client.get("/sessions/1").text
    assert_that(
        (_FIRST in html, _SECOND in html, "В очереди" in html, 'hx-trigger="every 3s"' in html),
        equal_to((True, False, True, True)),
        "Page of a started session does not show the chosen declarations as queued",
    )


def test_carries_a_folder_from_the_choice_to_the_result_files_and_the_zip(
    tmp_path: Path,
) -> None:
    policy = number()
    config = settings(tmp_path)
    application = create_app(config)
    with TestClient(application) as client:
        started(client, (_FIRST, _SECOND), folder(policy))
        count = asyncio.run(asyncio.wait_for(work(config, Given(FakeModel(answers(policy)))), 120))
        page = client.get("/sessions/1").text
        archive = client.get("/sessions/1/archive")
        files = [client.get(f"/declarations/{each}/file").content[:2] for each in (1, 2)]
    names = sorted(zipfile.ZipFile(io.BytesIO(archive.content)).namelist())
    assert_that(
        (
            count >= 3,
            names,
            files,
            "Профиль не подтверждён" in page,
            "Готово 2 из 2" in page,
        ),
        equal_to(
            (
                True,
                ["508 – результат проверки.xlsx", "511 – результат проверки.xlsx"],
                [b"PK", b"PK"],
                True,
                True,
            )
        ),
        "Folder does not go from the choice to result files and the archive of the session",
    )


def test_writes_to_the_result_file_that_the_profile_is_not_confirmed(tmp_path: Path) -> None:
    policy = number()
    config = settings(tmp_path)
    application = create_app(config)
    with TestClient(application) as client:
        started(client, (_FIRST,), folder(policy))
        asyncio.run(asyncio.wait_for(work(config, Given(FakeModel(answers(policy)))), 120))
        content = client.get("/declarations/1/file").content
    sheet = load_workbook(io.BytesIO(content))["Профиль полиса"]
    assert_that(
        str(sheet["A1"].value),
        contains_string("Профиль полиса не подтверждён"),
        "Result file does not say that the profile is not confirmed",
    )


def test_shows_honestly_that_the_profile_could_not_be_built_without_a_model(
    tmp_path: Path,
) -> None:
    config = settings(tmp_path)
    application = create_app(config)
    with TestClient(application) as client:
        started(client, (_FIRST, _SECOND), folder(number()))
        asyncio.run(asyncio.wait_for(work(config, Unreachable()), 120))
        page = client.get("/sessions/1").text
        result = client.get("/declarations/1").text
    assert_that(
        (
            "Профиль полиса не собран" in page,
            "Готово 2 из 2" in page,
            "Профиль полиса не собран" in result,
        ),
        equal_to((True, True, True)),
        "Session without a model does not show that the profile is missing and still finishes",
    )


def test_takes_the_profile_of_the_first_session_for_the_same_files(tmp_path: Path) -> None:
    policy = number()
    config = settings(tmp_path)
    application = create_app(config)
    model = FakeModel(answers(policy))
    files = folder(policy)
    with TestClient(application) as client:
        started(client, (_FIRST,), files)
        asyncio.run(asyncio.wait_for(work(config, Given(model)), 120))
        calls = model.count()
        started(client, (_SECOND,), files)
        asyncio.run(asyncio.wait_for(work(config, Given(model)), 120))
        page = client.get("/sessions/2").text
    assert_that(
        (model.count() - calls, "Готово 1 из 1" in page, "черновику" in page),
        equal_to((0, True, True)),
        "Second session of the same files builds the profile again",
    )


def test_lists_only_sessions_of_the_user(tmp_path: Path) -> None:
    application = create_app(settings(tmp_path))
    with TestClient(application) as client:
        as_user(application, "alice")
        client.post("/sessions", files=folder(number()))
        as_user(application, "bob")
        mine = client.get("/sessions").text
        as_user(application, "alice")
        hers = client.get("/sessions").text
    assert_that(
        ('href="/sessions/1"' in mine, 'href="/sessions/1"' in hers),
        equal_to((False, True)),
        "List of sessions shows a session of another user",
    )


def test_hides_the_session_of_another_user_on_every_page(tmp_path: Path) -> None:
    application = create_app(settings(tmp_path))
    with TestClient(application) as client:
        as_user(application, "alice")
        started(client, (_FIRST,), folder(number()))
        as_user(application, "bob")
        codes = [
            client.get("/sessions/1").status_code,
            client.get("/sessions/1/body").status_code,
            client.get("/sessions/1/archive").status_code,
            client.post("/sessions/1/start", data={"declaration": [_SECOND]}).status_code,
        ]
    assert_that(codes, equal_to([404, 404, 404, 404]), "Session of another user is not hidden")


def test_keeps_the_session_of_another_user_unstarted(tmp_path: Path) -> None:
    application = create_app(settings(tmp_path))
    with TestClient(application) as client:
        as_user(application, "alice")
        client.post("/sessions", files=folder(number()))
        as_user(application, "bob")
        client.post("/sessions/1/start", data={"declaration": [_SECOND]})
        as_user(application, "alice")
        html = client.get("/sessions/1").text
    assert_that(
        'action="/sessions/1/start"' in html,
        equal_to(True),
        "Another user starts the session of the owner",
    )


def test_hides_the_result_of_another_user_on_its_page_and_file(tmp_path: Path) -> None:
    policy = number()
    config = settings(tmp_path)
    application = create_app(config)
    with TestClient(application) as client:
        as_user(application, "alice")
        started(client, (_FIRST,), folder(policy))
        asyncio.run(asyncio.wait_for(work(config, Given(FakeModel(answers(policy)))), 120))
        own = client.get("/declarations/1/file").status_code
        as_user(application, "bob")
        codes = [
            client.get("/declarations/1").status_code,
            client.get("/declarations/1/file").status_code,
        ]
    assert_that((own, codes), equal_to((200, [404, 404])), "Result of another user is not hidden")


def test_answers_not_found_for_a_session_that_does_not_exist(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        response = client.get("/sessions/99")
    assert_that(response.status_code, equal_to(404), "Missing session is not reported")


def test_answers_not_found_for_the_archive_of_a_session_without_results(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        started(client, (_FIRST,), folder(number()))
        response = client.get("/sessions/1/archive")
    assert_that(response.status_code, equal_to(404), "Archive without results is offered")
