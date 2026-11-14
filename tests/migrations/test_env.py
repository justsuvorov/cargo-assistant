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
from sqlalchemy import inspect, make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.jobs.database import Database
from app.jobs.models import Base, CheckResult, Declaration, Policy, PolicyProfile


def upgraded(folder: Path) -> Path:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{folder / 'm.db'}")
    command.upgrade(config, "head")
    return folder / "m.db"


def test_creates_every_table_of_the_model(tmp_path: Path) -> None:
    with sqlite3.connect(upgraded(tmp_path)) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert_that(
        tables - {"alembic_version"},
        equal_to(set(Base.metadata.tables)),
        "Migration does not create exactly the tables of the model",
    )


def test_creates_every_column_of_the_model(tmp_path: Path) -> None:
    with sqlite3.connect(upgraded(tmp_path)) as connection:
        columns = {
            (table, row[1])
            for table in Base.metadata.tables
            for row in connection.execute(f"PRAGMA table_info({table})")
        }
    assert_that(
        columns,
        equal_to(
            {
                (table.name, column.name)
                for table in Base.metadata.sorted_tables
                for column in table.columns
            }
        ),
        "Migration columns do not match the columns of the model",
    )


def test_downgrades_back_to_empty_database(tmp_path: Path) -> None:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{tmp_path / 'd.db'}")
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    with sqlite3.connect(tmp_path / "d.db") as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert_that(
        tables - {"alembic_version"},
        equal_to(set()),
        "Downgrade does not remove every table",
    )


def test_generates_sql_for_postgres_without_connection(tmp_path: Path) -> None:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    config.set_main_option("sqlalchemy.url", "postgresql+asyncpg://u:p@h/db")
    out = tmp_path / "up.sql"
    config.output_buffer = out.open("w", encoding="utf-8")
    command.upgrade(config, "head", sql=True)
    config.output_buffer.close()
    assert_that(
        "ALTER TABLE llm_calls ADD COLUMN provider" in out.read_text(encoding="utf-8"),
        equal_to(True),
        "Offline migration does not add the provider column for Postgres",
    )


def test_adds_binding_to_declarations_and_removes_it_on_downgrade(tmp_path: Path) -> None:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{tmp_path / 'b.db'}")
    command.upgrade(config, "head")
    with sqlite3.connect(tmp_path / "b.db") as connection:
        upgraded_columns = {row[1] for row in connection.execute("PRAGMA table_info(declarations)")}
    command.downgrade(config, "0004")
    with sqlite3.connect(tmp_path / "b.db") as connection:
        downgraded_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(declarations)")
        }
    assert_that(
        ("binding" in upgraded_columns, "binding" in downgraded_columns),
        equal_to((True, False)),
        "Migration does not add the binding column and remove it on downgrade",
    )


def test_generates_sql_with_binding_of_declaration_for_postgres(tmp_path: Path) -> None:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    config.set_main_option("sqlalchemy.url", "postgresql+asyncpg://u:p@h/db")
    out = tmp_path / "up.sql"
    config.output_buffer = out.open("w", encoding="utf-8")
    command.upgrade(config, "head", sql=True)
    config.output_buffer.close()
    assert_that(
        "ALTER TABLE declarations ADD COLUMN binding" in out.read_text(encoding="utf-8"),
        equal_to(True),
        "Offline migration does not add the binding column of declarations for Postgres",
    )


def test_generates_sql_with_build_job_of_policy_for_postgres(tmp_path: Path) -> None:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    config.set_main_option("sqlalchemy.url", "postgresql+asyncpg://u:p@h/db")
    out = tmp_path / "up.sql"
    config.output_buffer = out.open("w", encoding="utf-8")
    command.upgrade(config, "head", sql=True)
    config.output_buffer.close()
    assert_that(
        "ALTER TABLE policies ADD COLUMN job_id" in out.read_text(encoding="utf-8"),
        equal_to(True),
        "Offline migration does not add the build job to policies for Postgres",
    )


def sqlite_tables(path: Path) -> set[str]:
    with sqlite3.connect(path) as connection:
        return {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }


def test_adds_versions_and_corrections_and_takes_them_away_on_downgrade(tmp_path: Path) -> None:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{tmp_path / 'v.db'}")
    command.upgrade(config, "head")
    up = sqlite_tables(tmp_path / "v.db")
    command.downgrade(config, "0005")
    down = sqlite_tables(tmp_path / "v.db")
    command.upgrade(config, "head")
    again = sqlite_tables(tmp_path / "v.db")
    assert_that(
        ("corrections" in up, "corrections" in down, again == up),
        equal_to((True, False, True)),
        "Migration does not go up, down and up again with the corrections table",
    )


async def round_trip(url: str) -> tuple[bool, bool]:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    await asyncio.to_thread(command.upgrade, config, "head")
    await asyncio.to_thread(command.downgrade, config, "0005")
    engine = create_async_engine(url)
    async with engine.connect() as connection:
        down = await connection.run_sync(lambda sync: inspect(sync).has_table("corrections"))
    await engine.dispose()
    await asyncio.to_thread(command.upgrade, config, "head")
    engine = create_async_engine(url)
    async with engine.connect() as connection:
        up = await connection.run_sync(lambda sync: inspect(sync).has_table("corrections"))
    await engine.dispose()
    return down, up


async def administer(statement: str) -> None:
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"], isolation_level="AUTOCOMMIT")
    async with engine.connect() as connection:
        await connection.exec_driver_sql(statement)
    await engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is unset")
