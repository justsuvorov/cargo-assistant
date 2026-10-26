import random
from pathlib import Path

from hamcrest import assert_that, equal_to

from app.core.schema.environment import Environment


def test_reads_worker_limit_from_environment_file(tmp_path: Path) -> None:
    limit = random.randint(50, 99)
    (tmp_path / ".env").write_text(f"WORKER_MAX_JOBS={limit}\n", encoding="utf-8")
    assert_that(
        Environment(str(tmp_path / ".env")).worker_max_jobs,
        equal_to(limit),
        "Worker limit is not read from the environment",
    )


def test_hides_gateway_key_when_printed(tmp_path: Path) -> None:
    secret = f"key-{random.randint(10**8, 10**9)}"
    (tmp_path / ".env").write_text(f"LLM_API_KEY={secret}\n", encoding="utf-8")
    assert_that(
        secret in repr(Environment(str(tmp_path / ".env"))),
        equal_to(False),
        "Gateway key is not hidden when settings are printed",
    )


def test_keeps_development_mode_off_by_default(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("", encoding="utf-8")
    assert_that(
        Environment(str(tmp_path / ".env")).auth_dev_mode,
        equal_to(False),
        "Development mode is not off by default",
    )
