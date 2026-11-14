import asyncio
import io
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from alembic import command
from alembic.config import Config
from docx import Document
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hamcrest import assert_that, contains_string, equal_to
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
from app.jobs.models import PolicyProfile
from app.jobs.packages import Shelving
from app.jobs.queue import Queue
from app.jobs.stages import Building, Kit, Routed, Standard
from app.jobs.versions import Stamp
from app.jobs.worker import Shift
from app.llm.fake import FakeModel
from app.llm.model import Model
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


class Given:
    """Test double named given."""

    def __init__(self, model: Model) -> None:
        self._model = model

    def model(self, job_id: int) -> Model:
        del job_id
        return self._model


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
        "WORKER_JOB_TIMEOUT=60\n",
        encoding="utf-8",
    )
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    return EnvSettings(Environment(str(folder / ".env")))


def docx(*lines: str) -> bytes:
    document = Document()
    for line in lines:
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def declaration() -> bytes:
    book = Workbook()
    sheet = book.create_sheet("Декларация")
    for row, cells in (
        (2, {7: "№ 7 от 26.08.2026 г."}),
        (8, {0: "Декларация", 3: "№ Р-005", 4: "об отгрузке"}),
        (16, {1: "1.", 2: "Полное наименование груза", 6: "мясо, сыр"}),
        (25, {1: "9.", 2: "Период страхования", 6: "21.09.2026", 7: "по", 8: "30.12.2026"}),
    ):
        for column, value in cells.items():
            sheet.cell(row=row, column=column + 1, value=value)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def package(*, with_policy: bool) -> list[tuple[str, tuple[str, bytes]]]:
    files = {"Полис/ДС/ДС 1/x.docx": docx("Пункт 6"), "Полис/Декларации/a.xlsx": declaration()}
    if with_policy:
        files["Полис/ГП/полис.docx"] = docx(
            "Генеральный полис № 7 страхования грузов", "г. Город", "Условия"
        )
    return [("files", item) for item in files.items()]


async def work(config: EnvSettings, model: Model) -> None:
    database = Database(config.database())
    queue = Queue(database, Utc())
    storage = DiskStorage(config.storage())
    bench = Workbench(storage, config.soffice())
    folio = Folios(database, Utc())
    pool = ThreadPoolExecutor(2)
    kit = Kit(config.cards(), storage, Stamp("t", "c", "p", "m"), Postponing(), pool)
    pipelines = Routed(
        Standard(Silent(), folio, database, bench, kit),
        Building(bench, folio, Shelving(database, queue), Given(model), Silent()),
    )
    await asyncio.wait_for(Shift(queue, pipelines, config, Silent(), Blank()).drain(), 60)
    pool.shutdown()
    await database.close()


def built(config: EnvSettings) -> None:
    asyncio.run(work(config, FakeModel({"profile.policy": json.dumps({"passages": []})})))


def start(client: TestClient, *, with_policy: bool = True) -> None:
    client.post("/sessions", files=package(with_policy=with_policy))
    client.post("/sessions/1/start", data={"declaration": ["Декларации/a.xlsx"]})


def as_user(application: FastAPI, sub: str) -> FastAPI:
    application.state.services = replace(
        application.state.services,
        passport=Sender(Person(sub, f"name-{sub}", frozenset({"user"}))),
    )
    return application


def built_policy(config: EnvSettings) -> FastAPI:
    application = as_user(create_app(config), "alice")
    with TestClient(application) as client:
        start(client)
    built(config)
    return application


