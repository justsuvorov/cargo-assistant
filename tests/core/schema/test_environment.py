import random
from pathlib import Path

from hamcrest import assert_that, equal_to, raises
from pydantic import ValidationError

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


def test_chooses_vsk_gateway_by_default(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("", encoding="utf-8")
    assert_that(
        Environment(str(tmp_path / ".env")).llm_provider,
        equal_to("vsk"),
        "VSK gateway is not the default provider",
    )


def test_keeps_external_providers_forbidden_by_default(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("", encoding="utf-8")
    assert_that(
        Environment(str(tmp_path / ".env")).llm_allow_external,
        equal_to(False),
        "External providers are not forbidden by default",
    )


def test_keeps_certificate_check_on_by_default(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("", encoding="utf-8")
    assert_that(
        Environment(str(tmp_path / ".env")).llm_verify_tls,
        equal_to(True),
        "Certificate check of the model is not on by default",
    )


def test_hides_external_provider_keys_when_printed(tmp_path: Path) -> None:
    anthropic, gemini = (f"key-{random.randint(10**8, 10**9)}" for _ in range(2))
    (tmp_path / ".env").write_text(
        f"ANTHROPIC_API_KEY={anthropic}\nGEMINI_API_KEY={gemini}\n", encoding="utf-8"
    )
    printed = repr(Environment(str(tmp_path / ".env")))
    assert_that(
        anthropic in printed or gemini in printed,
        equal_to(False),
        "External provider keys are not hidden when settings are printed",
    )


def test_refuses_zero_concurrency_of_model(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("LLM_MAX_CONCURRENCY=0\n", encoding="utf-8")
    assert_that(
        lambda: Environment(str(tmp_path / ".env")),
        raises(ValidationError),
        "Zero concurrency that would block every call is not refused",
    )


def test_reads_total_time_limit_of_model(tmp_path: Path) -> None:
    limit = random.uniform(10, 900)
    (tmp_path / ".env").write_text(f"LLM_TOTAL_TIMEOUT={limit}\n", encoding="utf-8")
    assert_that(
        Environment(str(tmp_path / ".env")).llm_total_timeout,
        equal_to(limit),
        "Total time limit of the model is not read from the environment",
    )


def test_keeps_login_enabled_by_default(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("", encoding="utf-8")
    assert_that(
        Environment(str(tmp_path / ".env")).auth_disabled,
        equal_to(False),
        "Login is not enabled by default",
    )


def test_reads_switch_that_disables_login(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("AUTH_DISABLED=true\n", encoding="utf-8")
    assert_that(
        Environment(str(tmp_path / ".env")).auth_disabled,
        equal_to(True),
        "Switch that disables login is not read from the environment",
    )
