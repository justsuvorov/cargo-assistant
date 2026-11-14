import asyncio
import random
import string
from pathlib import Path

from hamcrest import assert_that, equal_to, raises
from sqlalchemy import select

from app.core.clock import Utc
from app.jobs.building import Workbench
from app.jobs.database import Database
from app.jobs.errors import ChoiceError, MissingWorkspaceError
from app.jobs.models import Base, Declaration, Job, Policy, PolicyProfile, Workspace
from app.jobs.queue import Queue
from app.jobs.workspaces import Filing
from app.storage.archive import Blob
from app.storage.disk import DiskStorage
from app.storage.layout import Keys

_FIRST = "Декларации/Июнь/508.xls"
_SECOND = "Декларации/Июнь/511.xlsx"


def word() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=8))


def folder(policy: bytes = b"policy") -> tuple[Blob, ...]:
    return (
        Blob("ГП.docx", policy),
        Blob("ДС/ДС 1.docx", b"addendum"),
        Blob(_FIRST, b"first"),
        Blob(_SECOND, b"second"),
    )


async def prepare(path: Path) -> tuple[Database, Filing]:
    database = Database(f"sqlite+aiosqlite:///{path / 'w.db'}")
    async with database.session() as session:
        connection = await session.connection()
        await connection.run_sync(Base.metadata.create_all)
        await session.commit()
    storage = DiskStorage(path / "files")
    filing = Filing(
        database,
        Queue(database, Utc()),
        (storage, Keys(), Workbench(storage, path / "home")),
        Utc(),
    )
    return database, filing


async def opens_folder(tmp_path: Path) -> tuple[list[str], str, bool, bool]:
    database, filing = await prepare(tmp_path)
    owner = word()
    number = await filing.open(owner, "Иванов", "Пример", folder())
    async with database.session() as session:
        row = await session.get(Workspace, number)
    stored = DiskStorage(tmp_path / "files").exists(f"{owner}/{number}/folder/{_FIRST}")
    await database.close()
    assert row is not None
    return list(row.found), row.owner_name, stored, row.owner == owner and bool(row.package_sha)


def test_opens_the_folder_and_lists_its_declarations_under_the_owner(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(opens_folder(tmp_path), 60)),
        equal_to(([_FIRST, _SECOND], "Иванов", True, True)),
        "Opened folder is not stored under the owner with its declarations listed",
    )


async def starts_chosen_declarations(
    tmp_path: Path,
) -> tuple[list[tuple[str, str, str]], list[str]]:
    database, filing = await prepare(tmp_path)
    owner = word()
    number = await filing.open(owner, "Иванов", "Пример", folder())
    await filing.start(owner, number, (_SECOND,))
    async with database.session() as session:
        declarations = (await session.scalars(select(Declaration))).all()
        jobs = (await session.scalars(select(Job).order_by(Job.id))).all()
        found = [(each.owner, each.file_name, each.file_key) for each in declarations]
        kinds = [f"{each.kind}:{each.uploaded_by}" for each in jobs]
    await database.close()
    return found, kinds


def test_starts_a_job_for_each_chosen_declaration_and_one_for_the_profile(tmp_path: Path) -> None:
    found, kinds = asyncio.run(asyncio.wait_for(starts_chosen_declarations(tmp_path), 60))
    assert_that(
        (len(found), found[0][1], found[0][2].endswith(f"/folder/{_SECOND}"), kinds),
        equal_to((1, "511.xlsx", True, ["profile_build:Иванов", "reconcile:Иванов"])),
        "Start does not queue the build of the profile and one job per chosen declaration",
    )


