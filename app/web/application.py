import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.auth.exchange import Remote
from app.auth.passport import Keycloak, Open, Passport, RemoteKeys
from app.auth.seal import Sealed, Signed
from app.core.clock import Utc
from app.core.journal import Sink
from app.core.schema.environment import Environment
from app.core.settings import EnvSettings, Settings
from app.jobs.database import Database
from app.jobs.folios import Folios
from app.jobs.intake import Intake
from app.jobs.packages import Shelving
from app.jobs.queue import Queue
from app.storage.disk import DiskStorage
from app.storage.layout import Keys
from app.web import api, login, pages, policies, results
from app.web.services import Services


def passport(settings: Settings) -> Passport:
    return (
        Open(settings.user())
        if settings.development()
        else Keycloak(settings, RemoteKeys(settings.certs()))
    )


def session(settings: Settings, seal: Signed) -> Passport:
    return Open(settings.user()) if settings.development() else Sealed(seal)


def announce(settings: Settings, sink: Sink) -> None:
    if settings.development():
        sink.warning("Вход отключён, сервис доступен без проверки пользователя")


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    announce(application.state.services.settings, logging.getLogger("web"))
    yield
    await application.state.services.database.close()


def create_app(settings: Settings) -> FastAPI:
    database = Database(settings.database())
    queue = Queue(database, Utc())
    seal = Signed(settings.secret() or ("development" if settings.development() else ""), Utc())
    application = FastAPI(title="cargo-assistant", lifespan=lifespan)
    storage = DiskStorage(settings.storage())
    application.state.services = Services(
        settings,
        database,
        queue,
        Intake(database, queue, storage, Keys(), Utc()),
        Shelving(database, queue, storage, Keys()),
        Folios(database, Utc()),
        passport(settings),
        session(settings, seal),
        seal,
        Remote(settings),
        storage,
    )
    application.mount(
        "/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static"
    )
    application.include_router(login.router)
    application.include_router(policies.router)
    application.include_router(pages.router)
    application.include_router(results.router)
    application.include_router(api.router)
    return application


def build() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return create_app(EnvSettings(Environment()))
