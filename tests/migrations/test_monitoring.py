import asyncio
import os
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from hamcrest import assert_that, equal_to
from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.jobs.models import Base
from migrations.monitoring import Views

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is unset"
    ),
]


def ago(seconds: float) -> str:
    return f"timezone('utc', now()) - interval '{seconds} seconds'"


async def administer(statement: str) -> None:
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"], isolation_level="AUTOCOMMIT")
    async with engine.connect() as connection:
        await connection.exec_driver_sql(statement)
    await engine.dispose()


def migrate(url: str, target: str) -> None:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    if target == "base":
        command.downgrade(config, target)
    else:
        command.upgrade(config, target)


@contextmanager
def scratch() -> Iterator[str]:
    name = f"t22_{uuid.uuid4().hex}"
    asyncio.run(administer(f"CREATE DATABASE {name}"))
    url = make_url(os.environ["TEST_DATABASE_URL"]).set(database=name).render_as_string(False)
    try:
        migrate(url, "head")
        yield url
    finally:
        asyncio.run(administer(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))


async def query(url: str, statements: tuple[str, ...]) -> list[Mapping[str, object]]:
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        found: list[Mapping[str, object]] = []
        for statement in statements:
            result = await connection.exec_driver_sql(statement)
            found = [dict(row) for row in result.mappings()] if result.returns_rows else []
    await engine.dispose()
    return found


def sql(url: str, *statements: str) -> list[Mapping[str, object]]:
    return asyncio.run(asyncio.wait_for(query(url, statements), 30))


def job(number: int, **fields: str | int) -> str:
    v = {
        "kind": "reconcile",
        "status": "done",
        "outcome": "success",
        "created": 7200,
        "finished": "NULL",
        "queued": "NULL",
        "locked": "NULL",
        "sha": "",
        "user": "",
        "payload": "{}",
        "error": "",
        **fields,
    }
    return (
        "INSERT INTO jobs (id, kind, payload, status, stage, progress, attempts, locked_at, error,"
        " timings, created_at, updated_at, queued_at, uploaded_by, access_group, file_sha256,"
        f" outcome, finished_at) VALUES ({number}, '{v['kind']}', '{v['payload']}',"
        f" '{v['status']}', '', 0, 1, {v['locked']}, '{v['error']}', '{{}}',"
        f" {ago(float(v['created']))}, {ago(float(v['created']))}, {v['queued']}, '{v['user']}',"
        f" 'g', '{v['sha']}', '{v['outcome']}', {v['finished']})"
    )


def worker(key: str, *, seen: float = 0, stopped: str = "NULL", running: int = 0) -> str:
    return (
        "INSERT INTO worker_heartbeats (id, host, pid, version, started_at, last_seen, running,"
        f" stopped_at) VALUES ('{key}', 'host', 1, 'v1', {ago(9000)}, {ago(seen)}, {running},"
        f" {stopped})"
    )


def attempt(number: int, of: int, **fields: str | int) -> str:
    v = {
        "worker_key": "NULL",
        "queued": "NULL",
        "started": 100,
        "finished": "NULL",
        "outcome": "success",
        "error_class": "",
        "error_text": "",
        "timings": "{}",
        "code": "c1",
        "profile": 0,
        **fields,
    }
    return (
        "INSERT INTO job_runs (id, job_id, attempt, worker_id, queued_at, started_at, finished_at,"
        " outcome, error_class, error_text, timings, code_version, cards_version, profile_version,"
        f" prompts_version, model) VALUES ({number}, {of}, 1, {v['worker_key']}, {v['queued']},"
        f" {ago(float(v['started']))}, {v['finished']}, '{v['outcome']}', '{v['error_class']}',"
        f" '{v['error_text']}', '{v['timings']}', '{v['code']}', 'k1', {v['profile']}, 'p1', 'm1')"
    )


def alert(url: str, name: str) -> Mapping[str, object]:
    return sql(url, f"SELECT * FROM monitoring.v_alerts WHERE alert = '{name}'")[0]


def firing(url: str, name: str) -> int:
    return int(str(alert(url, name)["firing"]))


def test_creates_every_view_of_the_catalog() -> None:
    with scratch() as url:
        found = sql(
            url, "SELECT table_name FROM information_schema.views WHERE table_schema = 'monitoring'"
        )
    assert_that(
        {str(row["table_name"]) for row in found},
        equal_to(set(Views().names())),
        "Monitoring schema does not hold exactly the views of the catalog",
    )


