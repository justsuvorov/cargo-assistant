import asyncio
import random
import uuid
from datetime import date, datetime
from pathlib import Path

from hamcrest import assert_that, contains_string, equal_to, raises

from app.core.clock import Utc
from app.jobs.database import Database
from app.jobs.errors import NotReadyError, WaitingError
from app.jobs.folios import Folios
from app.jobs.models import Base, Declaration, Policy
from app.jobs.queue import Queue
from app.policy.schema.profile import Profile


class Fixed:
    """Test double named fixed."""

    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


def profile(number: str = "", issued: date = date.min, insurer: str = "") -> Profile:
    return Profile(number=number, issued=issued, insurer=insurer, clauses={})


async def prepare(path: Path) -> tuple[Database, Queue, int]:
    database = Database(f"sqlite+aiosqlite:///{path / 'f.db'}")
    async with database.session() as session:
        connection = await session.connection()
        await connection.run_sync(Base.metadata.create_all)
        session.add(Policy(access_group="g", number="", insured=""))
        await session.commit()
    return database, Queue(database, Utc()), 1


async def numbers_drafts_one_after_another(tmp_path: Path) -> int:
    database, queue, policy = await prepare(tmp_path)
    folio = Folios(database, queue, Utc())
    await folio.draft(policy, profile())
    await folio.draft(policy, profile("A"))
    latest = await folio.latest(policy)
    await database.close()
    return latest.number


def test_numbers_drafts_one_after_another(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(numbers_drafts_one_after_another(tmp_path), 30)),
        equal_to(2),
        "Drafts of one policy are not numbered one after another",
    )


async def refuses_profile_without_issue_date(tmp_path: Path) -> str:
    database, queue, policy = await prepare(tmp_path)
    folio = Folios(database, queue, Utc())
    await folio.draft(policy, profile("A", date.min, "B"))
    try:
        await folio.approve(policy, 1, "expert")
    except NotReadyError as error:
        return str(error)
    finally:
        await database.close()
    return ""


def test_refuses_profile_without_issue_date(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(refuses_profile_without_issue_date(tmp_path), 30)),
        contains_string("дата выдачи"),
        "Profile without an issue date is not refused for approval",
    )


async def refuses_profile_without_number_and_insurer(tmp_path: Path) -> str:
    database, queue, policy = await prepare(tmp_path)
    folio = Folios(database, queue, Utc())
    await folio.draft(policy, profile("", date(2025, 1, 1), " "))
    try:
        await folio.approve(policy, 1, "expert")
    except NotReadyError as error:
        return str(error)
    finally:
        await database.close()
    return ""


def test_refuses_profile_without_number_and_insurer(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(refuses_profile_without_number_and_insurer(tmp_path), 30)),
        equal_to("Подтвердить нельзя, не заполнено: номер полиса, страхователь"),
        "Profile without a number and an insurer is not refused for approval",
    )


async def approves_and_remembers_who_and_when(tmp_path: Path) -> tuple[str, str, datetime | None]:
    database, queue, policy = await prepare(tmp_path)
    moment = datetime(2026, 5, 4, 12, 0)
    folio = Folios(database, queue, Fixed(moment))
    await folio.draft(policy, profile("A", date(2025, 1, 1), "B"))
    await folio.approve(policy, 1, "ivanov")
    latest = await folio.latest(policy)
    await database.close()
    return latest.status, latest.approved_by, latest.approved_at


def test_approves_and_remembers_who_and_when(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(approves_and_remembers_who_and_when(tmp_path), 30)),
        equal_to(("approved", "ivanov", datetime(2026, 5, 4, 12, 0))),
        "Approval does not keep who approved the profile and when",
    )


async def refuses_approval_of_outdated_version(tmp_path: Path) -> bool:
    database, queue, policy = await prepare(tmp_path)
    folio = Folios(database, queue, Utc())
    await folio.draft(policy, profile("A", date(2025, 1, 1), "B"))
    await folio.draft(policy, profile("A2", date(2025, 1, 1), "B"))
    try:
        await folio.approve(policy, 1, "expert")
    except NotReadyError:
        return True
    finally:
        await database.close()
    return False


