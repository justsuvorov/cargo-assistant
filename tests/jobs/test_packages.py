import asyncio
import random
from contextlib import suppress
from pathlib import Path

from hamcrest import assert_that, equal_to, raises
from sqlalchemy import select

from app.core.clock import Utc
from app.jobs.database import Database
from app.jobs.models import Base, Policy, PolicyDocument
from app.jobs.packages import Shelving
from app.jobs.queue import Queue
from app.storage.archive import Blob
from app.storage.disk import DiskStorage
from app.storage.errors import EscapeError
from app.storage.layout import Keys


async def prepare(path: Path) -> tuple[Database, Shelving, Queue]:
    database = Database(f"sqlite+aiosqlite:///{path / 'p.db'}")
    async with database.session() as session:
        connection = await session.connection()
        await connection.run_sync(Base.metadata.create_all)
        await session.commit()
    queue = Queue(database, Utc())
    return database, Shelving(database, queue, DiskStorage(path / "files"), Keys()), queue


async def stores_files_under_relative_paths(tmp_path: Path) -> tuple[bytes, str, dict[str, object]]:
    database, shelving, queue = await prepare(tmp_path)
    data = random.randbytes(16)
    registered = await shelving.receive((Blob("ДС/ДС 1/a.doc", data),), "g")
    snapshot = await queue.snapshot(registered.job_id)
    stored = DiskStorage(tmp_path / "files").read(
        f"policies/{registered.policy_id}/documents/ДС/ДС 1/a.doc"
    )
    await database.close()
    return stored, snapshot.kind, snapshot.payload


def test_stores_files_under_relative_paths_and_queues_build(tmp_path: Path) -> None:
    stored, kind, payload = asyncio.run(
        asyncio.wait_for(stores_files_under_relative_paths(tmp_path), 30)
    )
    assert_that(
        (len(stored), kind, payload),
        equal_to((16, "profile_build", {"policy_id": 1})),
        "Package is not stored under relative paths and queued for building",
    )


async def links_policy_to_its_build_job(tmp_path: Path) -> tuple[int, int]:
    database, shelving, _ = await prepare(tmp_path)
    registered = await shelving.receive((Blob("a.doc", b"x"),), "g")
    again = await shelving.rebuild(registered.policy_id)
    async with database.session() as session:
        policy = await session.get(Policy, registered.policy_id)
    await database.close()
    return (policy.job_id or 0) if policy else 0, again


def test_links_policy_to_its_last_build_job(tmp_path: Path) -> None:
    linked, again = asyncio.run(asyncio.wait_for(links_policy_to_its_build_job(tmp_path), 30))
    assert_that(
        (linked, again),
        equal_to((2, 2)),
        "Policy does not point at the job of the last build",
    )


async def keeps_nothing_after_escaping_path(tmp_path: Path) -> tuple[int, bool]:
    database, shelving, _ = await prepare(tmp_path)
    with suppress(EscapeError):
        await shelving.receive((Blob("a.doc", b"x"), Blob("../b.doc", b"y")), "g")
    async with database.session() as session:
        rows = len((await session.scalars(select(PolicyDocument))).all())
    await database.close()
    return rows, (tmp_path / "files" / "policies" / "1" / "documents" / "a.doc").exists()


def test_keeps_nothing_after_escaping_path(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(keeps_nothing_after_escaping_path(tmp_path), 30)),
        equal_to((0, False)),
        "Package with a path leading out does not leave rows and files out",
    )


async def receives_path_leading_out(tmp_path: Path) -> None:
    database, shelving, _ = await prepare(tmp_path)
    try:
        await shelving.receive((Blob("../b.doc", b"y"),), "g")
    finally:
        await database.close()


def test_refuses_package_with_path_leading_out(tmp_path: Path) -> None:
    assert_that(
        lambda: asyncio.run(asyncio.wait_for(receives_path_leading_out(tmp_path), 30)),
        raises(EscapeError),
        "Package with a path leading out is not refused",
    )
