import asyncio
import hashlib
import random
from contextlib import suppress
from pathlib import Path

from hamcrest import assert_that, equal_to
from sqlalchemy import func, select

from app.core.clock import Utc
from app.jobs.database import Database
from app.jobs.intake import Intake
from app.jobs.models import Base, Declaration, Job
from app.jobs.queue import Queue
from app.storage.disk import DiskStorage
from app.storage.errors import EscapeError
from app.storage.layout import Keys


async def prepare(path: Path) -> tuple[Database, Intake, Queue]:
    database = Database(f"sqlite+aiosqlite:///{path / 'i.db'}")
    async with database.session() as session:
        connection = await session.connection()
        await connection.run_sync(Base.metadata.create_all)
        await session.commit()
    queue = Queue(database, Utc())
    return database, Intake(database, queue, DiskStorage(path / "files"), Keys(), Utc()), queue


async def stores_file_and_queues_reconcile_job(
    tmp_path: Path,
) -> tuple[bytes, str, dict[str, object]]:
    database, intake, queue = await prepare(tmp_path)
    data = random.randbytes(16)
    receipt = await intake.receive("a.xlsx", data, "fsc", "ivanov")
    snapshot = await queue.snapshot(receipt.job_id)
    stored = DiskStorage(tmp_path / "files").read(
        f"declarations/{receipt.declaration_id}/source/a.xlsx"
    )
    await database.close()
    return stored, snapshot.status, snapshot.payload


def test_stores_file_and_queues_reconcile_job(tmp_path: Path) -> None:
    stored_bytes, status, payload = asyncio.run(
        asyncio.wait_for(stores_file_and_queues_reconcile_job(tmp_path), 30)
    )
    assert_that(
        (status, payload, len(stored_bytes)),
        equal_to(("queued", {"declaration_id": 1}, 16)),
        "Upload is not stored and queued for reconciliation",
    )


async def keeps_no_declaration_when_file_name_is_unsafe(tmp_path: Path) -> int:
    database, intake, _ = await prepare(tmp_path)
    with suppress(EscapeError):
        await intake.receive("../x.xlsx", b"x", "fsc", "ivanov")
    async with database.session() as session:
        count = await session.scalar(select(func.count()).select_from(Declaration))
    await database.close()
    return count or 0


def test_keeps_no_declaration_when_file_name_is_unsafe(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(keeps_no_declaration_when_file_name_is_unsafe(tmp_path), 30)),
        equal_to(0),
        "Declaration is not removed after a refused file name",
    )


async def journals_uploader_group_and_file_hash(tmp_path: Path) -> tuple[str, str, str, str]:
    database, intake, _ = await prepare(tmp_path)
    data = random.randbytes(16)
    receipt = await intake.receive("a.xlsx", data, "fsc", "ivanov")
    async with database.session() as session:
        job = await session.get(Job, receipt.job_id)
        assert job is not None
        found = (
            job.uploaded_by,
            job.access_group,
            job.file_sha256,
            hashlib.sha256(data).hexdigest(),
        )
    await database.close()
    return found


def test_journals_uploader_group_and_file_hash_of_the_job(tmp_path: Path) -> None:
    uploader, group, digest, expected = asyncio.run(
        asyncio.wait_for(journals_uploader_group_and_file_hash(tmp_path), 30)
    )
    assert_that(
        (uploader, group, digest),
        equal_to(("ivanov", "fsc", expected)),
        "Job does not keep who uploaded the file, the group and the hash of the file",
    )