def test_refuses_approval_of_outdated_version(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(refuses_approval_of_outdated_version(tmp_path), 30)),
        equal_to(True),
        "Approval of a version that is not the latest is not refused",
    )


async def waits_for_profile_while_only_draft_exists(tmp_path: Path) -> bool:
    database, queue, policy = await prepare(tmp_path)
    folio = Folios(database, queue, Utc())
    await folio.draft(policy, profile("A", date(2025, 1, 1), "B"))
    try:
        await folio.approved(policy)
    except WaitingError:
        return True
    finally:
        await database.close()
    return False


def test_waits_for_profile_while_only_draft_exists(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(waits_for_profile_while_only_draft_exists(tmp_path), 30)),
        equal_to(True),
        "Draft profile is not treated as missing for reconciliation",
    )


async def answers_from_approved_version_after_new_draft(tmp_path: Path) -> str:
    database, queue, policy = await prepare(tmp_path)
    folio = Folios(database, queue, Utc())
    number = uuid.uuid4().hex
    await folio.draft(policy, profile(number, date(2025, 1, 1), "B"))
    await folio.approve(policy, 1, "expert")
    await folio.draft(policy, profile("other", date(2025, 1, 1), "B"))
    answer = (await folio.approved(policy)).number()
    await database.close()
    return f"{answer == number}"


def test_answers_from_approved_version_after_new_draft(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(answers_from_approved_version_after_new_draft(tmp_path), 30)),
        equal_to("True"),
        "Approved profile does not stay in force after a new draft",
    )


async def releases_waiting_job_of_the_policy_on_approval(tmp_path: Path) -> str:
    database, queue, policy = await prepare(tmp_path)
    folio = Folios(database, queue, Utc())
    async with database.session() as session:
        job = await queue.add(session, "reconcile", {"declaration_id": 1})
        session.add(
            Declaration(
                policy_id=policy,
                job_id=job,
                access_group="g",
                file_name="a.xlsx",
                created_at=datetime(2026, 1, 1),
            )
        )
        await session.commit()
    await queue.claim(1)
    await queue.wait(job, "Ожидает профиль полиса")
    await folio.draft(policy, profile("A", date(2025, 1, 1), "B"))
    await folio.approve(policy, 1, "expert")
    status = (await queue.snapshot(job)).status
    await database.close()
    return status


def test_releases_waiting_job_of_the_policy_on_approval(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(releases_waiting_job_of_the_policy_on_approval(tmp_path), 30)),
        equal_to("queued"),
        "Approval does not put the waiting job back into the queue",
    )


async def fills_requisites(tmp_path: Path) -> tuple[str, str]:
    database, queue, policy = await prepare(tmp_path)
    number = f"N{random.randint(1, 999)}"
    await Folios(database, queue, Utc()).draft(policy, profile(number, insurer="Икс"))
    async with database.session() as session:
        row = await session.get(Policy, policy)
    await database.close()
    return (row.number, row.insured) if row else ("", "")


def test_fills_policy_requisites_from_draft(tmp_path: Path) -> None:
    number, insured = asyncio.run(asyncio.wait_for(fills_requisites(tmp_path), 30))
    assert_that(
        (number.startswith("N"), insured),
        equal_to((True, "Икс")),
        "Draft does not fill the number and the insurer of the policy",
    )


async def drafts_unknown_policy(tmp_path: Path) -> None:
    database, queue, _ = await prepare(tmp_path)
    try:
        await Folios(database, queue, Utc()).draft(99, profile())
    finally:
        await database.close()


def test_refuses_unknown_policy(tmp_path: Path) -> None:
    assert_that(
        lambda: asyncio.run(asyncio.wait_for(drafts_unknown_policy(tmp_path), 30)),
        raises(Exception, "Полис 99 не найден"),
        "Draft of an unknown policy is not refused",
    )
