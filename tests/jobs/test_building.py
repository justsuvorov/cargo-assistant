import asyncio
import io
import json
import uuid
import zipfile
from datetime import date
from pathlib import Path

from docx import Document
from hamcrest import assert_that, contains_string, equal_to
from sqlalchemy import select

from app.core.clock import Utc
from app.core.schema.environment import Environment
from app.core.settings import EnvSettings
from app.jobs.building import Workbench
from app.jobs.database import Database
from app.jobs.folios import Folios
from app.jobs.logbook import Blank
from app.jobs.models import Base, Policy, PolicyDocument
from app.jobs.packages import Shelving
from app.jobs.queue import Queue
from app.jobs.stages import Building
from app.jobs.worker import Shift
from app.llm.fake import FakeModel
from app.llm.model import Model
from app.storage.archive import Blob, Unzipped
from app.storage.disk import DiskStorage
from app.storage.tree import Tree


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


def docx(*lines: str) -> bytes:
    document = Document()
    for line in lines:
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def passage(key: str, text: str, dates: list[str]) -> dict[str, object]:
    return {"key": key, "point": "", "text": text, "dates": dates, "amounts": [], "entries": []}


def package(number: str) -> tuple[Blob, ...]:
    return (
        Blob(
            "Пакет/ГП/полис.docx",
            docx(
                f"Генеральный полис № {number} страхования грузов",
                "г. Город, 20.10.2025",
                "Условия",
            ),
        ),
        Blob(
            "Пакет/ДС/ДС 1/соглашение.docx",
            docx(
                f"Дополнительное соглашение № {number}-D00001",
                f"к Генеральному полису страхования грузов № {number} от 20.10.2025 г.",
                "г. Город\t\t«26» ноября 2025 г.",
                "Пункт 6 принять в следующей редакции:",
                "Настоящее Дополнительное соглашение вступает в силу с 27.11.2025 г.",
            ),
        ),
    )


async def build(tmp_path: Path, files: tuple[Blob, ...], model: Model) -> tuple[Database, int, int]:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'b.db'}")
    async with database.session() as session:
        connection = await session.connection()
        await connection.run_sync(Base.metadata.create_all)
        await session.commit()
    queue = Queue(database, Utc())
    storage = DiskStorage(tmp_path / "files")
    shelving = Shelving(database, queue)
    for file in Tree(files).files():
        storage.save(f"u/1/folder/{file.name()}", file.data())
    async with database.session() as session:
        policy = Policy(owner="u", package_sha="s", package_key="u/1/folder")
        session.add(policy)
        await session.flush()
        policy.job_id = await queue.add(session, "profile_build", {"policy_id": policy.id})
        await session.commit()
    (tmp_path / ".env").write_text("WORKER_JOB_TIMEOUT=60\n", encoding="utf-8")
    pipelines = Building(
        Workbench(storage, tmp_path / "soffice"),
        Folios(database, Utc()),
        shelving,
        Given(model, []),
        Silent(),
    )
    await Shift(
        queue, pipelines, EnvSettings(Environment(str(tmp_path / ".env"))), Silent(), Blank()
    ).drain()
    return database, policy.id, policy.job_id or 0


async def saves_draft_with_requisites_from_the_model(tmp_path: Path) -> tuple[str, date, str]:
    number = uuid.uuid4().hex[:8]
    answers = {
        "profile.policy": json.dumps(
            {"passages": [passage("number", number, ["2025-10-20"]), passage("insurer", "Икс", [])]}
        ),
        "profile.amendment.1": json.dumps({"passages": []}),
    }
    database, policy, job = await build(tmp_path, package(number), FakeModel(answers))
    profile = (await Folios(database, Utc()).latest(policy)).profile
    snapshot = await Queue(database, Utc()).snapshot(job)
    await database.close()
    return (profile.number == number and "x") or "", profile.issued, snapshot.status


def test_saves_draft_with_requisites_from_the_model(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(saves_draft_with_requisites_from_the_model(tmp_path), 60)),
        equal_to(("x", date(2025, 10, 20), "done")),
        "Build job does not save the draft profile with the requisites of the model",
    )


