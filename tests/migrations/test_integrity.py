import asyncio
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from hamcrest import assert_that, equal_to
from sqlalchemy import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.jobs.database import Database
from app.jobs.models import CheckResult, Declaration, Policy, PolicyProfile


def config(url: str) -> Config:
    result = Config()
    result.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    result.set_main_option("sqlalchemy.url", url)
    return result


async def refused(database: Database, rows: list[object]) -> bool:
    async with database.session() as session:
        session.add_all(rows)
        try:
            await session.commit()
        except IntegrityError:
            return True
    return False


async def duplicates(url: str) -> tuple[bool, bool, bool]:
    database = Database(url)
    async with database.session() as session:
        session.add_all(
            [
                Policy(owner="u", package_sha="s", number="", insured=""),
                Declaration(file_name="a.xlsx", created_at=datetime(2026, 1, 1)),
            ]
        )
        await session.commit()
        session.add_all(
            [
                PolicyProfile(policy_id=1, version=1),
                CheckResult(
                    declaration_id=1, line="1", field="f", status="ok", reason="r", source="rule"
                ),
            ]
        )
        await session.commit()
    found = (
        await refused(database, [Policy(owner="u", package_sha="s", number="", insured="")]),
        await refused(database, [PolicyProfile(policy_id=1, version=1)]),
        await refused(
            database,
            [
                CheckResult(
                    declaration_id=1, line="1", field="f", status="no", reason="r", source="rule"
                )
            ],
        ),
    )
    await database.close()
    return found


def test_refuses_duplicate_policy_profile_and_check_place_on_sqlite(tmp_path: Path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'i.db'}"
    command.upgrade(config(url), "head")
    assert_that(
        asyncio.run(asyncio.wait_for(duplicates(url), 30)),
        equal_to((True, True, True)),
        "Migrated database accepts a duplicate policy, profile version or check place",
    )


def test_removes_unique_profile_version_on_downgrade_and_restores_it_on_upgrade(
    tmp_path: Path,
) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'u.db'}"
    command.upgrade(config(url), "head")
    command.downgrade(config(url), "0008")
    with sqlite3.connect(tmp_path / "u.db") as connection:
        downgraded = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'policy_profiles'"
        ).fetchone()[0]
    command.upgrade(config(url), "head")
    with sqlite3.connect(tmp_path / "u.db") as connection:
        upgraded = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'policy_profiles'"
        ).fetchone()[0]
    assert_that(
        ("uq_profile_version" in downgraded, "uq_profile_version" in upgraded),
        equal_to((False, True)),
        "Migration 0009 does not add the unique profile version and remove it on downgrade",
    )


async def administer(statement: str) -> None:
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"], isolation_level="AUTOCOMMIT")
    async with engine.connect() as connection:
        await connection.exec_driver_sql(statement)
    await engine.dispose()


async def constraints(url: str) -> set[str]:
    engine = create_async_engine(url)
    async with engine.connect() as connection:
        result = await connection.exec_driver_sql(
            "SELECT conname FROM pg_constraint WHERE contype = 'u'"
        )
        found = {row[0] for row in result}
    await engine.dispose()
    return found


@pytest.mark.postgres
@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is unset")
def test_refuses_duplicates_and_migrates_down_and_up_on_postgres() -> None:
    name = f"t34_{uuid.uuid4().hex}"
    asyncio.run(administer(f"CREATE DATABASE {name}"))
    url = make_url(os.environ["TEST_DATABASE_URL"]).set(database=name).render_as_string(False)
    try:
        command.upgrade(config(url), "head")
        refusals = asyncio.run(asyncio.wait_for(duplicates(url), 60))
        command.downgrade(config(url), "0008")
        downgraded = asyncio.run(asyncio.wait_for(constraints(url), 30))
        command.upgrade(config(url), "head")
        upgraded = asyncio.run(asyncio.wait_for(constraints(url), 30))
        assert_that(
            (refusals, "uq_profile_version" in downgraded, "uq_profile_version" in upgraded),
            equal_to(((True, True, True), False, True)),
            "Postgres does not refuse duplicates or migration 0009 does not go down and up",
        )
    finally:
        asyncio.run(administer(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
