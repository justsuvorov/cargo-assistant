import asyncio
import random
import string
from datetime import date
from pathlib import Path

from hamcrest import assert_that, equal_to, raises
from sqlalchemy import select

from app.core.clock import Utc
from app.jobs.database import Database
from app.jobs.models import Base, Policy, PolicyDocument
from app.jobs.packages import Shelving
from app.jobs.queue import Queue
from app.policy.assembled import Assembled, Listed
from app.policy.papers import Agreement, Opened


def word() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=8))


async def prepare(path: Path, key: str) -> tuple[Database, Shelving, Queue]:
    database = Database(f"sqlite+aiosqlite:///{path / 'p.db'}")
    async with database.session() as session:
        connection = await session.connection()
        await connection.run_sync(Base.metadata.create_all)
        session.add(Policy(owner="u", package_sha="s", package_key=key))
        await session.commit()
    queue = Queue(database, Utc())
    return database, Shelving(database, queue), queue


async def finds_prefix(tmp_path: Path, key: str) -> str:
    database, shelving, _ = await prepare(tmp_path, key)
    try:
        return await shelving.prefix(1)
    finally:
        await database.close()


def test_gives_the_folder_of_the_session_that_brought_the_files_of_the_policy(
    tmp_path: Path,
) -> None:
    key = f"{word()}/7/folder"
    assert_that(
        asyncio.run(asyncio.wait_for(finds_prefix(tmp_path, key), 30)),
        equal_to(key),
        "Package does not point at the folder of the policy",
    )


def test_fails_loudly_for_a_policy_without_a_folder(tmp_path: Path) -> None:
    assert_that(
        lambda: asyncio.run(asyncio.wait_for(finds_prefix(tmp_path, ""), 30)),
        raises(LookupError),
        "Policy without a folder is not refused",
    )


async def rebuilds(tmp_path: Path) -> tuple[int, int, dict[str, object]]:
    database, shelving, queue = await prepare(tmp_path, "u/1/folder")
    first = await shelving.rebuild(1)
    again = await shelving.rebuild(1)
    async with database.session() as session:
        policy = await session.get(Policy, 1)
    snapshot = await queue.snapshot(again)
    await database.close()
    return (policy.job_id or 0) if policy else 0, first, snapshot.payload


def test_links_policy_to_its_last_build_job(tmp_path: Path) -> None:
    linked, first, payload = asyncio.run(asyncio.wait_for(rebuilds(tmp_path), 30))
    assert_that(
        (linked, first, payload),
        equal_to((2, 1, {"policy_id": 1})),
        "Policy does not point at the job of the last build",
    )


async def classifies(tmp_path: Path) -> list[tuple[str, str, str, tuple[str, ...]]]:
    database, shelving, _ = await prepare(tmp_path, "u/1/folder")
    package = Assembled(
        Opened("ГП.docx", "text"),
        (Agreement(Opened("ДС/ДС 1.docx", "text"), 1, date(2026, 1, 2), ("5",)),),
        Listed((), ()),
        (),
    )
    await shelving.classify(1, package)
    await shelving.classify(1, package)
    async with database.session() as session:
        rows = (await session.scalars(select(PolicyDocument).order_by(PolicyDocument.id))).all()
        found = [
            (row.kind, row.file_key, row.addendum_number, tuple(row.applies_to)) for row in rows
        ]
    await database.close()
    return found


def test_tells_the_documents_of_the_package_apart_once(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(classifies(tmp_path), 30)),
        equal_to(
            [
                ("policy", "u/1/folder/ГП.docx", "", ()),
                ("amendment", "u/1/folder/ДС/ДС 1.docx", "1", ("5",)),
            ]
        ),
        "Documents of the package are not told apart or are kept twice",
    )
