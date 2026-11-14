import asyncio
import os
import random
import uuid
from datetime import date, datetime
from pathlib import Path

import pytest
from hamcrest import assert_that, contains_string, equal_to, raises
from sqlalchemy import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.clock import Utc
from app.jobs.database import Database
from app.jobs.errors import MissingProfileError, NotReadyError
from app.jobs.folios import Folios
from app.jobs.models import Base, Policy, PolicyProfile
from app.policy.schema.profile import Profile


class Fixed:
    """Test double named fixed."""

    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


def profile(number: str = "", issued: date = date.min, insurer: str = "") -> Profile:
    return Profile(number=number, issued=issued, insurer=insurer, clauses={})


async def prepare(path: Path) -> tuple[Database, int]:
    database = Database(f"sqlite+aiosqlite:///{path / 'f.db'}")
    async with database.session() as session:
        connection = await session.connection()
        await connection.run_sync(Base.metadata.create_all)
        session.add(Policy(owner="u", package_sha="s", number="", insured=""))
        await session.commit()
    return database, 1


async def administer(url: str, statement: str) -> None:
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as connection:
        await connection.exec_driver_sql(statement)
    await engine.dispose()


async def numbers_drafts_one_after_another(tmp_path: Path) -> int:
    database, policy = await prepare(tmp_path)
    folio = Folios(database, Utc())
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
    database, policy = await prepare(tmp_path)
    folio = Folios(database, Utc())
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
    database, policy = await prepare(tmp_path)
    folio = Folios(database, Utc())
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
    database, policy = await prepare(tmp_path)
    moment = datetime(2026, 5, 4, 12, 0)
    folio = Folios(database, Fixed(moment))
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
    database, policy = await prepare(tmp_path)
    folio = Folios(database, Utc())
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


async def takes_draft_while_nobody_approved_a_version(tmp_path: Path) -> tuple[str, int]:
    database, policy = await prepare(tmp_path)
    folio = Folios(database, Utc())
    await folio.draft(policy, profile("A", date(2025, 1, 1), "B"))
    taken = await folio.taken(policy)
    await database.close()
    return taken.status, taken.version


def test_takes_draft_while_nobody_approved_a_version(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(takes_draft_while_nobody_approved_a_version(tmp_path), 30)),
        equal_to(("draft", 1)),
        "Draft is not used for reconciliation while no version is approved",
    )


async def answers_from_approved_version_after_new_draft(tmp_path: Path) -> tuple[bool, str, int]:
    database, policy = await prepare(tmp_path)
    folio = Folios(database, Utc())
    number = uuid.uuid4().hex
    await folio.draft(policy, profile(number, date(2025, 1, 1), "B"))
    await folio.approve(policy, 1, "expert")
    await folio.draft(policy, profile("other", date(2025, 1, 1), "B"))
    taken = await folio.taken(policy)
    await database.close()
    return taken.policy.number() == number, taken.status, taken.version


def test_answers_from_approved_version_after_new_draft(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(answers_from_approved_version_after_new_draft(tmp_path), 30)),
        equal_to((True, "approved", 1)),
        "Approved profile does not stay in force after a new draft",
    )


async def takes_problems_of_the_package_with_the_profile(tmp_path: Path) -> tuple[bool]:
    database, policy = await prepare(tmp_path)
    folio = Folios(database, Utc())
    problem = f"Файл {uuid.uuid4().hex} не читается"
    await folio.draft(
        policy,
        Profile(number="A", issued=date(2025, 1, 1), insurer="B", clauses={}, problems=(problem,)),
    )
    taken = await folio.taken(policy)
    await database.close()
    return (taken.problems == (problem,),)


def test_takes_problems_of_the_package_with_the_profile(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(takes_problems_of_the_package_with_the_profile(tmp_path), 30)),
        equal_to((True,)),
        "Problems of the package do not come with the profile",
    )


async def takes_nothing_from_policy_without_profile(tmp_path: Path) -> bool:
    database, policy = await prepare(tmp_path)
    try:
        await Folios(database, Utc()).taken(policy)
    except MissingProfileError:
        return True
    finally:
        await database.close()
    return False


def test_takes_nothing_from_policy_without_profile(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(takes_nothing_from_policy_without_profile(tmp_path), 30)),
        equal_to(True),
        "Policy without a profile does not say so",
    )


async def fills_requisites(tmp_path: Path) -> tuple[str, str]:
    database, policy = await prepare(tmp_path)
    number = f"N{random.randint(1, 999)}"
    await Folios(database, Utc()).draft(policy, profile(number, insurer="Икс"))
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
    database, _ = await prepare(tmp_path)
    try:
        await Folios(database, Utc()).draft(99, profile())
    finally:
        await database.close()


def test_refuses_unknown_policy(tmp_path: Path) -> None:
    assert_that(
        lambda: asyncio.run(asyncio.wait_for(drafts_unknown_policy(tmp_path), 30)),
        raises(Exception, "Полис 99 не найден"),
        "Draft of an unknown policy is not refused",
    )


async def drafts_at_once(url: str, count: int) -> list[int]:
    database = Database(url)
    async with database.session() as session:
        connection = await session.connection()
        await connection.run_sync(Base.metadata.create_all)
        session.add(Policy(owner="u", package_sha="s", number="", insured=""))
        await session.commit()
    folio = Folios(database, Utc())
    found = await asyncio.gather(*[folio.draft(1, profile(f"N{each}")) for each in range(count)])
    await database.close()
    return sorted(found)


@pytest.mark.postgres
@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is unset")
def test_gives_drafts_saved_at_once_different_versions_without_losing_any_on_postgres() -> None:
    base = os.environ["TEST_DATABASE_URL"]
    name = f"t34_{uuid.uuid4().hex}"
    asyncio.run(administer(base, f"CREATE DATABASE {name}"))
    try:
        url = make_url(base).set(database=name).render_as_string(False)
        assert_that(
            asyncio.run(asyncio.wait_for(drafts_at_once(url, 4), 60)),
            equal_to([1, 2, 3, 4]),
            "Drafts saved at once get equal versions or some of them are lost",
        )
    finally:
        asyncio.run(administer(base, f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))


def test_gives_drafts_saved_at_once_different_versions_on_sqlite(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(
            asyncio.wait_for(drafts_at_once(f"sqlite+aiosqlite:///{tmp_path / 'r.db'}", 4), 60)
        ),
        equal_to([1, 2, 3, 4]),
        "Drafts saved at once on sqlite get equal versions or some of them are lost",
    )


async def refuses_equal_versions(tmp_path: Path) -> bool:
    database, policy = await prepare(tmp_path)
    async with database.session() as session:
        session.add_all(
            [PolicyProfile(policy_id=policy, version=1), PolicyProfile(policy_id=policy, version=1)]
        )
        try:
            await session.commit()
        except IntegrityError:
            return True
        return False


def test_refuses_two_profiles_of_a_policy_with_one_version(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(refuses_equal_versions(tmp_path), 30)),
        equal_to(True),
        "Two profiles of one policy with the same version are accepted",
    )
