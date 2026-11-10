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
