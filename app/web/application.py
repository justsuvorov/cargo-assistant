from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.auth.passport import Keycloak, Open, Passport, RemoteKeys
from app.core.clock import Utc
from app.core.schema.environment import Environment
from app.core.settings import EnvSettings, Settings
from app.jobs.database import Database
from app.jobs.intake import Intake
from app.jobs.queue import Queue
from app.storage.disk import DiskStorage
from app.storage.layout import Keys
from app.web import api, pages
from app.web.services import Services


def passport(settings: Settings) -> Passport:
    return Open() if settings.development() else Keycloak(settings, RemoteKeys(settings.certs()))


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    yield
    await application.state.services.database.close()


def create_app(settings: Settings) -> FastAPI:
    database = Database(settings.database())
    queue = Queue(database, Utc())
    application = FastAPI(title="cargo-assistant", lifespan=lifespan)
    application.state.services = Services(
        settings,
        database,
        queue,
        Intake(database, queue, DiskStorage(settings.storage()), Keys(), Utc()),
        passport(settings),
    )
    application.mount(
        "/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static"
    )
    application.include_router(pages.router)
    application.include_router(api.router)
    return application


def build() -> FastAPI:
    return create_app(EnvSettings(Environment()))
