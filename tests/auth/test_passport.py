import json
import random
import time
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from hamcrest import assert_that, equal_to, raises
from jwt import PyJWK
from jwt.algorithms import RSAAlgorithm

from app.auth.errors import DeniedError
from app.auth.passport import Keycloak, Open, StaticKeys
from app.core.schema.environment import Environment
from app.core.settings import EnvSettings


def settings(folder: Path, realm: str) -> EnvSettings:
    (folder / ".env").write_text(
        f"KEYCLOAK_URL=http://kc.local\nKEYCLOAK_REALM={realm}\nKEYCLOAK_CLIENT_ID=cargo\n",
        encoding="utf-8",
    )
    return EnvSettings(Environment(str(folder / ".env")))


def pair() -> tuple[rsa.RSAPrivateKey, StaticKeys]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(private.public_key()))
    return private, StaticKeys({"k1": PyJWK.from_dict({**jwk, "kid": "k1", "alg": "RS256"})})


def token(private: rsa.RSAPrivateKey, claims: dict[str, object]) -> str:
    return jwt.encode(
        {"exp": int(time.time()) + 60, "aud": "cargo", **claims},
        private,
        algorithm="RS256",
        headers={"kid": "k1"},
    )


def test_accepts_token_signed_by_known_key(tmp_path: Path) -> None:
    realm = f"r{random.randint(1, 999)}"
    private, keys = pair()
    identity = Keycloak(settings(tmp_path, realm), keys).identity(
        token(
            private,
            {
                "iss": f"http://kc.local/realms/{realm}",
                "preferred_username": "ivanov",
                "realm_access": {"roles": ["cargo_expert"]},
                "groups": ["/fsc"],
            },
        )
    )
    assert_that(
        (identity.name(), identity.allows("expert"), identity.sees("fsc")),
        equal_to(("ivanov", True, True)),
        "Verified token does not give the name, roles and groups",
    )


def test_lets_expert_do_what_user_does(tmp_path: Path) -> None:
    realm = f"r{random.randint(1, 999)}"
    private, keys = pair()
    identity = Keycloak(settings(tmp_path, realm), keys).identity(
        token(
            private,
            {"iss": f"http://kc.local/realms/{realm}", "realm_access": {"roles": ["cargo_expert"]}},
        )
    )
    assert_that(
        identity.allows("user"),
        equal_to(True),
        "Expert is not allowed what a user is allowed",
    )


def test_hides_other_groups_from_person(tmp_path: Path) -> None:
    realm = f"r{random.randint(1, 999)}"
    private, keys = pair()
    identity = Keycloak(settings(tmp_path, realm), keys).identity(
        token(private, {"iss": f"http://kc.local/realms/{realm}", "groups": ["/fsc"]})
    )
    assert_that(
        identity.sees("other"),
        equal_to(False),
        "Person sees a group that they do not belong to",
    )


def test_rejects_token_signed_by_unknown_key(tmp_path: Path) -> None:
    realm = f"r{random.randint(1, 999)}"
    _, keys = pair()
    stranger, _ = pair()
    assert_that(
        lambda: Keycloak(settings(tmp_path, realm), keys).identity(
            token(stranger, {"iss": f"http://kc.local/realms/{realm}"})
        ),
        raises(DeniedError),
        "Token signed by a stranger is not rejected",
    )


def test_rejects_token_of_other_realm(tmp_path: Path) -> None:
    private, keys = pair()
    assert_that(
        lambda: Keycloak(settings(tmp_path, "main"), keys).identity(
            token(private, {"iss": "http://kc.local/realms/other"})
        ),
        raises(DeniedError),
        "Token of another realm is not rejected",
    )


def test_rejects_expired_token(tmp_path: Path) -> None:
    realm = f"r{random.randint(1, 999)}"
    private, keys = pair()
    assert_that(
        lambda: Keycloak(settings(tmp_path, realm), keys).identity(
            token(private, {"iss": f"http://kc.local/realms/{realm}", "exp": 1})
        ),
        raises(DeniedError),
        "Expired token is not rejected",
    )


def test_rejects_garbage_instead_of_token(tmp_path: Path) -> None:
    _, keys = pair()
    assert_that(
        lambda: Keycloak(settings(tmp_path, "main"), keys).identity("garbage"),
        raises(DeniedError),
        "Garbage is not rejected",
    )


def test_open_passport_allows_everything_without_token() -> None:
    identity = Open().identity("")
    assert_that(
        (identity.allows("admin"), identity.sees("any"), identity.group()),
        equal_to((True, True, "dev")),
        "Development passport does not allow everything",
    )
