import asyncio
import random
import string
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from datetime import date, datetime, timedelta
from pathlib import Path

from hamcrest import assert_that, equal_to, less_than, raises
from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.worksheet import Worksheet
from sqlalchemy import select, update

from app.core.clock import Utc
from app.core.schema.environment import Environment
from app.core.settings import EnvSettings
from app.domain.place import Spot
from app.domain.reason import Cause
from app.domain.remark import Note
from app.domain.semantics import Question
from app.domain.status import Match
from app.domain.verdict import Ruling, Verdict
from app.jobs.building import Workbench
from app.jobs.checking import Judge, Postponed, Tabled, Unconfigured
from app.jobs.database import Database
from app.jobs.errors import LostError
from app.jobs.folios import Folios
from app.jobs.logbook import Blank
from app.jobs.models import Base, CheckResult, Correction, Declaration, Job, Policy
from app.jobs.queue import Queue, Snapshot
from app.jobs.retention import Monthly
from app.jobs.stages import Kit, Standard
from app.jobs.versions import Stamp
from app.jobs.worker import Shift
from app.llm.errors import MisconfiguredError
from app.policy.schema.profile import Profile, Wording
from app.reconcile.reconciliation import Found
from app.storage.disk import DiskStorage
from tools.eval.pipeline import Checked
from tools.eval.shelf import Shelf

_CARDS = Path(__file__).parents[2] / "cards"


class Silent:
    """Test double named silent."""

    def info(self, message: str, job_id: int, declaration_id: int) -> None:
        pass

    def warning(self, message: str, job_id: int, declaration_id: int) -> None:
        pass

    def error(self, message: str, job_id: int, declaration_id: int) -> None:
        pass


class Counting:
    """Semantic judge that agrees with everything and counts the batches it was given."""

    def __init__(self, pause: float = 0.0) -> None:
        self.batches: list[int] = []
        self._pause = pause

    def version(self) -> str:
        return "prompts-7"

    def judge(self, _job_id: int) -> "Counting":
        return self

    def verdicts(self, questions: tuple[Question, ...]) -> tuple[Verdict, ...]:
        time.sleep(self._pause)
        self.batches.append(len(questions))
        return tuple(
            Ruling(
                question.place(),
                Match(),
                Cause("fake.match", "llm"),
                Note("Согласовано", question.clause().reference()),
            )
            for question in questions
        )


def put(sheet: Worksheet, row: int, cells: dict[int, str]) -> None:
    for column, value in cells.items():
        sheet.cell(row=row, column=column + 1, value=value)


def russian(path: Path, policy: str) -> None:
    book = Workbook()
    sheet = book.create_sheet("Декларация")
    put(sheet, 1, {5: "Приложение № 2 к Генеральному Полису"})
    put(sheet, 2, {7: f"№ {policy} от 26.08.2026 г."})
    put(sheet, 4, {7: "От ООО «Тест»"})
    put(sheet, 8, {0: "Декларация", 3: "№ Р-5", 4: "об отгрузке"})
    put(sheet, 16, {1: "1.", 2: "Полное наименование груза", 6: "мясо, сыр"})
    put(sheet, 20, {1: "4.", 2: "Страховая сумма", 6: "1000", 8: "рублей"})
    put(sheet, 21, {1: "5.", 2: "Транспорт", 6: "Авто"})
    put(sheet, 22, {1: "6.", 2: "Пункт отправления", 6: "г. Первый"})
    put(sheet, 24, {1: "8.", 2: "Пункт назначения", 6: "г. Второй"})
    put(sheet, 25, {1: "9.", 2: "Период страхования", 6: "21.09.2026", 7: "по", 8: "30.12.2026"})
    book.save(path)


