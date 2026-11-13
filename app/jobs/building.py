import asyncio
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from pathlib import Path
from typing import Final, Protocol, final

from app.core.journal import Journal
from app.domain.errors import UnreadableError
from app.ingest.doc import Doc
from app.jobs.folios import Folio
from app.jobs.packages import Packages
from app.jobs.queue import Snapshot
from app.llm.model import Model
from app.policy.directory import Directory
from app.policy.extraction import Extraction
from app.policy.package import Package
from app.policy.schema.profile import Profile
from app.storage.disk import Storage
from app.storage.layout import Layout

_CONVERSIONS = 4


class Models(Protocol):
    """Source of the language model for a job, asked only when a stage really needs it."""

    def model(self, job_id: int) -> Model: ...


class Cell[T](Protocol):
    """Place where one stage of a job leaves a result for the next stage."""

    def put(self, value: T) -> None: ...

    def get(self) -> T: ...


@final
class Shelf[T]:
    """Cell of a single job; reading it before any stage filled it is an error."""

    __slots__ = ("_items",)

    def __init__(self) -> None:
        self._items: Final[list[T]] = []

    def put(self, value: T) -> None:
        self._items.append(value)

    def get(self) -> T:
        if not self._items:
            raise LookupError("Предыдущая стадия не оставила результата")
        return self._items[-1]


class Bench(Protocol):
    """Place where a package is unpacked, a declaration is copied and doc files are converted,
    kept in one folder; the folder of a copied declaration is the parent of the returned path."""

    def unpack(self, prefix: str) -> Path: ...

    def copy(self, key: str) -> Path: ...

    def scratch(self) -> Path: ...

    def warm(self, path: Path) -> None: ...


@final
class Workbench:
    """Bench in a folder of the service, never in the system temporary folder, so the texts of
    the customer are kept in one place that is cleaned on a schedule."""

    __slots__ = ("_home", "_storage")

    def __init__(self, storage: Storage, home: Path) -> None:
        self._storage: Final = storage
        self._home: Final = home

    def unpack(self, prefix: str) -> Path:
        work = self._home / "work"
        work.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix="package-", dir=work))
        try:
            self._storage.export(prefix, folder)
        except BaseException:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        return folder

    def copy(self, key: str) -> Path:
        work = self._home / "work"
        work.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix="declaration-", dir=work))
        try:
            path = folder / key.rsplit("/", 1)[-1]
            path.write_bytes(self._storage.read(key))
        except BaseException:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        return path

    def scratch(self) -> Path:
        work = self._home / "work"
        work.mkdir(parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix="result-", dir=work))

    def warm(self, path: Path) -> None:
        with suppress(UnreadableError):
            Doc(path, "soffice", self._home).warm()


@final
class Fetching:
    """Stage that copies the files of the package from the storage to a working folder."""

    __slots__ = ("_bench", "_folder", "_layout")

    def __init__(self, bench: Bench, layout: Layout, folder: Cell[Path]) -> None:
        self._bench: Final = bench
        self._layout: Final = layout
        self._folder: Final = folder

    def name(self) -> str:
        return "fetch"

    async def run(self, job: Snapshot) -> None:
        self._folder.put(
            await asyncio.to_thread(
                self._bench.unpack, self._layout.package(int(str(job.payload["policy_id"])))
            )
        )


@final
class Converting:
    """Stage that converts all doc files of the package at once, several in parallel.

    A file that cannot be converted is not an error here: reading names it in the problems.
    """

    __slots__ = ("_bench", "_folder", "_journal")

    def __init__(self, bench: Bench, folder: Cell[Path], journal: Journal) -> None:
        self._bench: Final = bench
        self._folder: Final = folder
        self._journal: Final = journal

    def name(self) -> str:
        return "convert"

    async def run(self, job: Snapshot) -> None:
        count = await asyncio.to_thread(self._convert, self._folder.get())
        self._journal.info(f"Преобразовано файлов doc: {count}", job.id, 0)

    def _convert(self, folder: Path) -> int:
        files = sorted(path for path in folder.rglob("*") if path.suffix.lower() == ".doc")
        with ThreadPoolExecutor(_CONVERSIONS) as pool:
            return len(list(pool.map(self._bench.warm, files)))


@final
class Reading:
    """Stage that reads the working folder into a package and removes the folder."""

    __slots__ = ("_folder", "_journal", "_package")

    def __init__(self, folder: Cell[Path], package: Cell[Package], journal: Journal) -> None:
        self._folder: Final = folder
        self._package: Final = package
        self._journal: Final = journal

    def name(self) -> str:
        return "read"

    async def run(self, job: Snapshot) -> None:
        folder = self._folder.get()
        try:
            package = await asyncio.to_thread(Directory(folder).package)
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        self._package.put(package)
        self._journal.info(
            f"Пакет прочитан: соглашений {len(package.amendments())}, "
            f"замечаний {len(package.problems())}",
            job.id,
            0,
        )


@final
class Extracting:
    """Stage where the model finds the clauses of the package and code checks them."""

    __slots__ = ("_models", "_package", "_profile")

    def __init__(self, models: Models, package: Cell[Package], profile: Cell[Profile]) -> None:
        self._models: Final = models
        self._package: Final = package
        self._profile: Final = profile

    def name(self) -> str:
        return "extract"

    async def run(self, job: Snapshot) -> None:
        model = self._models.model(job.id)
        package = self._package.get()
        self._profile.put(await asyncio.to_thread(Extraction(package, model).profile))


@final
class Saving:
    """Stage that stores the draft as a new profile version and tells the documents apart."""

    __slots__ = ("_folio", "_journal", "_package", "_packages", "_profile")

    def __init__(
        self,
        folio: Folio,
        packages: Packages,
        package: Cell[Package],
        profile: Cell[Profile],
        journal: Journal,
    ) -> None:
        self._folio: Final = folio
        self._packages: Final = packages
        self._package: Final = package
        self._profile: Final = profile
        self._journal: Final = journal

    def name(self) -> str:
        return "save"

    async def run(self, job: Snapshot) -> None:
        policy_id = int(str(job.payload["policy_id"]))
        version = await self._folio.draft(policy_id, self._profile.get())
        await self._packages.classify(policy_id, self._package.get())
        self._journal.info(f"Черновик профиля сохранён версией {version}", job.id, 0)