async def times_every_stage_of_the_build(tmp_path: Path) -> list[str]:
    answers = {"profile.policy": json.dumps({"passages": []})}
    database, _, job = await build(tmp_path, package("77")[:1], FakeModel(answers))
    snapshot = await Queue(database, Utc()).snapshot(job)
    await database.close()
    return sorted(snapshot.timings)


def test_times_every_stage_of_the_build(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(times_every_stage_of_the_build(tmp_path), 60)),
        equal_to(["convert", "extract", "fetch", "read", "save"]),
        "Build job does not time every stage",
    )


async def counts_one_request_per_document(tmp_path: Path) -> int:
    model = FakeModel(
        {
            "profile.policy": json.dumps({"passages": []}),
            "profile.amendment.1": json.dumps({"passages": []}),
        }
    )
    database, _, _ = await build(tmp_path, package("5"), model)
    await database.close()
    return model.count()


def test_counts_one_request_per_document(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(counts_one_request_per_document(tmp_path), 60)),
        equal_to(2),
        "Build job does not ask the model once per document",
    )


async def fails_with_message_when_policy_text_is_missing(tmp_path: Path) -> tuple[str, str]:
    files = (Blob("Пакет/ДС/ДС 1/соглашение.docx", docx("Пункт 6")),)
    database, _, job = await build(tmp_path, files, FakeModel({}))
    snapshot = await Queue(database, Utc()).snapshot(job)
    await database.close()
    return snapshot.status, snapshot.error


def test_fails_with_message_when_policy_text_is_missing(tmp_path: Path) -> None:
    status, error = asyncio.run(
        asyncio.wait_for(fails_with_message_when_policy_text_is_missing(tmp_path), 60)
    )
    assert_that(
        (status, error),
        equal_to(("failed", error)),
        "Build job without the policy does not fail",
    )


async def failure_without_policy(tmp_path: Path) -> str:
    files = (Blob("Пакет/ДС/ДС 1/соглашение.docx", docx("Пункт 6")),)
    database, _, job = await build(tmp_path, files, FakeModel({}))
    error = (await Queue(database, Utc()).snapshot(job)).error
    await database.close()
    return error


def test_names_the_missing_policy_in_the_failure(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(failure_without_policy(tmp_path), 60)),
        contains_string("UnreadableError"),
        "Failure of the build does not say what was unreadable",
    )


async def marks_documents_by_what_they_are(tmp_path: Path) -> list[tuple[str, str]]:
    answers = {
        "profile.policy": json.dumps({"passages": []}),
        "profile.amendment.1": json.dumps({"passages": []}),
    }
    database, _, _ = await build(tmp_path, package("9"), FakeModel(answers))
    async with database.session() as session:
        rows = (await session.scalars(select(PolicyDocument).order_by(PolicyDocument.id))).all()
    await database.close()
    return [(row.kind, row.addendum_number) for row in rows]


def test_marks_documents_by_what_they_are(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(marks_documents_by_what_they_are(tmp_path), 60)),
        equal_to([("policy", ""), ("amendment", "1")]),
        "Build job does not mark the policy and the amendment documents",
    )


def test_keeps_archive_folders_in_the_stored_package() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Полис/ДС/ДС 2/файл.docx", b"x")
        archive.writestr("Полис/ГП.docx", b"y")
    names = sorted(file.name() for file in Tree(Unzipped(buffer.getvalue()).files()).files())
    assert_that(
        names,
        equal_to(["ГП.docx", "ДС/ДС 2/файл.docx"]),
        "Archive folders are not kept in the stored package",
    )


async def works_inside_the_home_folder(tmp_path: Path) -> tuple[bool, list[str]]:
    answers = {"profile.policy": json.dumps({"passages": []})}
    database, _, _ = await build(tmp_path, package("77")[:1], FakeModel(answers))
    await database.close()
    work = tmp_path / "soffice" / "work"
    return work.is_dir(), [path.name for path in work.iterdir()]


def test_unpacks_the_package_inside_the_home_folder_and_removes_it(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(works_inside_the_home_folder(tmp_path), 60)),
        equal_to((True, [])),
        "Build does not unpack the package inside the home folder or does not remove it",
    )
