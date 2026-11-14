import asyncio
import random
import string
from datetime import datetime
from pathlib import Path

from hamcrest import assert_that, equal_to, raises
from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from sqlalchemy import select

from app.domain.errors import UnreadableError
from app.jobs.binding import Binding, Ingesting
from app.jobs.building import Workbench
from app.jobs.database import Database
from app.jobs.models import Base, Declaration, Policy, Workspace
from app.jobs.queue import Snapshot
from app.storage.disk import DiskStorage


class Recording:
    """Test double named recording."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def info(self, message: str, job_id: int, declaration_id: int) -> None:
        self.lines.append(f"{message}, job_id={job_id}, declaration_id={declaration_id}")

    def warning(self, message: str, job_id: int, declaration_id: int) -> None:
        self.lines.append(f"{message}, job_id={job_id}, declaration_id={declaration_id}")

    def error(self, message: str, job_id: int, declaration_id: int) -> None:
        self.lines.append(f"{message}, job_id={job_id}, declaration_id={declaration_id}")


def word() -> str:
    return "".join(random.choices(string.ascii_uppercase, k=6)) + str(random.randint(100, 999))


def put(sheet: Worksheet, row: int, cells: dict[int, str]) -> None:
    for column, value in cells.items():
        sheet.cell(row=row, column=column + 1, value=value)


def russian(path: Path, policy: str, number: str, start: str) -> None:
    book = Workbook()
    sheet = book.create_sheet("Декларация")
    put(sheet, 1, {5: "Приложение № 2 к Генеральному Полису"})
    put(sheet, 2, {7: f"№ {policy} от 26.08.2026 г." if policy else ""})
    put(sheet, 4, {7: "От ООО «Тест»"})
    put(sheet, 8, {0: "Декларация", 3: f"№ Р-{number}", 4: "об отгрузке"})
    put(sheet, 16, {1: "1.", 2: "Полное наименование груза", 6: "мясо, сыр"})
    put(sheet, 20, {1: "4.", 2: "Страховая сумма", 6: "1000", 8: "рублей"})
    put(sheet, 21, {1: "5.", 2: "Транспорт", 6: "Авто"})
    put(sheet, 22, {1: "6.", 2: "Пункт отправления", 6: "г. Первый"})
    put(sheet, 24, {1: "8.", 2: "Пункт назначения", 6: "г. Второй"})
    put(sheet, 25, {1: "9.", 2: "Период страхования", 6: start, 7: "по", 8: "30.12.2026"})
    book.save(path)


def english(path: Path, policy: str, number: str, start: str) -> None:
    book = Workbook()
    sheet = book.create_sheet("Declaration")
    put(sheet, 1, {0: "Appendix 2 to the Open Cover"})
    put(sheet, 2, {7: f"No. {policy} dated 26.08.2026"})
    put(sheet, 3, {7: "From Test Trading LLC"})
    put(sheet, 4, {0: "Declaration", 3: f"No. {number}", 4: "of shipment"})
    put(sheet, 5, {1: "1.", 2: "Full description of cargo", 6: "frozen meat"})
    put(sheet, 6, {1: "4.", 2: "Sum insured", 6: "1500.50", 8: "euro"})
    put(sheet, 7, {1: "5.", 2: "Mode of transport", 6: "Truck"})
    put(sheet, 8, {1: "6.", 2: "Place of departure", 6: "Port A"})
    put(sheet, 9, {1: "8.", 2: "Place of destination", 6: "Port B"})
    put(sheet, 10, {1: "9.", 2: "Insurance period", 6: start, 7: "to", 8: "30.12.2026"})
    book.save(path)


async def prepared(tmp_path: Path, name: str, *, with_policy: bool = True) -> Database:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'b.db'}")
    async with database.session() as session:
        connection = await session.connection()
        await connection.run_sync(Base.metadata.create_all)
        session.add(Policy(owner="u", package_sha="s"))
        await session.flush()
        session.add(
            Workspace(
                owner="u",
                policy_id=1 if with_policy else None,
                found=[],
                created_at=datetime(2026, 1, 1),
            )
        )
        await session.flush()
        session.add(
            Declaration(
                owner="u",
                workspace_id=1,
                file_name=name,
                file_key=f"u/1/folder/{name}",
                created_at=datetime(2026, 1, 1),
            )
        )
        await session.commit()
    return database


def snapshot() -> Snapshot:
    return Snapshot(5, "reconcile", "running", "", 0, 1, "", {}, {"declaration_id": 1})


async def row(database: Database) -> Declaration:
    async with database.session() as session:
        found = (await session.scalars(select(Declaration))).one()
        session.expunge(found)
        return found


async def ingested(tmp_path: Path, make: str, policy: str, number: str, start: str) -> Declaration:
    name = "a.xlsx"
    storage = DiskStorage(tmp_path / "files")
    source = tmp_path / name
    {"ru": russian, "en": english}[make](source, policy, number, start)
    storage.save(f"u/1/folder/{name}", source.read_bytes())
    database = await prepared(tmp_path, name)
    await Ingesting(Workbench(storage, tmp_path / "home"), database, Recording()).run(snapshot())
    found = await row(database)
    await database.close()
    return found


def test_writes_number_form_rows_and_month_of_a_russian_declaration(tmp_path: Path) -> None:
    number = str(random.randint(100, 999))
    found = asyncio.run(
        asyncio.wait_for(ingested(tmp_path, "ru", word(), number, "21.09.2026"), 60)
    )
    assert_that(
        (found.number, found.form, found.shipments, found.month),
        equal_to((number, "vertical", 1, "2026-09")),
        "Ingest does not write the number, form, rows and month of a Russian declaration",
    )


def test_writes_number_form_rows_and_month_of_an_english_declaration(tmp_path: Path) -> None:
    number = str(random.randint(100, 999))
    found = asyncio.run(
        asyncio.wait_for(ingested(tmp_path, "en", word(), number, "03.11.2026"), 60)
    )
    assert_that(
        (found.number, found.form, found.shipments, found.month),
        equal_to((number, "vertical", 1, "2026-11")),
        "Ingest does not write the number, form, rows and month of an English declaration",
    )


async def ingest_leftovers(tmp_path: Path) -> list[str]:
    await ingested(tmp_path, "ru", word(), "5", "21.09.2026")
    return [path.name for path in (tmp_path / "home" / "work").iterdir()]


def test_removes_the_work_folder_of_the_declaration_after_reading(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(ingest_leftovers(tmp_path), 60)),
        equal_to([]),
        "Ingest does not remove the copy of the declaration from the work folder",
    )


async def ingest_garbage(tmp_path: Path) -> None:
    storage = DiskStorage(tmp_path / "files")
    storage.save("u/1/folder/a.xlsx", b"not a workbook")
    database = await prepared(tmp_path, "a.xlsx")
    try:
        await Ingesting(Workbench(storage, tmp_path / "home"), database, Recording()).run(
            snapshot()
        )
    finally:
        await database.close()


def test_fails_loudly_on_a_file_that_is_not_a_declaration(tmp_path: Path) -> None:
    assert_that(
        lambda: asyncio.run(asyncio.wait_for(ingest_garbage(tmp_path), 60)),
        raises(UnreadableError),
        "Ingest does not fail on a file that is not a declaration",
    )


async def bound(tmp_path: Path, *, with_policy: bool) -> tuple[Declaration, list[str]]:
    database = await prepared(tmp_path, "a.xlsx", with_policy=with_policy)
    journal = Recording()
    try:
        await Binding(database, journal).run(snapshot())
        found = await row(database)
    finally:
        await database.close()
    return found, journal.lines


def test_binds_the_declaration_to_the_policy_of_its_session(tmp_path: Path) -> None:
    found, _ = asyncio.run(asyncio.wait_for(bound(tmp_path, with_policy=True), 60))
    assert_that(
        (found.policy_id, found.binding),
        equal_to((1, "bound")),
        "Binding does not link the declaration to the policy of its session",
    )


def test_fails_loudly_when_the_session_has_no_policy(tmp_path: Path) -> None:
    assert_that(
        lambda: asyncio.run(asyncio.wait_for(bound(tmp_path, with_policy=False), 60)),
        raises(LookupError),
        "Binding does not fail when the session has no policy",
    )


def test_writes_the_binding_to_the_journal_with_job_and_declaration(tmp_path: Path) -> None:
    _, lines = asyncio.run(asyncio.wait_for(bound(tmp_path, with_policy=True), 60))
    assert_that(
        any("job_id=5" in line and "declaration_id=1" in line for line in lines),
        equal_to(True),
        "Journal does not name the job and the declaration of the binding",
    )
