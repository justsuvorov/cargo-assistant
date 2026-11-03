import asyncio
from datetime import datetime
from pathlib import Path

from hamcrest import assert_that, equal_to, raises
from sqlalchemy import select

from app.core.schema.environment import Environment
from app.jobs.database import Database
from app.jobs.gateway import Gateway, Tracked
from app.jobs.models import Base, Job, LLMCall
from app.llm.assembly import Configured
from app.llm.errors import MisconfiguredError
from app.llm.fake import FakeModel
from app.llm.ledger import Measured, Outcome, Route
from app.llm.model import Model
from app.llm.probe import Survey


class Silent:
    """Test double named silent."""

    def info(self, message: str, job_id: int, declaration_id: int) -> None:
        pass

    def warning(self, message: str, job_id: int, declaration_id: int) -> None:
        pass

    def error(self, message: str, job_id: int, declaration_id: int) -> None:
        pass


class Logged:
    """Test double named logged."""

    def purpose(self) -> str:
        return "profile.policy"

    def origin(self) -> Route:
        return Route("fake", "m")

    def digest(self) -> str:
        return "d" * 8

    def outcome(self) -> Outcome:
        return Measured((3, 4), 0.5, valid=True)


class Assembled:
    """Test double named assembled."""

    def model(self) -> Model:
        return FakeModel({})

    def probe(self, parallel: int) -> Survey:
        raise NotImplementedError(parallel)


def test_names_the_missing_setting_when_gateway_has_no_url(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("LLM_PROVIDER=vsk\n", encoding="utf-8")
    loop = asyncio.new_event_loop()
    ledger = Tracked(Database(f"sqlite+aiosqlite:///{tmp_path / 'g.db'}"), loop, 5.0)
    loop.close()
    gateway = Gateway(Configured(Environment(str(tmp_path / ".env")), Silent(), ledger))
    assert_that(
        lambda: gateway.model(1),
        raises(MisconfiguredError, "LLM_API_URL"),
        "Gateway without a configured model does not name the missing setting",
    )


async def books_call_under_the_job_of_the_thread(tmp_path: Path) -> int:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'g.db'}")
    async with database.session() as session:
        connection = await session.connection()
        await connection.run_sync(Base.metadata.create_all)
        moment = datetime(2026, 1, 1)
        session.add(Job(kind="x", status="running", created_at=moment, updated_at=moment))
        await session.commit()
    tracked = Tracked(database, asyncio.get_running_loop(), 10.0)
    Gateway(Assembled()).model(1)
    await asyncio.to_thread(tracked.record, Logged())
    async with database.session() as session:
        calls = (await session.scalars(select(LLMCall))).all()
    await database.close()
    return calls[0].job_id or 0


def test_books_call_under_the_job_of_the_thread(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(books_call_under_the_job_of_the_thread(tmp_path), 30)),
        equal_to(1),
        "Call of the model is not booked under the job that made it",
    )