def english(path: Path, policy: str) -> None:
    book = Workbook()
    sheet = book.create_sheet("Declaration")
    put(sheet, 1, {0: "Appendix 2 to the Open Cover"})
    put(sheet, 2, {7: f"No. {policy} dated 26.08.2026"})
    put(sheet, 3, {7: "From Test Trading LLC"})
    put(sheet, 4, {0: "Declaration", 3: "No. 7", 4: "of shipment"})
    put(sheet, 5, {1: "1.", 2: "Full description of cargo", 6: "frozen meat"})
    put(sheet, 6, {1: "4.", 2: "Sum insured", 6: "1500.50", 8: "euro"})
    put(sheet, 7, {1: "5.", 2: "Mode of transport", 6: "Truck"})
    put(sheet, 8, {1: "6.", 2: "Place of departure", 6: "Port A"})
    put(sheet, 9, {1: "8.", 2: "Place of destination", 6: "Port B"})
    put(sheet, 10, {1: "9.", 2: "Insurance period", 6: "03.11.2026", 7: "to", 8: "30.12.2026"})
    book.save(path)


def word() -> str:
    return "".join(random.choices(string.ascii_uppercase, k=6)) + str(random.randint(100, 999))


def profile(number: str) -> Profile:
    wording = Wording(
        source="ГП п.1", effective=date(2025, 1, 1), text="перевозка продуктов питания"
    )
    return Profile(
        number=number,
        issued=date(2025, 1, 1),
        insurer="Страховщик",
        clauses={"object": (wording,), "territory": (wording,)},
    )


class Stand:
    """Everything one test needs: database, storage, queue and a pipeline with a given judge."""

    def __init__(
        self, folder: Path, judge: Counting, make: str, policy: str, *, bound: bool = True
    ) -> None:
        self.bound = bound
        self.database = Database(f"sqlite+aiosqlite:///{folder / 's.db'}")
        self.storage = DiskStorage(folder / "files")
        self.queue = Queue(self.database, Utc())
        self.folio = Folios(self.database, Utc())
        self.pool = ThreadPoolExecutor(2)
        self.judge = judge
        self.folder = folder
        self.make = make
        self.policy = policy
        (folder / ".env").write_text("WORKER_POLL_INTERVAL=0.05\n", encoding="utf-8")
        self.settings = EnvSettings(Environment(str(folder / ".env")))

    async def prepare(self) -> None:
        source = self.folder / "a.xlsx"
        {"ru": russian, "en": english}[self.make](source, self.policy)
        self.storage.save("declarations/1/source/a.xlsx", source.read_bytes())
        async with self.database.session() as session:
            connection = await session.connection()
            await connection.run_sync(Base.metadata.create_all)
            session.add(Policy(number=self.policy if self.bound else "OTHER1", access_group="g"))
            await session.flush()
            session.add(
                Declaration(
                    access_group="g",
                    file_name="a.xlsx",
                    file_key="declarations/1/source/a.xlsx",
                    created_at=datetime(2026, 1, 1),
                )
            )
            job = await self.queue.add(session, "reconcile", {"declaration_id": 1})
            declaration = await session.get(Declaration, 1)
            if declaration is not None:
                declaration.job_id = job
            await session.commit()
        await self.folio.draft(1, profile(self.policy if self.bound else "OTHER1"))
        await self.folio.approve(1, 1, "expert")

    async def drain(self) -> int:
        kit = Kit(
            _CARDS,
            self.storage,
            Stamp("v1", "c1", "p1", "m1"),
            self.judge,
            self.pool,
        )
        bench = Workbench(self.storage, self.folder / "home")
        pipelines = Standard(Silent(), self.folio, self.database, bench, kit)
        return await Shift(self.queue, pipelines, self.settings, Silent(), Blank()).drain()

    async def close(self) -> None:
        self.pool.shutdown()
        await self.database.close()


async def whole_run(folder: Path, make: str) -> tuple[object, ...]:
    stand = Stand(folder, Counting(), make, word())
    try:
        await stand.prepare()
        await stand.drain()
        async with stand.database.session() as session:
            declaration = await session.get(Declaration, 1)
            job = await session.get(Job, 1)
            results = list((await session.scalars(select(CheckResult))).all())
        assert declaration is not None
        assert job is not None
        book = load_workbook(folder / "files" / declaration.result_key)
        return (
            job.status,
            len(results),
            declaration.places_expected,
            declaration.places_answered,
            book.sheetnames,
            book["Результат проверки"].max_row - 1,
            sorted(stand.judge.batches),
            (
                declaration.code_version,
                declaration.cards_version,
                declaration.profile_version,
                declaration.prompts_version,
            ),
            declaration.result_key.endswith("результат проверки.xlsx"),
        )
    finally:
        await stand.close()


