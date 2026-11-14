import random
from pathlib import Path

from hamcrest import assert_that, equal_to

from app.core.schema.environment import Environment
from app.core.settings import EnvSettings


def test_builds_issuer_from_keycloak_address_and_realm(tmp_path: Path) -> None:
    realm = f"realm{random.randint(1, 999)}"
    (tmp_path / ".env").write_text(
        f"KEYCLOAK_URL=http://kc.local\nKEYCLOAK_REALM={realm}\n", encoding="utf-8"
    )
    assert_that(
        EnvSettings(Environment(str(tmp_path / ".env"))).issuer(),
        equal_to(f"http://kc.local/realms/{realm}"),
        "Issuer is not built from address and realm",
    )


def test_maps_logical_role_to_configured_name(tmp_path: Path) -> None:
    name = f"role{random.randint(1, 999)}"
    (tmp_path / ".env").write_text(f"KEYCLOAK_ROLE_EXPERT={name}\n", encoding="utf-8")
    assert_that(
        EnvSettings(Environment(str(tmp_path / ".env"))).role("expert"),
        equal_to(name),
        "Expert role is not taken from settings",
    )


def test_exposes_storage_directory_as_path(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(f"STORAGE_DIR={tmp_path / 'files'}\n", encoding="utf-8")
    assert_that(
        EnvSettings(Environment(str(tmp_path / ".env"))).storage(),
        equal_to(tmp_path / "files"),
        "Storage directory is not exposed as a path",
    )


def test_gives_journal_defaults_of_thirty_seconds_a_day_and_three_months(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("", encoding="utf-8")
    settings = EnvSettings(Environment(str(tmp_path / ".env")))
    assert_that(
        (settings.beat(), settings.purge(), settings.months()),
        equal_to((30.0, 86400.0, 3)),
        "Journal intervals and storage period do not have the agreed defaults",
    )


def test_keeps_libreoffice_folder_inside_storage_by_default(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(f"STORAGE_DIR={tmp_path / 'files'}\n", encoding="utf-8")
    assert_that(
        EnvSettings(Environment(str(tmp_path / ".env"))).soffice(),
        equal_to(tmp_path / "files" / "soffice"),
        "LibreOffice folder is not inside the storage by default",
    )


def test_takes_libreoffice_folder_and_cache_days_from_environment(tmp_path: Path) -> None:
    days = random.randint(2, 30)
    (tmp_path / ".env").write_text(
        f"SOFFICE_DIR={tmp_path / 'lo'}\nSOFFICE_CACHE_DAYS={days}\n", encoding="utf-8"
    )
    settings = EnvSettings(Environment(str(tmp_path / ".env")))
    assert_that(
        (settings.soffice(), settings.cache_days()),
        equal_to((tmp_path / "lo", days)),
        "LibreOffice folder and cache days are not taken from the environment",
    )


def test_keeps_converted_files_for_seven_days_by_default(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("", encoding="utf-8")
    assert_that(
        EnvSettings(Environment(str(tmp_path / ".env"))).cache_days(),
        equal_to(7),
        "Converted files are not kept for seven days by default",
    )


def test_names_the_model_of_the_chosen_provider(tmp_path: Path) -> None:
    name = f"model{random.randint(1, 999)}"
    (tmp_path / ".env").write_text(
        f"LLM_PROVIDER=anthropic\nANTHROPIC_MODEL={name}\nLLM_MODEL=other\n", encoding="utf-8"
    )
    assert_that(
        EnvSettings(Environment(str(tmp_path / ".env"))).model(),
        equal_to(name),
        "Model is not taken from the settings of the chosen provider",
    )


def test_keeps_login_required_when_nothing_is_set(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("", encoding="utf-8")
    assert_that(
        EnvSettings(Environment(str(tmp_path / ".env"))).development(),
        equal_to(False),
        "Login is not required by default",
    )


def test_disables_login_by_new_switch(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("AUTH_DISABLED=true\n", encoding="utf-8")
    assert_that(
        EnvSettings(Environment(str(tmp_path / ".env"))).development(),
        equal_to(True),
        "Login is not disabled by the new switch",
    )


def test_disables_login_by_old_switch_as_synonym(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("AUTH_DEV_MODE=true\n", encoding="utf-8")
    assert_that(
        EnvSettings(Environment(str(tmp_path / ".env"))).development(),
        equal_to(True),
        "Login is not disabled by the old switch kept as a synonym",
    )


def test_names_local_user_dev_user_by_default(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("", encoding="utf-8")
    assert_that(
        EnvSettings(Environment(str(tmp_path / ".env"))).user(),
        equal_to("dev-user"),
        "Local user is not dev-user by default",
    )


def test_takes_local_user_from_environment(tmp_path: Path) -> None:
    name = f"u{random.randint(1, 999)}"
    (tmp_path / ".env").write_text(f"AUTH_DEV_USER_ID={name}\n", encoding="utf-8")
    assert_that(
        EnvSettings(Environment(str(tmp_path / ".env"))).user(),
        equal_to(name),
        "Local user is not taken from the environment",
    )


def test_limits_folder_to_two_hundred_megabytes_by_default(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("", encoding="utf-8")
    config = EnvSettings(Environment(str(tmp_path / ".env")))
    assert_that(
        (config.folder_limit(), config.conditions_limit()),
        equal_to((200 * 1024 * 1024, 20 * 1024 * 1024)),
        "Default limits of the folder and of the conditions file are not 200 and 20 megabytes",
    )


def test_takes_upload_limits_from_environment(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("FOLDER_MAX_MB=1\nCONDITIONS_MAX_MB=0.5\n", encoding="utf-8")
    config = EnvSettings(Environment(str(tmp_path / ".env")))
    assert_that(
        (config.folder_limit(), config.conditions_limit()),
        equal_to((1048576, 524288)),
        "Upload limits are not taken from settings",
    )
