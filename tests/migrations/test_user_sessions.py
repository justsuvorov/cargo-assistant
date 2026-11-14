import asyncio
import os
import sqlite3
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from hamcrest import assert_that, equal_to
from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import create_async_engine


def config(url: str) -> Config:
    found = Config()
    found.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    found.set_main_option("sqlalchemy.url", url)
    return found


def test_keeps_old_policies_apart_without_an_owner_after_upgrade(tmp_path: Path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'm.db'}"
    command.upgrade(config(url), "0006")
    with sqlite3.connect(tmp_path / "m.db") as connection:
        connection.executemany(
            "INSERT INTO policies (number, insured, access_group) VALUES ('', '', ?)",
            [("g",), ("g",)],
        )
    command.upgrade(config(url), "head")
    with sqlite3.connect(tmp_path / "m.db") as connection:
        rows = connection.execute("SELECT owner, package_sha FROM policies ORDER BY id").fetchall()
    assert_that(
        rows,
        equal_to([("", "legacy-1"), ("", "legacy-2")]),
        "Old policies are not kept apart without an owner",
    )


def test_downgrades_to_the_group_of_access_with_an_empty_value(tmp_path: Path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'm.db'}"
    command.upgrade(config(url), "head")
    command.downgrade(config(url), "0006")
    with sqlite3.connect(tmp_path / "m.db") as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(declarations)")}
    assert_that(
        "access_group" in columns and "owner" not in columns,
        equal_to(True),
        "Downgrade does not bring the group of access back",
    )


async def administer(url: str, statements: tuple[str, ...], *, auto: bool) -> list[object]:
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
    asyncio.run(asyncio.wait_for(administer(base, (f"CREATE DATABASE {name}",), auto=True), 30))
    url = make_url(base).set(database=name).render_as_string(False)
    try:
        command.upgrade(config(url), "0006")
        asyncio.run(
            asyncio.wait_for(
                administer(
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
        command.upgrade(config(url), "head")
        found = asyncio.run(
            asyncio.wait_for(
                administer(url, ("SELECT package_sha FROM policies ORDER BY id",), auto=False),
                30,
            )
        )
        command.downgrade(config(url), "base")
    finally:
        asyncio.run(
            asyncio.wait_for(
                administer(base, (f"DROP DATABASE IF EXISTS {name} WITH (FORCE)",), auto=True), 30
            )
        )
    assert_that(
        found,
        equal_to(["legacy-1", "legacy-2"]),
        "Upgrade on Postgres does not keep old policies apart",
    )