async def starts_twice(tmp_path: Path, *, same: bool, built: str) -> tuple[int, int]:
    database, filing = await prepare(tmp_path)
    owner = word()
    first = await filing.open(owner, "A", "Пример", folder())
    await filing.start(owner, first, (_FIRST,))
    async with database.session() as session:
        policy = (await session.scalars(select(Policy))).one()
        if built == "profile":
            session.add(PolicyProfile(policy_id=policy.id, version=1, body={}, status="draft"))
        if built == "failed":
            job = await session.get(Job, policy.job_id)
            assert job is not None
            job.status = "failed"
        await session.commit()
    second = await filing.open(owner, "A", "Пример", folder() if same else folder(b"changed"))
    await filing.start(owner, second, (_FIRST,))
    async with database.session() as session:
        policies = len((await session.scalars(select(Policy))).all())
        builds = len((await session.scalars(select(Job).where(Job.kind == "profile_build"))).all())
    await database.close()
    return policies, builds


def test_takes_the_policy_of_the_same_files_and_builds_nothing_when_it_has_a_profile(
    tmp_path: Path,
) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(starts_twice(tmp_path, same=True, built="profile"), 60)),
        equal_to((1, 1)),
        "Same files of the same owner do not share one policy and its profile",
    )


def test_does_not_queue_a_second_build_while_the_first_one_goes(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(starts_twice(tmp_path, same=True, built="none"), 60)),
        equal_to((1, 1)),
        "A second session queues another build of the profile that is already being built",
    )


def test_builds_the_profile_again_after_a_failed_build(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(starts_twice(tmp_path, same=True, built="failed"), 60)),
        equal_to((1, 2)),
        "A failed build of the profile is not repeated by the next session",
    )


def test_makes_another_policy_for_changed_files(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(starts_twice(tmp_path, same=False, built="profile"), 60)),
        equal_to((2, 2)),
        "Changed files of a policy do not make a new policy",
    )


async def keeps_policies_of_two_owners_apart(tmp_path: Path) -> int:
    database, filing = await prepare(tmp_path)
    for owner in (word(), word()):
        number = await filing.open(owner, "A", "Пример", folder())
        await filing.start(owner, number, (_FIRST,))
    async with database.session() as session:
        found = len((await session.scalars(select(Policy))).all())
    await database.close()
    return found


def test_keeps_policies_of_two_owners_apart_for_the_same_files(tmp_path: Path) -> None:
    assert_that(
        asyncio.run(asyncio.wait_for(keeps_policies_of_two_owners_apart(tmp_path), 60)),
        equal_to(2),
        "One owner shares a policy with another owner",
    )


async def starts_as(tmp_path: Path, who: str, chosen: tuple[str, ...], times: int) -> None:
    database, filing = await prepare(tmp_path)
    number = await filing.open("owner", "A", "Пример", folder())
    try:
        for _ in range(times):
            await filing.start(who, number, chosen)
    finally:
        await database.close()


def test_refuses_to_start_the_session_of_another_owner(tmp_path: Path) -> None:
    assert_that(
        lambda: asyncio.run(asyncio.wait_for(starts_as(tmp_path, "intruder", (_FIRST,), 1), 60)),
        raises(MissingWorkspaceError),
        "Session of another owner is started",
    )


def test_refuses_an_empty_choice(tmp_path: Path) -> None:
    assert_that(
        lambda: asyncio.run(asyncio.wait_for(starts_as(tmp_path, "owner", (), 1), 60)),
        raises(ChoiceError),
        "Empty choice of declarations is started",
    )


def test_refuses_a_file_that_is_not_among_found_declarations(tmp_path: Path) -> None:
    assert_that(
        lambda: asyncio.run(asyncio.wait_for(starts_as(tmp_path, "owner", ("ГП.docx",), 1), 60)),
        raises(ChoiceError),
        "A file that is not a declaration of the folder is started",
    )


def test_refuses_to_start_a_session_twice(tmp_path: Path) -> None:
    assert_that(
        lambda: asyncio.run(asyncio.wait_for(starts_as(tmp_path, "owner", (_FIRST,), 2), 60)),
        raises(ChoiceError),
        "Session is started twice",
    )