def test_reads_every_view_of_the_empty_journal() -> None:
    with scratch() as url:
        sql(url, *(f"SELECT * FROM monitoring.{name}" for name in Views().names()))
        count = len(sql(url, "SELECT * FROM monitoring.v_alerts"))
    assert_that(count, equal_to(6), "Alerts view does not give one row for each of six alerts")


def test_migrates_down_and_up_again_on_postgres() -> None:
    with scratch() as url:
        migrate(url, "base")
        left = sql(
            url,
            "SELECT table_name FROM information_schema.tables"
            " WHERE table_schema IN ('public', 'monitoring') AND table_name <> 'alembic_version'",
        )
        migrate(url, "head")
        tables = sql(
            url,
            "SELECT table_name FROM information_schema.tables"
            " WHERE table_schema = 'public' AND table_name <> 'alembic_version'",
        )
    assert_that(
        (left, {str(row["table_name"]) for row in tables}),
        equal_to(([], set(Base.metadata.tables))),
        "Downgrade does not empty the database or upgrade does not restore the tables",
    )


def test_creates_every_column_of_the_model_on_postgres() -> None:
    with scratch() as url:
        found = sql(
            url,
            "SELECT table_name, column_name FROM information_schema.columns"
            " WHERE table_schema = 'public' AND table_name <> 'alembic_version'",
        )
    assert_that(
        {(str(row["table_name"]), str(row["column_name"])) for row in found},
        equal_to(
            {
                (table.name, column.name)
                for table in Base.metadata.sorted_tables
                for column in table.columns
            }
        ),
        "Postgres columns do not match the columns of the model",
    )


def test_lists_attempts_with_run_and_wait_seconds() -> None:
    with scratch() as url:
        sql(
            url,
            job(1, kind="reconcile"),
            attempt(1, 1, queued=ago(130), started=100, finished=ago(70), error_text="x"),
        )
        row = sql(url, "SELECT * FROM monitoring.v_runs")[0]
    assert_that(
        (round(float(str(row["seconds"]))), round(float(str(row["wait_seconds"]))), row["kind"]),
        equal_to((30, 30, "reconcile")),
        "Attempt view does not give run seconds, wait seconds and job kind",
    )


def test_lists_sessions_of_reconcile_jobs_only() -> None:
    with scratch() as url:
        sql(
            url,
            job(1, payload='{"declaration_id": 7}', user="u1", finished=ago(60)),
            job(2, kind="profile_build"),
            attempt(1, 1, error_class="", finished=ago(60), code="c9"),
        )
        rows = sql(url, "SELECT * FROM monitoring.v_session_outcomes")
    assert_that(
        [
            (
                row["job_id"],
                row["declaration_id"],
                row["uploaded_by"],
                row["outcome"],
                row["code_version"],
            )
            for row in rows
        ],
        equal_to([(1, 7, "u1", "success", "c9")]),
        "Session view does not list only reconcile jobs with the version of the last attempt",
    )


def test_marks_worker_alive_only_when_it_signals_in_time() -> None:
    with scratch() as url:
        sql(
            url,
            worker("a", seen=170),
            worker("b", seen=190),
            worker("c", seen=10, stopped=ago(5)),
        )
        rows = sql(
            url, "SELECT worker_id, alive FROM monitoring.v_worker_status ORDER BY worker_id"
        )
    assert_that(
        [(row["worker_id"], row["alive"]) for row in rows],
        equal_to([("a", 1), ("b", 0), ("c", 0)]),
        "Worker status does not mark silent and stopped workers as not alive",
    )


def test_counts_jobs_in_queue_and_in_work_by_kind() -> None:
    with scratch() as url:
        sql(
            url,
            job(1, status="queued", outcome="", queued=ago(60)),
            job(2, status="queued", outcome="", queued=ago(20)),
            job(3, status="running", outcome=""),
            job(4, status="waiting", outcome="", kind="profile_build"),
            job(5),
        )
        rows = sql(url, "SELECT * FROM monitoring.v_queue_status ORDER BY kind")
    assert_that(
        [
            (
                row["kind"],
                row["queued"],
                row["running"],
                row["waiting"],
                round(float(str(row["oldest_queued_seconds"]))),
            )
            for row in rows
        ],
        equal_to([("profile_build", 0, 0, 1, 0), ("reconcile", 2, 1, 0, 60)]),
        "Queue view does not count queued, running and waiting jobs by kind",
    )


