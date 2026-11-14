import asyncio
import io
import json
import zipfile
from dataclasses import replace
from pathlib import Path

from alembic import command
from alembic.config import Config
from docx import Document
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hamcrest import assert_that, contains_string, equal_to

from app.auth.identity import Identity, Person
from app.core.clock import Utc
from app.core.schema.environment import Environment
from app.core.settings import EnvSettings
from app.jobs.building import Workbench
from app.jobs.database import Database
from app.jobs.folios import Folios
from app.jobs.logbook import Blank
from app.jobs.packages import Shelving
from app.jobs.queue import Queue
from app.jobs.stages import Building
from app.jobs.worker import Shift
from app.llm.fake import FakeModel
from app.llm.model import Model
from app.storage.disk import DiskStorage
from app.storage.layout import Keys
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

    def __init__(self, model: Model, seen: list[int]) -> None:
        self._model = model
        self._seen = seen

    def model(self, job_id: int) -> Model:
        self._seen.append(job_id)
        return self._model


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


def archive(*, with_policy: bool) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        if with_policy:
            package.writestr(
                "Полис/ГП/полис.docx",
                docx("Генеральный полис № 7 страхования грузов", "г. Город", "Условия"),
            )
        package.writestr("Полис/ДС/ДС 1/x.docx", docx("Пункт 6"))
    return buffer.getvalue()


async def work(config: EnvSettings, model: Model) -> None:
    database = Database(config.database())
    queue = Queue(database, Utc())
    storage = DiskStorage(config.storage())
    building = Building(
        Workbench(storage, config.soffice()),
        Folios(database, Utc()),
        Shelving(database, queue, storage, Keys()),
        Given(model, []),
        Silent(),
    )
    await asyncio.wait_for(Shift(queue, building, config, Silent(), Blank()).drain(), 60)
    await database.close()


def built(config: EnvSettings) -> None:
    asyncio.run(work(config, FakeModel({"profile.policy": json.dumps({"passages": []})})))


def upload(client: TestClient, data: bytes) -> None:
    client.post("/policies/upload", files=[("files", ("package.zip", data))])


def test_redirects_to_policy_page_after_upload(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path)), follow_redirects=False) as client:
        response = client.post(
            "/policies/upload", files=[("files", ("package.zip", archive(with_policy=True)))]
        )
    assert_that(
        (response.status_code, response.headers["location"]),
        equal_to((303, "/policies/1")),
        "Upload of a package does not lead to the page of the policy",
    )


