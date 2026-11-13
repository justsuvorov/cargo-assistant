import asyncio
import os
import sqlite3
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from hamcrest import assert_that, equal_to
from sqlalchemy import inspect, make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.jobs.models import Base


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