def test_shows_queued_build_right_after_the_start(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        start(client)
        html = client.get("/policies/1").text
    assert_that(html, contains_string("В очереди"), "Fresh build is not shown as queued")


def test_shows_undefined_issue_date_and_problems_block(tmp_path: Path) -> None:
    config = settings(tmp_path)
    with TestClient(create_app(config)) as client:
        start(client)
        built(config)
        html = client.get("/policies/1").text
    assert_that(
        ("не определена" in html, "Проблемы пакета полиса" in html),
        equal_to((True, True)),
        "Page does not show the undefined date and the block of problems",
    )


def test_refuses_to_approve_profile_with_gaps(tmp_path: Path) -> None:
    config = settings(tmp_path)
    with TestClient(create_app(config)) as client:
        start(client)
        built(config)
        response = client.post("/policies/1/approve", params={"version": 1})
    assert_that(
        (response.status_code, "Подтвердить нельзя" in response.text),
        equal_to((409, True)),
        "Profile with undefined requisites is not refused for approval",
    )


def test_approves_profile_after_the_owner_fills_requisites(tmp_path: Path) -> None:
    config = settings(tmp_path)
    with TestClient(create_app(config), follow_redirects=False) as client:
        start(client)
        built(config)
        client.post(
            "/policies/1/profile",
            data={"number": "N-1", "issued": "2025-10-20", "insurer": "Икс"},
        )
        approved = client.post("/policies/1/approve", params={"version": 2})
        html = client.get("/policies/1").text
    assert_that(
        (approved.status_code, "подтверждён" in html, "Локальный пользователь" in html),
        equal_to((303, True, True)),
        "Approved profile does not keep its version and who approved it",
    )


def test_refuses_edit_that_breaks_the_profile_schema(tmp_path: Path) -> None:
    config = settings(tmp_path)
    with TestClient(create_app(config)) as client:
        start(client)
        built(config)
        response = client.post("/policies/1/profile", data={"issued": "not a date"})
    assert_that(
        (response.status_code, "Правки не приняты" in response.text),
        equal_to((422, True)),
        "Edit that breaks the schema is not refused",
    )


def test_shows_failure_of_build_on_the_page(tmp_path: Path) -> None:
    config = settings(tmp_path)
    with TestClient(create_app(config)) as client:
        start(client, with_policy=False)
        built(config)
        html = client.get("/policies/1").text
    assert_that(
        "Сборка профиля не удалась" in html,
        equal_to(True),
        "Failure of the build is not visible on the page of the policy",
    )


def test_rebuilds_the_profile_for_the_owner(tmp_path: Path) -> None:
    config = settings(tmp_path)
    with TestClient(create_app(config), follow_redirects=False) as client:
        start(client)
        built(config)
        response = client.post("/policies/1/rebuild")
    assert_that(
        (response.status_code, response.headers["location"]),
        equal_to((303, "/policies/1")),
        "Owner cannot ask for the profile to be built again",
    )


def test_lists_the_policy_of_the_session(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        start(client)
        html = client.get("/policies").text
    assert_that(
        'href="/policies/1"' in html,
        equal_to(True),
        "List of policies does not link the policy of the session",
    )


def test_does_not_offer_to_upload_a_package_outside_a_session(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        html = client.get("/policies").text
        response = client.post("/policies/upload", files=package(with_policy=True))
    assert_that(
        ("Загрузить пакет" in html, response.status_code in {404, 405}),
        equal_to((False, True)),
        "Package can be uploaded outside a session, which is not allowed",
    )


def test_answers_not_found_for_unknown_policy(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        response = client.get("/policies/99")
    assert_that(response.status_code, equal_to(404), "Unknown policy is not reported as missing")


def test_hides_policy_of_another_user_from_everybody(tmp_path: Path) -> None:
    application = built_policy(settings(tmp_path))
    with TestClient(as_user(application, "bob")) as client:
        codes = (
            client.get("/policies/1").status_code,
            client.get("/policies/1/body").status_code,
            client.post("/policies/1/rebuild").status_code,
            client.post("/policies/1/profile", data={"number": "N-1"}).status_code,
            client.post("/policies/1/approve", params={"version": 1}).status_code,
            'href="/policies/1"' in client.get("/policies").text,
        )
    assert_that(
        codes,
        equal_to((404, 404, 404, 404, 404, False)),
        "Policy of another user is not hidden",
    )


def test_shows_the_policy_to_its_owner(tmp_path: Path) -> None:
    application = built_policy(settings(tmp_path))
    with TestClient(application) as client:
        codes = (client.get("/policies/1").status_code, client.get("/policies/1/body").status_code)
    assert_that(codes, equal_to((200, 200)), "Policy is not shown to its owner")


async def forget_version(config: EnvSettings) -> None:
    database = Database(config.database())
    async with database.session() as session:
        row = await session.get(PolicyProfile, 1)
        assert row is not None
        row.body = {**row.body, "schema_version": 9}
        await session.commit()
    await database.close()


def test_shows_a_clear_error_for_a_profile_of_an_unknown_version(tmp_path: Path) -> None:
    config = settings(tmp_path)
    with TestClient(create_app(config)) as client:
        start(client)
        built(config)
        asyncio.run(asyncio.wait_for(forget_version(config), 30))
        response = client.get("/policies/1")
    assert_that(
        (response.status_code, "Профиль нельзя прочитать" in response.text),
        equal_to((200, True)),
        "Page of the policy does not explain a profile of an unknown version",
    )