def test_goes_up_down_and_up_again_on_postgres() -> None:
    name = f"t29_{uuid.uuid4().hex}"
    base = os.environ["TEST_DATABASE_URL"]
    asyncio.run(administer(f"CREATE DATABASE {name}"))
    url = make_url(base).set(database=name).render_as_string(False)
    try:
        found = asyncio.run(asyncio.wait_for(round_trip(url), 120))
    finally:
        asyncio.run(administer(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
    assert_that(
        found,
        equal_to((False, True)),
        "Migration does not go down and up again on Postgres",
    )


def configured(url: str) -> Config:
    found = Config()
    found.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    found.set_main_option("sqlalchemy.url", url)
    return found


def test_keeps_old_policies_apart_without_an_owner_after_upgrade(tmp_path: Path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'm.db'}"
    command.upgrade(configured(url), "0006")
    with sqlite3.connect(tmp_path / "m.db") as connection:
        connection.executemany(
            "INSERT INTO policies (number, insured, access_group) VALUES ('', '', ?)",
            [("g",), ("g",)],
        )
    command.upgrade(configured(url), "head")
    with sqlite3.connect(tmp_path / "m.db") as connection:
        rows = connection.execute("SELECT owner, package_sha FROM policies ORDER BY id").fetchall()
    assert_that(
        rows,
        equal_to([("", "legacy-1"), ("", "legacy-2")]),
        "Old policies are not kept apart without an owner",
    )


def test_downgrades_to_the_group_of_access_with_an_empty_value(tmp_path: Path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'm.db'}"
    command.upgrade(configured(url), "head")
    command.downgrade(configured(url), "0006")
    with sqlite3.connect(tmp_path / "m.db") as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(declarations)")}
    assert_that(
        "access_group" in columns and "owner" not in columns,
        equal_to(True),
        "Downgrade does not bring the group of access back",
    )


async def administer_at(url: str, statements: tuple[str, ...], *, auto: bool) -> list[object]:
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT" if auto else "READ COMMITTED")
    found: list[object] = []
    async with engine.connect() as connection:
        for statement in statements:
            result = await connection.exec_driver_sql(statement)
            found = [row[0] for row in result] if result.returns_rows else []
        await connection.commit()
    await engine.dispose()
    return found


@pytest.mark.postgres
@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is unset")
def test_upgrades_a_database_with_policies_on_postgres() -> None:
    base = os.environ["TEST_DATABASE_URL"]
    name = f"t36_{uuid.uuid4().hex}"
    asyncio.run(asyncio.wait_for(administer_at(base, (f"CREATE DATABASE {name}",), auto=True), 30))
    url = make_url(base).set(database=name).render_as_string(False)
    try:
        command.upgrade(configured(url), "0006")
        asyncio.run(
            asyncio.wait_for(
                administer_at(
                    url,
                    (
                        "INSERT INTO policies (number, insured, access_group)"
                        " VALUES ('', '', 'g'), ('', '', 'g')",
                    ),
                    auto=False,
                ),
                30,
            )
        )
        command.upgrade(configured(url), "head")
        found = asyncio.run(
            asyncio.wait_for(
                administer_at(url, ("SELECT package_sha FROM policies ORDER BY id",), auto=False),
                30,
            )
        )
        command.downgrade(configured(url), "base")
    finally:
        asyncio.run(
            asyncio.wait_for(
                administer_at(base, (f"DROP DATABASE IF EXISTS {name} WITH (FORCE)",), auto=True),
                30,
            )
        )
    assert_that(
        found,
        equal_to(["legacy-1", "legacy-2"]),
        "Upgrade on Postgres does not keep old policies apart",
    )


def scripted(url: str) -> Config:
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
    command.upgrade(scripted(url), "head")
    assert_that(
        asyncio.run(asyncio.wait_for(duplicates(url), 30)),
        equal_to((True, True, True)),
        "Migrated database does not refuse a duplicate policy, profile version or check place",
    )


def test_removes_unique_profile_version_on_downgrade_and_restores_it_on_upgrade(
    tmp_path: Path,
) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'u.db'}"
    command.upgrade(scripted(url), "head")
    command.downgrade(scripted(url), "0008")
    with sqlite3.connect(tmp_path / "u.db") as connection:
        downgraded = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'policy_profiles'"
        ).fetchone()[0]
    command.upgrade(scripted(url), "head")
    with sqlite3.connect(tmp_path / "u.db") as connection:
        upgraded = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'policy_profiles'"
        ).fetchone()[0]
    assert_that(
        ("uq_profile_version" in downgraded, "uq_profile_version" in upgraded),
        equal_to((False, True)),
        "Migration 0009 does not add the unique profile version and remove it on downgrade",
    )


async def administered(statement: str) -> None:
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
    asyncio.run(administered(f"CREATE DATABASE {name}"))
    url = make_url(os.environ["TEST_DATABASE_URL"]).set(database=name).render_as_string(False)
    try:
        command.upgrade(scripted(url), "head")
        refusals = asyncio.run(asyncio.wait_for(duplicates(url), 60))
        command.downgrade(scripted(url), "0008")
        downgraded = asyncio.run(asyncio.wait_for(constraints(url), 30))
        command.upgrade(scripted(url), "head")
        upgraded = asyncio.run(asyncio.wait_for(constraints(url), 30))
    finally:
        asyncio.run(administered(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
    assert_that(
        (refusals, "uq_profile_version" in downgraded, "uq_profile_version" in upgraded),
        equal_to(((True, True, True), False, True)),
        "Postgres does not refuse duplicates or migration 0009 does not go down and up",
    )