def test_summarizes_wait_before_claim_by_day() -> None:
    with scratch() as url:
        sql(
            url,
            job(1),
            *(
                attempt(n, 1, queued=ago(100 + wait), started=100, finished=ago(10))
                for n, wait in ((1, 10), (2, 20), (3, 30))
            ),
        )
        row = sql(url, "SELECT * FROM monitoring.v_queue_wait_daily")[0]
    assert_that(
        (row["runs"], round(float(str(row["avg_seconds"]))), round(float(str(row["p50_seconds"])))),
        equal_to((3, 20, 20)),
        "Wait view does not give the count, average and median of waits",
    )


def test_lists_running_jobs_on_workers_that_went_silent() -> None:
    with scratch() as url:
        sql(
            url,
            worker("live", seen=100),
            worker("dead", seen=200),
            job(1, status="running", outcome="", locked=ago(900)),
            job(2, status="running", outcome="", locked=ago(900)),
            attempt(1, 1, worker_key="'live'", outcome="running"),
            attempt(2, 2, worker_key="'dead'", outcome="running"),
        )
        rows = sql(url, "SELECT job_id, worker_id FROM monitoring.v_stuck_sessions")
    assert_that(
        [(row["job_id"], row["worker_id"]) for row in rows],
        equal_to([(2, "dead")]),
        "Stuck view does not list exactly the job of the silent worker",
    )


def test_gives_shares_of_session_outcomes_by_day() -> None:
    with scratch() as url:
        sql(
            url,
            job(1, finished=ago(60)),
            job(2, finished=ago(60)),
            job(3, finished=ago(60)),
            job(4, outcome="error", status="failed", finished=ago(60)),
            job(5, status="running", outcome=""),
        )
        row = sql(url, "SELECT * FROM monitoring.v_outcomes_daily")[0]
    assert_that(
        (row["sessions"], row["success"], row["failed"], row["failed_share"]),
        equal_to((4, 3, 1, 0.25)),
        "Outcome view does not count finished sessions and their shares",
    )


def test_counts_errors_by_class_and_races_by_day() -> None:
    with scratch() as url:
        sql(
            url,
            job(1, sha="s", created=500, finished=ago(100)),
            job(2, sha="s", created=300, finished=ago(50)),
            attempt(1, 1, outcome="error", error_class="KeyError", finished=ago(90)),
            attempt(2, 1, outcome="error", error_class="KeyError", finished=ago(80)),
            attempt(3, 2, outcome="timeout", error_class="TimeoutError", finished=ago(70)),
        )
        rows = sql(
            url, "SELECT category, error_class, runs FROM monitoring.v_errors_daily ORDER BY 1, 2"
        )
    assert_that(
        [(row["category"], row["error_class"], row["runs"]) for row in rows],
        equal_to([("error", "KeyError", 2), ("error", "TimeoutError", 1), ("race", "", 1)]),
        "Error view does not count errors by class and races",
    )


def test_counts_failed_attempts_since_the_last_success() -> None:
    with scratch() as url:
        sql(
            url,
            job(1),
            attempt(1, 1, outcome="error", finished=ago(500)),
            attempt(2, 1, outcome="success", finished=ago(400)),
            attempt(3, 1, outcome="error", finished=ago(300)),
            attempt(4, 1, outcome="waiting", finished=ago(250)),
            attempt(5, 1, outcome="timeout", finished=ago(200)),
        )
        row = sql(url, "SELECT streak FROM monitoring.v_failure_streak")[0]
    assert_that(row["streak"], equal_to(2), "Streak view does not skip waiting and stop at success")


def test_gives_duration_of_sessions_and_stages_by_day() -> None:
    with scratch() as url:
        sql(
            url,
            job(1),
            attempt(1, 1, started=110, finished=ago(100), timings='{"ingest": 4.0}'),
            attempt(2, 1, started=130, finished=ago(100), timings='{"ingest": 8.0}'),
        )
        rows = sql(
            url, "SELECT stage, runs, max_seconds FROM monitoring.v_duration_daily ORDER BY stage"
        )
    assert_that(
        [(row["stage"], row["runs"], round(float(str(row["max_seconds"])))) for row in rows],
        equal_to([("ingest", 2, 8), ("total", 2, 30)]),
        "Duration view does not give total and stage durations",
    )


