import base64
import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import jwt
from alembic import command
from alembic.config import Config
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from hamcrest import assert_that, contains_string, equal_to
from httpx import Response
from jwt.algorithms import RSAAlgorithm

from app.core.schema.environment import Environment
from app.core.settings import EnvSettings
from app.web.application import create_app


class Handler(BaseHTTPRequestHandler):
    """Request handler of the fake provider."""

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        del code, size

    def provider(self) -> "Provider":
        server = self.server
        assert isinstance(server, Server)
        return server.provider

    def reply(self, status: int, body: dict[str, object]) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        provider = self.provider()
        jwk = json.loads(RSAAlgorithm.to_jwk(provider.key.public_key()))
        self.reply(200, {"keys": [{**jwk, "kid": "k1", "alg": "RS256", "use": "sig"}]})

    def do_POST(self) -> None:
        provider = self.provider()
        form = parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
        provider.forms.append(form)
        challenge = provider.challenges.get(form["code"][0], "")
        digest = hashlib.sha256(form["code_verifier"][0].encode()).digest()
        if base64.urlsafe_b64encode(digest).decode().rstrip("=") != challenge:
            self.reply(400, {"error": "invalid_grant"})
            return
        self.reply(200, {"access_token": provider.token()})


class Server(ThreadingHTTPServer):
    """Server of the fake provider that knows the provider it serves."""

    def __init__(self, provider: "Provider") -> None:
        super().__init__(("127.0.0.1", 0), Handler)
        self.provider = provider


