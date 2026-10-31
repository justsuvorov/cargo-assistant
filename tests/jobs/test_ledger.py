import asyncio
import random
import sqlite3
from pathlib import Path

from hamcrest import assert_that, equal_to
from sqlalchemy import select

from app.jobs.database import Database
from app.jobs.ledger import Booked
from app.jobs.models import Base, LLMCall
from app.llm.ledger import Logged, Measured, Route


async def booked_rows(path: Path, jobs: tuple[int, int]) -> list[tuple[int, str, str, str, int]]:
    database = Database(f"sqlite+aiosqlite:///{path / 'l.db'}")
    async with database.session() as session:
        connection = await session.connection()
        await connection.run_sync(Base.metadata.create_all)
        await session.commit()
    loop = asyncio.get_running_loop()
    for job in jobs:
        ledger = Booked(database, loop, job, 10.0)
        call = Logged(
            "semantic",
            Route("vsk", "model-" + str(job)),
            "h" * 64,
            Measured((random.randint(1, 9), 2), 0.5, valid=True),
        )
        await asyncio.to_thread(ledger.record, call)
    async with database.session() as session:
        rows = (await session.execute(select(LLMCall).order_by(LLMCall.id))).scalars().all()
        found = [
            (r.job_id or 0, r.provider, r.model, r.prompt_hash[:1], r.tokens_out) for r in rows
        ]
    await database.close()
    return found


def test_writes_one_row_per_call_with_job_id(tmp_path: Path) -> None:
    first, second = random.randint(1, 50), random.randint(51, 99)
    rows = asyncio.run(asyncio.wait_for(booked_rows(tmp_path, (first, second)), 30))
    assert_that(
        rows,
        equal_to(
            [
                (first, "vsk", f"model-{first}", "h", 2),
                (second, "vsk", f"model-{second}", "h", 2),
            ]
        ),
        "Ledger does not write two rows with their job ids",
    )


async def failing(path: Path) -> str:
    database = Database(f"sqlite+aiosqlite:///{path / 'f.db'}")
    ledger = Booked(database, asyncio.get_running_loop(), 1, 10.0)
    call = Logged("semantic", Route("vsk", "m"), "h", Measured((1, 1), 0.1, valid=True))
    try:
        await asyncio.to_thread(ledger.record, call)
    except Exception as error:
        return type(error).__name__
    finally:
        await database.close()
    return ""


def test_raises_when_table_is_missing(tmp_path: Path) -> None:
    sqlite3.connect(tmp_path / "f.db").close()
    assert_that(
        asyncio.run(asyncio.wait_for(failing(tmp_path), 30)),
        equal_to("OperationalError"),
        "Ledger does not raise when the write fails",
    )