def test_splits_attempts_by_versions() -> None:
    with scratch() as url:
        sql(
            url,
            job(1),
            attempt(1, 1, code="a", finished=ago(50)),
            attempt(2, 1, code="a", outcome="error", finished=ago(50)),
            attempt(3, 1, code="b", profile=4, finished=ago(50)),
        )
        rows = sql(
            url,
            "SELECT code_version, profile_version, runs, success, failed"
            " FROM monitoring.v_versions ORDER BY 1",
        )
    assert_that(
        [tuple(row.values()) for row in rows],
        equal_to([("a", 0, 2, 1, 1), ("b", 4, 1, 1, 0)]),
        "Version view does not split attempts by code and profile versions",
    )


def test_counts_users_uploads_declarations_and_shipments_by_day_and_week() -> None:
    with scratch() as url:
        sql(
            url,
            job(1, user="u1"),
            job(2, user="u1"),
            job(3, user="u2"),
            "INSERT INTO declarations (owner, file_name, file_key, number, form, shipments,"
            f" month, result_key, created_at, places_expected, places_answered) VALUES ('g', 'n',"
            f" '', '', '', 5, '', '', {ago(7200)}, 0, 0)",
        )
        daily = sql(
            url, "SELECT users, uploads, declarations, shipments FROM monitoring.v_usage_daily"
        )
        weekly = sql(
            url, "SELECT users, uploads, declarations, shipments FROM monitoring.v_usage_weekly"
        )
    assert_that(
        ([tuple(r.values()) for r in daily], [tuple(r.values()) for r in weekly]),
        equal_to(([(2, 3, 1, 5)], [(2, 3, 1, 5)])),
        "Usage views do not count users, uploads, declarations and shipments",
    )


def test_gives_one_row_per_alert_with_threshold_and_note() -> None:
    with scratch() as url:
        rows = sql(url, "SELECT * FROM monitoring.v_alerts ORDER BY alert")
    assert_that(
        (list(rows[0].keys()), [row["alert"] for row in rows]),
        equal_to(
            (
                ["alert", "firing", "value", "threshold", "note"],
                [
                    "consecutive_failures",
                    "failure_share_1h",
                    "queue_stalled",
                    "stuck_sessions",
                    "upload_race_1h",
                    "worker_down",
                ],
            )
        ),
        "Alert view does not give a row per alert with the expected columns",
    )


def test_fires_worker_down_when_no_live_worker_signals_within_three_minutes() -> None:
    with scratch() as url:
        none = firing(url, "worker_down")
        sql(url, worker("a", seen=170))
        fresh = firing(url, "worker_down")
        sql(url, "UPDATE worker_heartbeats SET last_seen = " + ago(190))
        silent = firing(url, "worker_down")
        sql(url, "UPDATE worker_heartbeats SET last_seen = " + ago(10) + ", stopped_at = " + ago(5))
        stopped = firing(url, "worker_down")
    assert_that(
        (none, fresh, silent, stopped),
        equal_to((1, 0, 1, 1)),
        "Worker alert does not fire for no, silent and stopped workers only",
    )


def test_fires_queue_stalled_when_a_job_waits_over_fifteen_minutes() -> None:
    with scratch() as url:
        empty = firing(url, "queue_stalled")
        sql(url, job(1, status="queued", outcome="", queued=ago(890)))
        below = firing(url, "queue_stalled")
        sql(url, "UPDATE jobs SET queued_at = " + ago(910))
        above = firing(url, "queue_stalled")
    assert_that(
        (empty, below, above),
        equal_to((0, 0, 1)),
        "Queue alert does not fire only above fifteen minutes of waiting",
    )


def test_fires_stuck_sessions_when_a_running_job_has_a_silent_worker() -> None:
    with scratch() as url:
        sql(
            url,
            worker("w", seen=100),
            job(1, status="running", outcome="", locked=ago(900)),
            attempt(1, 1, worker_key="'w'", outcome="running"),
        )
        live = firing(url, "stuck_sessions")
        sql(url, "UPDATE worker_heartbeats SET last_seen = " + ago(200))
        silent = firing(url, "stuck_sessions")
    assert_that(
        (live, silent),
        equal_to((0, 1)),
        "Stuck alert does not fire only for a silent worker",
    )