def summary(folder: Path, make: str) -> tuple[object, ...]:
    found = asyncio.run(asyncio.wait_for(whole_run(folder, make), 120))
    return (found[0], found[1] == found[2] == found[3] == found[5], found[4], found[6], found[7:])


_EXPECTED = (
    "done",
    True,
    ["Результат проверки", "Особые условия"],
    [1, 1, 1],
    (("v1", "c1", 1, "prompts-7"), True),
)


def test_carries_a_russian_declaration_from_file_to_result_workbook(tmp_path: Path) -> None:
    assert_that(
        summary(tmp_path, "ru"),
        equal_to(_EXPECTED),
        "Russian declaration does not go from file to a result workbook with three model calls",
    )


def test_carries_an_english_declaration_from_file_to_result_workbook(tmp_path: Path) -> None:
    assert_that(
        summary(tmp_path, "en"),
        equal_to(_EXPECTED),
        "English declaration does not go from file to a result workbook with three model calls",
    )


async def rerun(folder: Path) -> tuple[int, int, str]:
    stand = Stand(folder, Counting(), "ru", word())
    try:
        await stand.prepare()
        await stand.drain()
        async with stand.database.session() as session:
            first = (await session.scalars(select(CheckResult))).first()
            assert first is not None
            session.add(
                Correction(
                    declaration_id=1,
                    line=first.line,
                    field=first.field,
                    author="expert",
                    created_at=datetime(2026, 1, 2),
                    status="match",
                    seen_status=first.status,
                    comment="проверено",
                )
            )
            await session.execute(update(Job).values(status="queued"))
            await session.commit()
        await stand.drain()
        async with stand.database.session() as session:
            results = (await session.scalars(select(CheckResult))).all()
            kept = (await session.scalars(select(Correction))).all()
        return len(results), len(kept), kept[0].comment
    finally:
        await stand.close()


def test_keeps_the_correction_of_an_expert_when_the_job_runs_again(tmp_path: Path) -> None:
    results, kept, comment = asyncio.run(asyncio.wait_for(rerun(tmp_path), 120))
    assert_that(
        (results > 0, kept, comment),
        equal_to((True, 1, "проверено")),
        "Second run of the job does not replace the results and keep the correction",
    )


async def purged_versions(folder: Path) -> str:
    stand = Stand(folder, Counting(), "ru", word())
    try:
        await stand.prepare()
        await stand.drain()
        late = Utc()
        removed = await Monthly(stand.database, Later(late), 0).purge()
        async with stand.database.session() as session:
            declaration = await session.get(Declaration, 1)
        assert declaration is not None
        assert removed >= 0
        return declaration.code_version
    finally:
        await stand.close()


class Later:
    """Clock that runs ten years ahead of another clock."""

    def __init__(self, clock: Utc) -> None:
        self._clock = clock

    def now(self) -> datetime:
        return self._clock.now() + timedelta(days=3650)


def test_keeps_versions_of_the_result_when_the_journal_is_purged(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(purged_versions(tmp_path), 120)),
        equal_to("v1"),
        "Purge of the journal does not keep the versions that gave the result",
    )


async def late_write(folder: Path, status: str, attempts: int) -> int:
    stand = Stand(folder, Counting(), "ru", word())
    try:
        await stand.prepare()
        async with stand.database.session() as session:
            await session.execute(update(Job).values(status=status, attempts=attempts))
            await session.commit()
        job = Snapshot(1, "reconcile", "running", "", 0, 1, "", {}, {"declaration_id": 1})
        verdict = Ruling(
            Spot("1", "cargo"), Match(), Cause("x.y", "rule"), Note("комментарий", "п. 1")
        )
        with suppress(LostError):
            await Tabled(stand.database).replace(job, Found((verdict,), 1))
        async with stand.database.session() as session:
            return len((await session.scalars(select(CheckResult))).all())
    finally:
        await stand.close()


def test_writes_nothing_after_the_job_was_taken_again_by_a_later_attempt(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(late_write(tmp_path, "running", 2), 60)),
        equal_to(0),
        "Attempt that no longer owns the job writes results",
    )


