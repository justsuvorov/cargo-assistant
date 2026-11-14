import asyncio
import contextvars
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

from hamcrest import assert_that, equal_to, raises
from pydantic import BaseModel

from app.core.clock import Utc
from app.domain.place import Spot
from app.domain.semantics import Inquiry
from app.jobs.building import Workbench
from app.jobs.checking import Postponed, Postponing, Unconfigured
from app.jobs.database import Database
from app.jobs.errors import WaitingError
from app.jobs.folios import Folios
from app.jobs.models import Base, Declaration, Job, Policy
from app.jobs.queue import Queue, Snapshot
from app.jobs.stages import Benches, Kit, Profiled, Routed, Standard, UnknownKindError
from app.jobs.versions import Stamp
from app.llm.errors import MisconfiguredError
from app.llm.fake import FakeModel
from app.llm.messages import Message
from app.llm.model import Model
from app.policy.schema.profile import Profile
from app.storage.disk import DiskStorage
from tests.rules.fakes import Text


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


async def prepare(path: Path, *, bound: bool, build: str = "") -> tuple[Database, Folios]:
    database = Database(f"sqlite+aiosqlite:///{path / 's.db'}")
    async with database.session() as session:
        connection = await session.connection()
        await connection.run_sync(Base.metadata.create_all)
        if build:
            session.add(
                Job(
                    kind="profile_build",
                    status=build,
                    created_at=datetime(2026, 1, 1),
                    updated_at=datetime(2026, 1, 1),
                )
            )
            await session.flush()
        session.add(Policy(owner="u", package_sha="s", job_id=1 if build else None))
        await session.flush()
        session.add(
            Declaration(
                policy_id=1 if bound else None,
                owner="u",
                file_name="a.xlsx",
                created_at=datetime(2026, 1, 1),
            )
        )
        await session.commit()
    return database, Folios(database, Utc())


async def passes(tmp_path: Path, *, bound: bool, build: str, profile: str) -> str:
    database, folio = await prepare(tmp_path, bound=bound, build=build)
    if profile:
        await folio.draft(1, Profile(number="A", issued=date(2025, 1, 1), insurer="B", clauses={}))
    if profile == "approved":
        await folio.approve(1, 1, "owner")
    try:
        await Profiled(folio, database).run(snapshot())
    except WaitingError as error:
        return str(error)
    finally:
        await database.close()
    return "passed"


def test_waits_for_the_build_of_the_profile_that_goes(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(
            asyncio.wait_for(passes(tmp_path, bound=True, build="running", profile=""), 30)
        ),
        equal_to("Ожидает сборки профиля полиса"),
        "Declaration does not wait for the profile that is being built",
    )


def test_passes_with_a_draft_profile_without_waiting_for_an_expert(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(
            asyncio.wait_for(passes(tmp_path, bound=True, build="done", profile="draft"), 30)
        ),
        equal_to("passed"),
        "Declaration of a policy with a draft profile is held back",
    )


def test_passes_with_an_approved_profile(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(
            asyncio.wait_for(passes(tmp_path, bound=True, build="done", profile="approved"), 30)
        ),
        equal_to("passed"),
        "Declaration of a policy with an approved profile is not let through",
    )


def test_passes_without_a_profile_when_the_build_failed(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(passes(tmp_path, bound=True, build="failed", profile=""), 30)),
        equal_to("passed"),
        "Declaration is held back although the build of its profile failed",
    )


def test_passes_declaration_without_policy(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(passes(tmp_path, bound=False, build="", profile=""), 30)),
        equal_to("passed"),
        "Declaration that is not bound to a policy is held back",
    )


async def asks_pipelines_for_other_kind(tmp_path: Path) -> None:
    database, folio = await prepare(tmp_path, bound=False)
    pool = ThreadPoolExecutor(1)
    try:
        bench = Workbench(DiskStorage(tmp_path / "files"), tmp_path / "home")
        kit = Kit(tmp_path, DiskStorage(tmp_path), Stamp("t", "c", "p", "m"), Postponing(), pool)
        Routed(
            Standard(Silent(), folio, database, bench, kit),
            Standard(Silent(), folio, database, bench, kit),
        ).stages("other")
    finally:
        pool.shutdown()
        await database.close()


def test_refuses_kind_that_no_pipeline_knows(tmp_path: Path) -> None:
    assert_that(
        lambda: asyncio.run(asyncio.wait_for(asks_pipelines_for_other_kind(tmp_path), 30)),
        raises(UnknownKindError),
        "Kind without a pipeline is not refused",
    )


class Answering:
    """Models whose model answers every semantic question about cargo with a mismatch."""

    def model(self, _job_id: int) -> Model:
        return FakeModel(
            {"semantic.cargo": '{"answers": [{"id": 1, "status": "mismatch", "comment": "нет"}]}'}
        )


class Unreachable:
    """Models of a process whose model gateway is not configured."""

    def model(self, job_id: int) -> Model:
        raise MisconfiguredError(f"Для задачи {job_id} не настроен шлюз модели")


def test_judges_semantic_questions_on_the_model_gateway_with_the_version_of_the_prompt() -> None:
    judge = Benches(Answering(), Silent(), 1, 40).judge(random.randint(1, 99))
    verdict = judge.verdicts(
        (Inquiry(Spot("1", "cargo"), "мех", Text("ГП п. 5", "грузы, кроме меха"), "правило"),)
    )[0]
    assert_that(
        (judge.version(), verdict.status().key(), verdict.reason().source()),
        equal_to(("semantic-1", "mismatch", "llm")),
        "Benches does not judge on the model gateway with the version of the prompt",
    )


def test_postpones_semantic_questions_when_the_gateway_is_not_configured() -> None:
    judge = Unconfigured(Benches(Unreachable(), Silent(), 1, 40)).judge(random.randint(1, 99))
    assert_that(
        (judge.version(), isinstance(judge, Postponed)),
        equal_to(("none", True)),
        "Benches without a configured gateway does not fall back to the postponed judge",
    )


_JOB: contextvars.ContextVar[int] = contextvars.ContextVar("job", default=0)


class Peeking:
    """Model that answers every cargo question with a match and remembers the job it saw."""

    def __init__(self) -> None:
        self.seen: list[int] = []

    def answer[T: BaseModel](
        self, purpose: str, messages: tuple[Message, ...], schema: type[T]
    ) -> T:
        self.seen.append(_JOB.get())
        return FakeModel(
            {"semantic.cargo": '{"answers": [{"id": 1, "status": "match", "comment": "да"}]}'}
        ).answer(purpose, messages, schema)


class Marking:
    """Models that mark the context of the caller with the job, like the model gateway."""

    def __init__(self, model: Peeking) -> None:
        self._model = model

    def model(self, job_id: int) -> Model:
        _JOB.set(job_id)
        return self._model


def test_books_a_semantic_call_in_another_thread_under_the_job() -> None:
    model = Peeking()
    job = random.randint(1, 99)
    judge = contextvars.copy_context().run(Benches(Marking(model), Silent(), 1, 40).judge, job)
    with ThreadPoolExecutor(1) as pool:
        pool.submit(
            judge.verdicts,
            (Inquiry(Spot("1", "cargo"), "мех", Text("ГП п. 5", "грузы"), "правило"),),
        ).result(timeout=10)
    assert_that(
        model.seen,
        equal_to([job]),
        "Semantic call made in another thread is not booked under its job",
    )