def test_fires_consecutive_failures_at_three_unsuccessful_attempts_in_a_row() -> None:
    with scratch() as url:
        sql(
            url,
            job(1),
            attempt(1, 1, outcome="error", finished=ago(300)),
            attempt(2, 1, outcome="timeout", finished=ago(200)),
        )
        two = firing(url, "consecutive_failures")
        sql(url, attempt(3, 1, outcome="requeued", finished=ago(100)))
        three = firing(url, "consecutive_failures")
        sql(url, attempt(4, 1, outcome="success", finished=ago(50)))
        reset = firing(url, "consecutive_failures")
    assert_that(
        (two, three, reset),
        equal_to((0, 1, 0)),
        "Failure alert does not fire at exactly three failures in a row",
    )


def test_fires_failure_share_above_a_fifth_with_at_least_five_sessions() -> None:
    with scratch() as url:
        sql(url, *(job(n, outcome="error", status="failed", finished=ago(60)) for n in range(1, 5)))
        few = firing(url, "failure_share_1h")
        sql(url, job(5, finished=ago(60)))
        all_bad = firing(url, "failure_share_1h")
        sql(url, "DELETE FROM jobs")
        sql(url, job(1, outcome="error", status="failed", finished=ago(60)))
        sql(url, *(job(n, finished=ago(60)) for n in range(2, 6)))
        exact = firing(url, "failure_share_1h")
        sql(url, "UPDATE jobs SET outcome = 'error', status = 'failed' WHERE id = 2")
        over = firing(url, "failure_share_1h")
        sql(url, "UPDATE jobs SET finished_at = " + ago(4000))
        old = firing(url, "failure_share_1h")
    assert_that(
        (few, all_bad, exact, over, old),
        equal_to((0, 1, 0, 1, 0)),
        "Share alert does not fire only above a fifth with five sessions in the last hour",
    )


def test_fires_upload_race_when_a_job_starts_while_the_same_file_is_in_work() -> None:
    with scratch() as url:
        sql(url, job(1, sha="s", created=900, finished=ago(600)), job(2, sha="s", created=300))
        after = firing(url, "upload_race_1h")
        sql(url, "UPDATE jobs SET finished_at = NULL, status = 'running' WHERE id = 1")
        during = firing(url, "upload_race_1h")
        sql(url, "UPDATE jobs SET created_at = " + ago(4000) + " WHERE id = 2")
        old = firing(url, "upload_race_1h")
    assert_that(
        (after, during, old),
        equal_to((0, 1, 0)),
        "Race alert does not fire only for overlapping jobs of one file in the last hour",
    )


def test_exposes_no_error_text_file_name_or_field_value_in_any_view() -> None:
    marker = "Client-Marker-7731"
    with scratch() as url:
        sql(
            url,
            job(1, error=marker, payload='{"declaration_id": 1, "file_name": "' + marker + '"}'),
            attempt(
                1, 1, outcome="error", error_class="KeyError", error_text=marker, finished=ago(5)
            ),
            "INSERT INTO declarations (owner, file_name, file_key, number, form, shipments,"
            f" month, result_key, created_at, places_expected, places_answered) VALUES ('g',"
            f" '{marker}', '{marker}', '{marker}', '', 1, '', '', {ago(60)}, 0, 0)",
            "INSERT INTO check_results (declaration_id, line, field, status, reason, clause,"
            f" comment, source, correction) VALUES (1, '1', 'f', 'match', 'r', '', '{marker}',"
            f" 'rule', '{marker}')",
        )
        values = [
            str(value)
            for name in Views().names()
            for row in sql(url, f"SELECT * FROM monitoring.{name}")
            for value in row.values()
        ]
        columns = sql(
            url,
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'monitoring'",
        )
    assert_that(
        (
            [value for value in values if marker in value],
            {str(row["column_name"]) for row in columns}
            & {
                "error_text",
                "error",
                "file_name",
                "file_key",
                "payload",
                "comment",
                "correction",
                "body",
            },
        ),
        equal_to(([], set())),
        "Views do not hide an error text, a file name and a field value",
    )