class Provider:
    """Fake identity provider with a token endpoint and published keys, on port zero."""

    def __init__(self, claims: dict[str, object]) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.challenges: dict[str, str] = {}
        self.claims = claims
        self.forms: list[dict[str, list[str]]] = []
        self.server = Server(self)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def address(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def token(self) -> str:
        return jwt.encode(
            {
                "exp": int(time.time()) + 300,
                "aud": "cargo",
                "iss": f"{self.address()}/realms/main",
                **self.claims,
            },
            self.key,
            algorithm="RS256",
            headers={"kid": "k1"},
        )

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def settings(folder: Path, provider: Provider, extra: str = "") -> EnvSettings:
    url = f"sqlite+aiosqlite:///{folder / 'web.db'}"
    (folder / ".env").write_text(
        f"DATABASE_URL={url}\nSTORAGE_DIR={folder / 'files'}\nKEYCLOAK_URL={provider.address()}\n"
        f"KEYCLOAK_REALM=main\nKEYCLOAK_CLIENT_ID=cargo\nSESSION_SECRET=top-secret-for-tests\n"
        f"SESSION_SECURE=false\n{extra}",
        encoding="utf-8",
    )
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    return EnvSettings(Environment(str(folder / ".env")))


def signed_in(client: TestClient, provider: Provider, target: str = "/reconcile") -> Response:
    start: Response = client.get(f"/auth/login?next={target}")
    query = parse_qs(urlparse(start.headers["location"]).query)
    provider.challenges["the-code"] = query["code_challenge"][0]
    arrived: Response = client.get(f"/auth/callback?code=the-code&state={query['state'][0]}")
    return arrived


def claims() -> dict[str, object]:
    return {"sub": "u-1", "preferred_username": "ivanov", "realm_access": {"roles": ["cargo_user"]}}


def test_sends_page_without_session_to_login(tmp_path: Path) -> None:
    provider = Provider(claims())
    try:
        with TestClient(create_app(settings(tmp_path, provider)), follow_redirects=False) as client:
            response = client.get("/archive?month=2030-01")
    finally:
        provider.close()
    assert_that(
        (response.status_code, response.headers["location"]),
        equal_to((302, "/auth/login?next=%2Farchive%3Fmonth%3D2030-01")),
        "Page without a session does not send the visitor to login",
    )


def test_answers_api_without_token_with_401_and_no_redirect(tmp_path: Path) -> None:
    provider = Provider(claims())
    try:
        with TestClient(create_app(settings(tmp_path, provider)), follow_redirects=False) as client:
            response = client.get("/api/jobs/1")
    finally:
        provider.close()
    assert_that(response.status_code, equal_to(401), "API without a token is not refused with 401")


def test_sends_visitor_to_keycloak_with_pkce_challenge(tmp_path: Path) -> None:
    provider = Provider(claims())
    try:
        with TestClient(create_app(settings(tmp_path, provider)), follow_redirects=False) as client:
            response = client.get("/auth/login")
    finally:
        provider.close()
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert_that(
        (
            response.headers["location"].startswith(provider.address() + "/realms/main/"),
            query["code_challenge_method"],
            query["response_type"],
            "cargo_login" in response.headers["set-cookie"],
        ),
        equal_to((True, ["S256"], ["code"], True)),
        "Login does not start the code flow with PKCE",
    )


def test_opens_pages_after_login_and_returns_to_requested_page(tmp_path: Path) -> None:
    provider = Provider(claims())
    try:
        with TestClient(create_app(settings(tmp_path, provider)), follow_redirects=False) as client:
            arrived = signed_in(client, provider, "/archive")
            page = client.get("/archive")
    finally:
        provider.close()
    assert_that(
        (arrived.status_code, arrived.headers["location"], page.status_code),
        equal_to((302, "/archive", 200)),
        "Visitor is not let in after login",
    )


def test_sends_code_verifier_and_client_to_token_endpoint(tmp_path: Path) -> None:
    provider = Provider(claims())
    try:
        with TestClient(create_app(settings(tmp_path, provider)), follow_redirects=False) as client:
            signed_in(client, provider)
    finally:
        provider.close()
    form = provider.forms[0]
    assert_that(
        (form["grant_type"], form["client_id"], len(form["code_verifier"][0]) >= 43),
        equal_to((["authorization_code"], ["cargo"], True)),
        "Token request does not carry the grant, client and verifier",
    )


def test_refuses_callback_with_foreign_state(tmp_path: Path) -> None:
    provider = Provider(claims())
    try:
        with TestClient(create_app(settings(tmp_path, provider)), follow_redirects=False) as client:
            client.get("/auth/login")
            response = client.get("/auth/callback?code=the-code&state=forged")
    finally:
        provider.close()
    assert_that(
        (response.status_code, provider.forms),
        equal_to((401, [])),
        "Callback with a foreign state is not refused",
    )


def test_refuses_callback_without_login_cookie(tmp_path: Path) -> None:
    provider = Provider(claims())
    try:
        with TestClient(create_app(settings(tmp_path, provider)), follow_redirects=False) as client:
            response = client.get("/auth/callback?code=the-code&state=x")
    finally:
        provider.close()
    assert_that(
        response.status_code, equal_to(401), "Callback without a login cookie is not refused"
    )


def test_refuses_login_when_token_has_no_sub(tmp_path: Path) -> None:
    provider = Provider({"sub": "", "realm_access": {"roles": ["cargo_user"]}})
    try:
        with TestClient(create_app(settings(tmp_path, provider)), follow_redirects=False) as client:
            response = signed_in(client, provider)
    finally:
        provider.close()
    assert_that(
        response.status_code, equal_to(401), "Login with a token without sub is not refused"
    )


def test_refuses_login_of_person_without_role(tmp_path: Path) -> None:
    provider = Provider({"sub": "u-2"})
    try:
        with TestClient(create_app(settings(tmp_path, provider)), follow_redirects=False) as client:
            response = signed_in(client, provider)
    finally:
        provider.close()
    assert_that(
        response.status_code, equal_to(403), "Login of a person without a role is not refused"
    )


def test_sends_visitor_to_login_again_when_session_is_forged(tmp_path: Path) -> None:
    provider = Provider(claims())
    try:
        with TestClient(create_app(settings(tmp_path, provider)), follow_redirects=False) as client:
            client.cookies.set("cargo_session", "e30=.forged")
            response = client.get("/reconcile")
    finally:
        provider.close()
    assert_that(response.status_code, equal_to(302), "Forged session is not sent to login")


def test_ends_session_on_logout_and_asks_keycloak_to_end_its_own(tmp_path: Path) -> None:
    provider = Provider(claims())
    try:
        with TestClient(create_app(settings(tmp_path, provider)), follow_redirects=False) as client:
            signed_in(client, provider)
            leaving = client.get("/auth/logout")
            after = client.get("/reconcile")
    finally:
        provider.close()
    assert_that(
        (leaving.headers["location"].split("?")[0], after.status_code),
        equal_to((f"{provider.address()}/realms/main/protocol/openid-connect/logout", 302)),
        "Logout does not end the session",
    )


def test_keeps_bearer_token_working_for_api(tmp_path: Path) -> None:
    provider = Provider(claims())
    try:
        with TestClient(create_app(settings(tmp_path, provider)), follow_redirects=False) as client:
            response = client.get(
                "/api/jobs/1", headers={"Authorization": f"Bearer {provider.token()}"}
            )
    finally:
        provider.close()
    assert_that(response.status_code, equal_to(404), "Bearer token is not accepted by API")


def test_marks_session_cookie_secure_when_asked(tmp_path: Path) -> None:
    provider = Provider(claims())
    try:
        with TestClient(
            create_app(settings(tmp_path, provider, "SESSION_SECURE=true\n")),
            follow_redirects=False,
            base_url="https://testserver",
        ) as client:
            response = signed_in(client, provider)
    finally:
        provider.close()
    assert_that(
        response.headers["set-cookie"],
        contains_string("Secure"),
        "Session cookie is not marked Secure",
    )


def test_needs_no_login_when_login_is_disabled(tmp_path: Path) -> None:
    provider = Provider(claims())
    try:
        with TestClient(
            create_app(settings(tmp_path, provider, "AUTH_DISABLED=true\nAUTH_DEV_USER_ID=me\n")),
            follow_redirects=False,
        ) as client:
            codes = (client.get("/reconcile").status_code, client.get("/auth/login").status_code)
    finally:
        provider.close()
    assert_that(codes, equal_to((200, 302)), "Disabled login does not skip the login page")


def test_refuses_to_start_without_session_secret(tmp_path: Path) -> None:
    provider = Provider(claims())
    try:
        config = settings(tmp_path, provider, "SESSION_SECRET=\n")
        failed = False
        try:
            create_app(config)
        except ValueError:
            failed = True
    finally:
        provider.close()
    assert_that(
        failed, equal_to(True), "Application does not refuse to start without a session secret"
    )