def test_shows_queued_build_right_after_upload(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        upload(client, archive(with_policy=True))
        html = client.get("/policies/1").text
    assert_that(html, contains_string("В очереди"), "Fresh build is not shown as queued")


def test_stores_package_files_under_their_folders(tmp_path: Path) -> None:
    config = settings(tmp_path)
    with TestClient(create_app(config)) as client:
        upload(client, archive(with_policy=True))
    assert_that(
        (tmp_path / "files" / "policies" / "1" / "documents" / "ДС" / "ДС 1" / "x.docx").is_file(),
        equal_to(True),
        "Uploaded archive does not keep the folders of the package",
    )


def test_refuses_archive_that_leads_out_of_the_folder(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("../evil.docx", b"x")
    with TestClient(create_app(settings(tmp_path))) as client:
        response = client.post("/policies/upload", files=[("files", ("p.zip", buffer.getvalue()))])
    assert_that(response.status_code, equal_to(400), "Zip slip is not refused")


def test_refuses_upload_without_files(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        response = client.post("/policies/upload", data={"x": "y"})
    assert_that(response.status_code, equal_to(422), "Upload without files is not refused")


def test_accepts_folder_upload_with_relative_names(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        client.post(
            "/policies/upload",
            files=[
                ("files", ("Папка/ГП.docx", docx("a"))),
                ("files", ("Папка/ДС/ДС 1.docx", docx("b"))),
            ],
        )
    assert_that(
        (tmp_path / "files" / "policies" / "1" / "documents" / "ДС" / "ДС 1.docx").is_file(),
        equal_to(True),
        "Folder upload does not keep relative names",
    )


def test_shows_undefined_issue_date_and_problems_block(tmp_path: Path) -> None:
    config = settings(tmp_path)
    with TestClient(create_app(config)) as client:
        upload(client, archive(with_policy=True))
        built(config)
        html = client.get("/policies/1").text
    assert_that(
        ("не определена" in html, "Требует внимания эксперта" in html),
        equal_to((True, True)),
        "Page does not show the undefined date and the block of problems",
    )


def test_refuses_to_approve_profile_with_gaps(tmp_path: Path) -> None:
    config = settings(tmp_path)
    with TestClient(create_app(config)) as client:
        upload(client, archive(with_policy=True))
        built(config)
        response = client.post("/policies/1/approve", params={"version": 1})
    assert_that(
        (response.status_code, "Подтвердить нельзя" in response.text),
        equal_to((409, True)),
        "Profile with undefined requisites is not refused for approval",
    )


def test_approves_profile_after_expert_fills_requisites(tmp_path: Path) -> None:
    config = settings(tmp_path)
    with TestClient(create_app(config), follow_redirects=False) as client:
        upload(client, archive(with_policy=True))
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
        upload(client, archive(with_policy=True))
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
        upload(client, archive(with_policy=False))
        built(config)
        html = client.get("/policies/1").text
    assert_that(
        "Сборка профиля не удалась" in html,
        equal_to(True),
        "Failure of the build is not visible on the page of the policy",
    )


def test_lists_uploaded_policy(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        upload(client, archive(with_policy=True))
        html = client.get("/policies").text
    assert_that(
        'href="/policies/1"' in html,
        equal_to(True),
        "List of policies does not link the uploaded policy",
    )


def test_shows_status_of_build_job_on_job_page(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        upload(client, archive(with_policy=True))
        response = client.get("/jobs/1/status")
    assert_that(response.status_code, equal_to(200), "Status of the build job is not shown")


def test_answers_not_found_for_unknown_policy(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as client:
        response = client.get("/policies/99")
    assert_that(response.status_code, equal_to(404), "Unknown policy is not reported as missing")


class Sender:
    """Test double named sender."""

    def __init__(self, person: Person) -> None:
        self._person = person

    def identity(self, _token: str) -> Identity:
        return self._person


def signed_in(application: FastAPI, roles: set[str], groups: set[str]) -> FastAPI:
    application.state.services = replace(
        application.state.services,
        passport=Sender(Person("v", "visitor", frozenset(roles), frozenset(groups))),
    )
    return application


def built_policy(config: EnvSettings) -> FastAPI:
    application = create_app(config)
    with TestClient(application) as client:
        upload(client, archive(with_policy=True))
    built(config)
    return application


def test_refuses_package_upload_to_user_without_expert_role(tmp_path: Path) -> None:
    config = settings(tmp_path)
    with TestClient(signed_in(create_app(config), {"user"}, {"dev"})) as client:
        response = client.post(
            "/policies/upload", files=[("files", ("package.zip", archive(with_policy=True)))]
        )
    assert_that(
        (response.status_code, (tmp_path / "files" / "policies").exists()),
        equal_to((403, False)),
        "Upload of a package is not refused to a user without the expert role",
    )


def test_refuses_rebuild_to_user_without_expert_role(tmp_path: Path) -> None:
    application = built_policy(settings(tmp_path))
    with TestClient(signed_in(application, {"user"}, {"dev"})) as client:
        response = client.post("/policies/1/rebuild")
    assert_that(
        response.status_code,
        equal_to(403),
        "Rebuild is not refused to a user without the expert role",
    )


def test_refuses_edit_to_user_without_expert_role(tmp_path: Path) -> None:
    application = built_policy(settings(tmp_path))
    with TestClient(signed_in(application, {"user"}, {"dev"})) as client:
        response = client.post("/policies/1/profile", data={"number": "N-1"})
    assert_that(
        response.status_code,
        equal_to(403),
        "Edit of the profile is not refused to a user without the expert role",
    )


def test_refuses_approval_to_user_without_expert_role(tmp_path: Path) -> None:
    application = built_policy(settings(tmp_path))
    with TestClient(signed_in(application, {"user"}, {"dev"})) as client:
        response = client.post("/policies/1/approve", params={"version": 1})
    assert_that(
        response.status_code,
        equal_to(403),
        "Approval of the profile is not refused to a user without the expert role",
    )


def test_hides_buttons_of_the_expert_from_other_users(tmp_path: Path) -> None:
    application = built_policy(settings(tmp_path))
    with TestClient(signed_in(application, {"user"}, {"dev"})) as client:
        page = client.get("/policies/1").text
        listing = client.get("/policies").text
    assert_that(
        [
            marker in text
            for text, marker in (
                (page, "Подтвердить профиль версии"),
                (page, "Сохранить правки"),
                (page, "Собрать профиль заново"),
                (listing, "Загрузить пакет"),
            )
        ],
        equal_to([False, False, False, False]),
        "Pages do not hide the buttons of the expert from a user without the expert role",
    )


def test_shows_buttons_of_the_expert_to_the_expert(tmp_path: Path) -> None:
    application = built_policy(settings(tmp_path))
    with TestClient(signed_in(application, {"user", "expert"}, {"dev"})) as client:
        page = client.get("/policies/1").text
        listing = client.get("/policies").text
    assert_that(
        [
            marker in text
            for text, marker in (
                (page, "Подтвердить профиль версии"),
                (page, "Сохранить правки"),
                (page, "Собрать профиль заново"),
                (listing, "Загрузить пакет"),
            )
        ],
        equal_to([True, True, True, True]),
        "Pages do not show the buttons of the expert to the expert",
    )


def test_hides_policy_of_another_group_from_everybody(tmp_path: Path) -> None:
    application = built_policy(settings(tmp_path))
    with TestClient(signed_in(application, {"user", "expert"}, {"other"})) as client:
        codes = (
            client.get("/policies/1").status_code,
            client.post("/policies/1/rebuild").status_code,
            client.post("/policies/1/profile", data={"number": "N-1"}).status_code,
            client.post("/policies/1/approve", params={"version": 1}).status_code,
            'href="/policies/1"' in client.get("/policies").text,
        )
    assert_that(
        codes,
        equal_to((404, 404, 404, 404, False)),
        "Policy of another group is not hidden from an expert of a different group",
    )
