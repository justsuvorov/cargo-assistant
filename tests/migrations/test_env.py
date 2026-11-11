import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from hamcrest import assert_that, equal_to

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
