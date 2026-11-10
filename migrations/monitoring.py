from typing import Final, Protocol, final

_NOW = "timezone('utc', now())"
_SILENCE = 180
_STALL = 900
_STREAK = 3
_SHARE_MIN = 5
_HOUR = "interval '1 hour'"


class Catalog(Protocol):
    """Views of the monitoring schema in the order they depend on each other."""

    def names(self) -> tuple[str, ...]: ...

    def creating(self) -> tuple[str, ...]: ...

    def dropping(self) -> tuple[str, ...]: ...


def _usage(unit: str, column: str) -> str:
    return f"""
WITH uploads AS (
    SELECT date_trunc('{unit}', created_at)::date AS period,
           count(DISTINCT uploaded_by) FILTER (WHERE uploaded_by <> '') AS users,
           count(*) AS uploads
    FROM jobs WHERE kind = 'reconcile' GROUP BY 1
), filed AS (
    SELECT date_trunc('{unit}', created_at)::date AS period,
           count(*) AS declarations, coalesce(sum(shipments), 0) AS shipments
    FROM declarations GROUP BY 1
)
SELECT coalesce(u.period, f.period) AS {column},
       coalesce(u.users, 0) AS users, coalesce(u.uploads, 0) AS uploads,
       coalesce(f.declarations, 0) AS declarations, coalesce(f.shipments, 0)::bigint AS shipments
FROM uploads u FULL JOIN filed f ON f.period = u.period
"""