def test_writes_nothing_after_the_job_failed_by_timeout(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(late_write(tmp_path, "failed", 1), 60)),
        equal_to(0),
        "Attempt of a job that already failed does not stay silent",
    )


def test_raises_lost_error_for_a_stale_attempt(tmp_path: Path) -> None:
    assert_that(
        lambda: asyncio.run(asyncio.wait_for(strict_late_write(tmp_path), 60)),
        raises(LostError),
        "Stale attempt does not stop loudly",
    )


async def strict_late_write(folder: Path) -> None:
    stand = Stand(folder, Counting(), "ru", word())
    try:
        await stand.prepare()
        async with stand.database.session() as session:
            await session.execute(update(Job).values(status="running", attempts=5))
            await session.commit()
        job = Snapshot(1, "reconcile", "running", "", 0, 1, "", {}, {"declaration_id": 1})
        await Tabled(stand.database).replace(job, Found((), 0))
    finally:
        await stand.close()


async def waits_beside_slow_judge(folder: Path) -> float:
    stand = Stand(folder, Counting(0.5), "ru", word())
    try:
        await stand.prepare()
        task = asyncio.create_task(stand.drain())
        slowest = 0.0
        while not task.done():
            started = time.perf_counter()
            await asyncio.to_thread(sum, range(10))
            slowest = max(slowest, time.perf_counter() - started)
            await asyncio.sleep(0.02)
        await task
        return slowest
    finally:
        await stand.close()


def test_does_not_hold_other_work_while_the_model_answers_slowly(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(waits_beside_slow_judge(tmp_path), 120)),
        less_than(0.4),
        "Slow model calls do not leave the threads that read other declarations free",
    )


async def stage_and_eval(
    folder: Path,
) -> tuple[list[tuple[str, str, str, str]], list[tuple[str, str, str, str]]]:
    stand = Stand(folder, Counting(), "ru", word(), bound=False)
    try:
        await stand.prepare()
        await stand.drain()
        async with stand.database.session() as session:
            rows = (await session.scalars(select(CheckResult))).all()
        staged = sorted((row.line, row.field, row.status, row.reason) for row in rows)
    finally:
        await stand.close()
    outcome = Checked(Shelf(folder / "files" / "declarations" / "1" / "source").catalog(), _CARDS)
    evaluated = sorted(
        (
            verdict.place().shipment(),
            verdict.place().field(),
            verdict.status().key(),
            verdict.reason().code(),
        )
        for verdict in outcome.reconcile("5").verdicts()
    )
    return staged, evaluated


def test_gives_the_same_verdicts_through_the_stage_and_through_eval(tmp_path: Path) -> None:
    staged, evaluated = asyncio.run(asyncio.wait_for(stage_and_eval(tmp_path), 120))
    assert_that(
        staged,
        equal_to(evaluated),
        "Stage and eval do not give the same verdicts for one declaration",
    )


class Unreachable:
    """Judges of a process whose model gateway is not configured."""

    def judge(self, job_id: int) -> Judge:
        raise MisconfiguredError(f"Для задачи {job_id} не настроен шлюз модели")


def test_falls_back_to_the_postponed_judge_when_the_gateway_is_not_configured() -> None:
    judge = Unconfigured(Unreachable()).judge(random.randint(1, 99))
    assert_that(
        (judge.version(), isinstance(judge, Postponed)),
        equal_to(("none", True)),
        "Missing gateway does not leave the postponed judge with the version none",
    )


async def unbound_reasons(folder: Path) -> tuple[str, ...]:
    stand = Stand(folder, Counting(), "ru", word(), bound=False)
    try:
        await stand.prepare()
        await stand.drain()
        async with stand.database.session() as session:
            rows = (await session.scalars(select(CheckResult))).all()
        return tuple(sorted({row.reason for row in rows if row.field in {"sum", "insurer"}}))
    finally:
        await stand.close()


def test_asks_a_person_with_the_reason_of_the_binding_for_an_unbound_declaration(
    tmp_path: Path,
) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(unbound_reasons(tmp_path), 120)),
        equal_to(("policy.unknown",)),
        "Unbound declaration does not get the code of its binding in cards with a policy clause",
    )
