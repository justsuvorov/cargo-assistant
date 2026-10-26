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