_VIEWS: Final = (
    (
        "v_runs",
        """
SELECT r.id AS run_id, r.job_id, j.kind, r.attempt, r.worker_id, r.queued_at, r.started_at,
       r.finished_at, r.outcome, r.error_class,
       extract(epoch FROM (r.finished_at - r.started_at))::double precision AS seconds,
       extract(epoch FROM (r.started_at - r.queued_at))::double precision AS wait_seconds,
       r.timings, r.code_version, r.cards_version, r.profile_version, r.prompts_version, r.model
FROM job_runs r JOIN jobs j ON j.id = r.job_id
""",
    ),
    (
        "v_session_outcomes",
        """
SELECT j.id AS job_id, (j.payload->>'declaration_id')::int AS declaration_id, j.uploaded_by,
       j.access_group, j.status, j.outcome, j.attempts, j.created_at, j.finished_at,
       extract(epoch FROM (j.finished_at - j.created_at))::double precision AS seconds,
       l.error_class, l.code_version, l.cards_version, l.profile_version, l.prompts_version,
       l.model
FROM jobs j
LEFT JOIN LATERAL (
    SELECT * FROM job_runs r WHERE r.job_id = j.id ORDER BY r.id DESC LIMIT 1
) l ON true
WHERE j.kind = 'reconcile'
""",
    ),
    (
        "v_worker_status",
        f"""
SELECT w.id AS worker_id, w.host, w.pid, w.version, w.started_at, w.last_seen, w.running,
       w.stopped_at,
       extract(epoch FROM ({_NOW} - w.last_seen))::double precision AS silent_seconds,
       CASE WHEN w.stopped_at IS NULL
                 AND {_NOW} - w.last_seen <= interval '{_SILENCE} seconds'
            THEN 1 ELSE 0 END AS alive
FROM worker_heartbeats w
""",
    ),
    (
        "v_queue_status",
        f"""
SELECT kind,
       count(*) FILTER (WHERE status = 'queued') AS queued,
       count(*) FILTER (WHERE status = 'running') AS running,
       count(*) FILTER (WHERE status = 'waiting') AS waiting,
       coalesce(max(extract(epoch FROM ({_NOW} - coalesce(queued_at, updated_at))))
                FILTER (WHERE status = 'queued'), 0)::double precision AS oldest_queued_seconds
FROM jobs WHERE status IN ('queued', 'running', 'waiting') GROUP BY kind
""",
    ),
    (
        "v_queue_wait_daily",
        """
SELECT started_at::date AS day, kind, count(*) AS runs,
       avg(wait_seconds) AS avg_seconds,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY wait_seconds) AS p50_seconds,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY wait_seconds) AS p95_seconds
FROM monitoring.v_runs WHERE wait_seconds IS NOT NULL GROUP BY 1, 2
""",
    ),
    (
        "v_stuck_sessions",
        f"""
SELECT j.id AS job_id, j.kind, (j.payload->>'declaration_id')::int AS declaration_id,
       r.id AS run_id, r.worker_id, r.started_at, w.last_seen,
       extract(epoch FROM ({_NOW} - coalesce(w.last_seen, j.locked_at)))::double precision
           AS silent_seconds
FROM jobs j
LEFT JOIN job_runs r ON r.job_id = j.id AND r.finished_at IS NULL
LEFT JOIN worker_heartbeats w ON w.id = r.worker_id
WHERE j.status = 'running'
  AND coalesce(w.last_seen, j.locked_at) < {_NOW} - interval '{_SILENCE} seconds'
""",
    ),
    (
        "v_outcomes_daily",
        """
SELECT finished_at::date AS day, count(*) AS sessions,
       count(*) FILTER (WHERE outcome = 'success') AS success,
       count(*) FILTER (WHERE outcome = 'error') AS failed,
       (count(*) FILTER (WHERE outcome = 'success'))::double precision / count(*)
           AS success_share,
       (count(*) FILTER (WHERE outcome = 'error'))::double precision / count(*) AS failed_share
FROM jobs WHERE kind = 'reconcile' AND outcome IN ('success', 'error') GROUP BY 1
""",
    ),
    (
        "v_upload_races",
        """
SELECT j.id AS job_id, min(k.id) AS earlier_job_id, j.created_at
FROM jobs j
JOIN jobs k ON k.file_sha256 = j.file_sha256 AND k.kind = 'reconcile' AND k.id < j.id
           AND (k.finished_at IS NULL OR k.finished_at > j.created_at)
WHERE j.kind = 'reconcile' AND j.file_sha256 <> ''
GROUP BY j.id, j.created_at
""",
    ),
    (
        "v_errors_daily",
        """
SELECT finished_at::date AS day, 'error'::text AS category, error_class, count(*) AS runs
FROM job_runs WHERE outcome IN ('error', 'timeout') GROUP BY 1, 3
UNION ALL
SELECT created_at::date, 'race'::text, ''::text, count(*) FROM monitoring.v_upload_races GROUP BY 1
""",
    ),
    (
        "v_failure_streak",
        """
WITH ordered AS (
    SELECT outcome, row_number() OVER (ORDER BY finished_at DESC, id DESC) AS place
    FROM job_runs WHERE finished_at IS NOT NULL AND outcome <> 'waiting'
)
SELECT coalesce((SELECT min(place) - 1 FROM ordered WHERE outcome = 'success'),
                (SELECT count(*) FROM ordered))::bigint AS streak
""",
    ),
    (
        "v_duration_daily",
        """
WITH parts AS (
    SELECT finished_at::date AS day, kind, 'total'::text AS stage, seconds
    FROM monitoring.v_runs WHERE outcome = 'success'
    UNION ALL
    SELECT r.finished_at::date, r.kind, t.key, t.value::double precision
    FROM monitoring.v_runs r CROSS JOIN LATERAL json_each_text(r.timings) t
    WHERE r.outcome = 'success'
)
SELECT day, kind, stage, count(*) AS runs, avg(seconds) AS avg_seconds,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY seconds) AS p50_seconds,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY seconds) AS p95_seconds,
       max(seconds) AS max_seconds
FROM parts GROUP BY 1, 2, 3
""",
    ),
    (
        "v_versions",
        """
SELECT started_at::date AS day, kind, code_version, cards_version, profile_version,
       prompts_version, model, count(*) AS runs,
       count(*) FILTER (WHERE outcome = 'success') AS success,
       count(*) FILTER (WHERE outcome IN ('error', 'timeout')) AS failed,
       avg(seconds) FILTER (WHERE outcome = 'success') AS avg_seconds,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY seconds)
           FILTER (WHERE outcome = 'success') AS p95_seconds
FROM monitoring.v_runs WHERE outcome <> 'running' GROUP BY 1, 2, 3, 4, 5, 6, 7
""",
    ),
    ("v_usage_daily", _usage("day", "day")),
    ("v_usage_weekly", _usage("week", "week")),
    (
        "v_alerts",
        f"""
SELECT 'worker_down'::text AS alert, (s.value > {_SILENCE})::int AS firing, s.value,
       {_SILENCE}::double precision AS threshold,
       'Секунд с последнего сигнала живого воркера, 86400 если живых воркеров нет'::text AS note
FROM (
    SELECT coalesce(extract(epoch FROM ({_NOW} - max(last_seen))), 86400)::double precision
           AS value
    FROM worker_heartbeats WHERE stopped_at IS NULL
) s
UNION ALL
SELECT 'queue_stalled', (s.value > {_STALL})::int, s.value, {_STALL}::double precision,
       'Секунд, сколько самая старая задача ждёт в очереди'
FROM (
    SELECT coalesce(max(extract(epoch FROM ({_NOW} - coalesce(queued_at, updated_at)))),
                    0)::double precision AS value
    FROM jobs WHERE status = 'queued'
) s
UNION ALL
SELECT 'stuck_sessions', (s.value > 0)::int, s.value, 0::double precision,
       'Задач в работе на воркере, который молчит больше {_SILENCE} секунд'
FROM (SELECT count(*)::double precision AS value FROM monitoring.v_stuck_sessions) s
UNION ALL
SELECT 'consecutive_failures', (s.value >= {_STREAK})::int, s.value,
       {_STREAK}::double precision,
       'Неуспешных попыток подряд, срабатывает при значении не меньше порога'
FROM (SELECT streak::double precision AS value FROM monitoring.v_failure_streak) s
UNION ALL
SELECT 'failure_share_1h',
       (s.total >= {_SHARE_MIN} AND s.failed * 5 > s.total)::int,
       CASE WHEN s.total = 0 THEN 0 ELSE s.failed::double precision / s.total END,
       0.2::double precision,
       'Доля неуспешных сессий за час, срабатывает при сессиях не меньше {_SHARE_MIN}, сессий '
       || s.total || ', неуспешных ' || s.failed
FROM (
    SELECT count(*) FILTER (WHERE outcome IN ('success', 'error')) AS total,
           count(*) FILTER (WHERE outcome = 'error') AS failed
    FROM jobs WHERE kind = 'reconcile' AND finished_at >= {_NOW} - {_HOUR}
) s
UNION ALL
SELECT 'upload_race_1h', (s.value > 0)::int, s.value, 0::double precision,
       'Задач за час, запущенных по уже обрабатываемой декларации'
FROM (
    SELECT count(*)::double precision AS value
    FROM monitoring.v_upload_races WHERE created_at >= {_NOW} - {_HOUR}
) s
""",
    ),
)


@final
class Views:
    """Statements that create and drop the views of the monitoring schema; they exist only in
    Postgres and read the journal tables, never texts of errors, names of files or field values."""

    __slots__ = ()

    def names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in _VIEWS)

    def creating(self) -> tuple[str, ...]:
        return (
            "CREATE SCHEMA IF NOT EXISTS monitoring",
            *(f"CREATE VIEW monitoring.{name} AS {body}" for name, body in _VIEWS),
        )

    def dropping(self) -> tuple[str, ...]:
        return ("DROP SCHEMA IF EXISTS monitoring CASCADE",)
