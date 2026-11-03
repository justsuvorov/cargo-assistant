import asyncio
from datetime import date, datetime
from pathlib import Path

from hamcrest import assert_that, equal_to, raises

from app.core.clock import Utc
from app.jobs.database import Database
from app.jobs.errors import WaitingError
from app.jobs.folios import Folios
from app.jobs.models import Base, Declaration, Policy
from app.jobs.queue import Queue, Snapshot
from app.jobs.stages import Profiled, Routed, Standard, UnknownKindError
from app.policy.schema.profile import Profile


class Silent:
    """Test double named silent."""

    def info(self, message: str, job_id: int, declaration_id: int) -> None:
        pass

    def warning(self, message: str, job_id: int, declaration_id: int) -> None:
        pass

    def error(self, message: str, job_id: int, declaration_id: int) -> None:
        pass


def snapshot() -> Snapshot:
    return Snapshot(1, "reconcile", "running", "", 0, 1, "", {}, {"declaration_id": 1})


async def prepare(path: Path, *, bound: bool) -> tuple[Database, Folios]:
    database = Database(f"sqlite+aiosqlite:///{path / 's.db'}")
    async with database.session() as session:
        connection = await session.connection()
        await connection.run_sync(Base.metadata.create_all)
        session.add(Policy(access_group="g"))
        await session.flush()
        session.add(
            Declaration(
                policy_id=1 if bound else None,
                access_group="g",
                file_name="a.xlsx",
                created_at=datetime(2026, 1, 1),
            )
        )
        await session.commit()
    return database, Folios(database, Queue(database, Utc()), Utc())


async def waits_for_approved_profile_of_bound_policy(tmp_path: Path) -> str:
    database, folio = await prepare(tmp_path, bound=True)
    await folio.draft(1, Profile(number="A", issued=date(2025, 1, 1), insurer="B", clauses={}))
    try:
        await Profiled(folio, database).run(snapshot())
    except WaitingError as error:
        return str(error)
    finally:
        await database.close()
    return ""


def test_waits_for_approved_profile_of_bound_policy(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(waits_for_approved_profile_of_bound_policy(tmp_path), 30)),
        equal_to("Ожидает профиль полиса"),
        "Declaration of a policy with a draft profile does not wait",
    )


async def passes_declaration_without_policy(tmp_path: Path) -> bool:
    database, folio = await prepare(tmp_path, bound=False)
    await Profiled(folio, database).run(snapshot())
    await database.close()
    return True


def test_passes_declaration_without_policy(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(passes_declaration_without_policy(tmp_path), 30)),
        equal_to(True),
        "Declaration that is not bound to a policy is held back",
    )


async def passes_declaration_of_policy_with_approved_profile(tmp_path: Path) -> bool:
    database, folio = await prepare(tmp_path, bound=True)
    await folio.draft(1, Profile(number="A", issued=date(2025, 1, 1), insurer="B", clauses={}))
    await folio.approve(1, 1, "expert")
    await Profiled(folio, database).run(snapshot())
    await database.close()
    return True


def test_passes_declaration_of_policy_with_approved_profile(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(
            asyncio.wait_for(passes_declaration_of_policy_with_approved_profile(tmp_path), 30)
        ),
        equal_to(True),
        "Declaration of a policy with an approved profile is not let through",
    )


async def asks_pipelines_for_other_kind(tmp_path: Path) -> None:
    database, folio = await prepare(tmp_path, bound=False)
    try:
        Routed(Standard(Silent(), folio, database), Standard(Silent(), folio, database)).stages(
            "other"
        )
    finally:
        await database.close()


def test_refuses_kind_that_no_pipeline_knows(tmp_path: Path) -> None:
    assert_that(
        lambda: asyncio.run(asyncio.wait_for(asks_pipelines_for_other_kind(tmp_path), 30)),
        raises(UnknownKindError),
        "Kind without a pipeline is not refused",
    )
