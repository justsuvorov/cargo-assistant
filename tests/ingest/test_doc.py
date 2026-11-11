import hashlib
import os
import random
import shutil
import string
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from pathlib import Path

import pytest
from docx import Document
from hamcrest import assert_that, contains_string, equal_to, raises

from app.domain.errors import UnreadableError
from app.ingest.book import Sheet
from app.ingest.doc import Conversions, Doc, Profiles


def text(sheets: tuple[Sheet, ...]) -> str:
    return " ".join(
        cell.text() for sheet in sheets for line in sheet.lines() for cell in line.cells()
    )


def test_refuses_doc_when_libreoffice_is_missing(tmp_path: Path) -> None:
    (tmp_path / "a.doc").write_bytes(b"x")
    missing = "".join(random.choices(string.ascii_lowercase, k=16))
    assert_that(
        lambda: Doc(tmp_path / "a.doc", missing, tmp_path / "home").sheets(),
        raises(UnreadableError, "LibreOffice не установлен"),
        "Doc does not refuse a file when LibreOffice is missing",
    )


def test_reads_converted_file_from_cache_without_libreoffice(tmp_path: Path) -> None:
    marker = f"Пункт {random.randint(1, 999)}"
    source = tmp_path / "a.doc"
    source.write_bytes(random.randbytes(64))
    cache = tmp_path / "home" / "cache"
    cache.mkdir(parents=True)
    document = Document()
    document.add_paragraph(marker)
    document.save(str(cache / f"{hashlib.sha256(source.read_bytes()).hexdigest()}.docx"))
    sheets = Doc(source, "missing-soffice", tmp_path / "home").sheets()
    assert_that(
        text(sheets),
        contains_string(marker),
        "Doc does not read a document that was converted before",
    )


def hold(profiles: Profiles, seen: list[Path], inside: threading.Barrier) -> None:
    with profiles.lease() as profile:
        seen.append(profile)
        inside.wait()


def test_hands_out_different_profiles_to_parallel_leases(tmp_path: Path) -> None:
    profiles = Profiles(tmp_path, 2)
    seen: list[Path] = []
    inside = threading.Barrier(2, timeout=5)
    with ThreadPoolExecutor(2) as pool:
        for future in [
            pool.submit(hold, profiles, seen, inside),
            pool.submit(hold, profiles, seen, inside),
        ]:
            future.result(timeout=10)
    assert_that(
        len(set(seen)),
        equal_to(2),
        "Parallel leases do not get different profiles",
    )


def test_frees_profile_after_lease(tmp_path: Path) -> None:
    profiles = Profiles(tmp_path, 1)
    with profiles.lease() as first:
        pass
    with profiles.lease() as second:
        pass
    assert_that(first, equal_to(second), "Profile is not free again after its lease ended")


def contend(profiles: Profiles, busy: dict[Path, int], clashes: list[Path]) -> None:
    for _ in range(25):
        with profiles.lease() as profile:
            busy[profile] = busy.get(profile, 0) + 1
            if busy[profile] > 1:
                clashes.append(profile)
            time.sleep(0.001)
            busy[profile] -= 1


def test_never_hands_one_profile_to_two_leases_at_once(tmp_path: Path) -> None:
    profiles = Profiles(tmp_path, 2)
    busy: dict[Path, int] = {}
    clashes: list[Path] = []
    with ThreadPoolExecutor(6) as pool:
        for future in [pool.submit(contend, profiles, busy, clashes) for _ in range(6)]:
            future.result(timeout=30)
    assert_that(clashes, equal_to([]), "One profile is not kept apart for a single lease at a time")


def test_takes_over_stale_lock_of_dead_process(tmp_path: Path) -> None:
    lock = tmp_path / "lock-0"
    lock.mkdir()
    old = time.time() - 3600
    os.utime(lock, (old, old))
    with Profiles(tmp_path, 1).lease() as profile:
        taken = profile
    assert_that(taken, equal_to(tmp_path / "profile-0"), "Stale lock is not taken over")


def make_docs(folder: Path, *names: str) -> list[Path]:
    sources = []
    for name in names:
        document = Document()
        for line in range(20):
            document.add_paragraph(f"Вымышленный пункт {name}.{line}")
        sources.append(folder / f"{name}.docx")
        document.save(str(sources[-1]))
    program = shutil.which("soffice")
    assert program
    subprocess.run(
        [
            program,
            f"-env:UserInstallation={(folder / 'p').as_uri()}",
            "--headless",
            "--convert-to",
            "doc",
            "--outdir",
            str(folder),
            *map(str, sources),
        ],
        check=True,
        capture_output=True,
        timeout=250,
    )
    return [folder / f"{name}.doc" for name in names]


@pytest.mark.soffice
@pytest.mark.timeout(300)
@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice is not installed")
def test_converts_two_documents_in_parallel_on_own_profiles(tmp_path: Path) -> None:
    docs = make_docs(tmp_path, "one", "two")
    with ThreadPoolExecutor(2) as pool:
        texts = list(
            pool.map(lambda path: text(Doc(path, "soffice", tmp_path / "h").sheets()), docs)
        )
    assert_that(
        [("one" in texts[0]), ("two" in texts[1])],
        equal_to([True, True]),
        "Parallel conversions do not both read their documents",
    )


@pytest.mark.timeout(300)
@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice is not installed")
def test_refuses_file_that_is_not_a_word_document(tmp_path: Path) -> None:
    (tmp_path / "a.doc").write_bytes(b"plain text")
    assert_that(
        lambda: Doc(tmp_path / "a.doc", "soffice", tmp_path / "h").sheets(),
        raises(UnreadableError, "не является документом Word"),
        "Doc does not refuse a file that is not a Word document",
    )


def fake_soffice(folder: Path, code: int, marker: str) -> str:
    lines = [
        "import pathlib, sys",
        "from docx import Document",
        "args = sys.argv[1:]",
        "out = pathlib.Path(args[args.index('--outdir') + 1])",
        "pathlib.Path(__file__).with_name('calls').open('a').write(str(out) + chr(10))",
        "source = pathlib.Path(args[-1])",
        f"if {code} == 0:",
        "    document = Document()",
        f"    document.add_paragraph({marker!r})",
        "    document.save(str(out / (source.stem + '.docx')))",
        f"sys.exit({code})",
    ]
    script = folder / "fake.py"
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if sys.platform == "win32":
        launcher = folder / "fake.cmd"
        launcher.write_text(f'@"{sys.executable}" "{script}" %*\n', encoding="utf-8")
    else:
        launcher = folder / "fake.sh"
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
        launcher.chmod(0o755)
    return str(launcher)


def source_doc(folder: Path) -> Path:
    path = folder / "a.doc"
    path.write_bytes(bytes.fromhex("D0CF11E0A1B11AE1") + random.randbytes(32))
    return path


def test_leaves_no_files_after_failed_conversion(tmp_path: Path) -> None:
    with suppress(UnreadableError):
        Doc(source_doc(tmp_path), fake_soffice(tmp_path, 1, "x"), tmp_path / "home").sheets()
    assert_that(
        [path.name for path in (tmp_path / "home").rglob("*") if path.suffix in {".part", ".docx"}]
        + [path.name for path in (tmp_path / "home" / "work").iterdir()],
        equal_to([]),
        "Doc does not remove the temporary files of a failed conversion",
    )


def test_converts_in_the_work_folder_of_the_home(tmp_path: Path) -> None:
    marker = f"Пункт {random.randint(1, 999)}"
    sheets = Doc(
        source_doc(tmp_path), fake_soffice(tmp_path, 0, marker), tmp_path / "home"
    ).sheets()
    folder = Path((tmp_path / "calls").read_text().strip())
    assert_that(
        (folder.parent, marker in text(sheets)),
        equal_to((tmp_path / "home" / "work", True)),
        "Doc does not convert in the work folder of its home",
    )


def test_converts_the_same_document_once(tmp_path: Path) -> None:
    command = fake_soffice(tmp_path, 0, "x")
    source = source_doc(tmp_path)
    Doc(source, command, tmp_path / "home").sheets()
    Doc(source, command, tmp_path / "home").sheets()
    assert_that(
        len((tmp_path / "calls").read_text().splitlines()),
        equal_to(1),
        "Doc does not use the cache and converts a document again",
    )


def aged(path: Path, seconds: float, now: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    os.utime(path, (now - seconds, now - seconds))
    return path


def test_sweeps_converted_files_older_than_the_edge_only(tmp_path: Path) -> None:
    now = time.time()
    cache = tmp_path / "cache"
    old = aged(cache / "old.docx", 7 * 86400 + 1, now)
    edge = aged(cache / "edge.docx", 7 * 86400, now)
    new = aged(cache / "new.docx", 7 * 86400 - 1, now)
    Conversions(tmp_path).sweep(now - 7 * 86400)
    assert_that(
        (old.exists(), edge.exists(), new.exists()),
        equal_to((False, True, True)),
        "Conversions do not remove exactly the files older than the edge",
    )


def test_sweeps_leftover_parts_and_work_folders(tmp_path: Path) -> None:
    now = time.time()
    part = aged(tmp_path / "cache" / "a.docx.1.2.part", 100, now)
    leftover = aged(tmp_path / "work" / "tmp1" / "a.docx", 100, now)
    os.utime(leftover.parent, (now - 100, now - 100))
    count = Conversions(tmp_path).sweep(now - 10)
    assert_that(
        (part.exists(), leftover.parent.exists(), count),
        equal_to((False, False, 2)),
        "Conversions do not remove stale parts and work folders",
    )


def test_sweeps_idle_profiles_and_keeps_leased_one(tmp_path: Path) -> None:
    profiles = Profiles(tmp_path / "profiles", 2)
    with profiles.lease() as busy:
        busy.mkdir()
        idle = tmp_path / "profiles" / "profile-1"
        (idle / "user").mkdir(parents=True)
        Conversions(tmp_path).sweep(0)
        kept = (busy.exists(), idle.exists())
    assert_that(kept, equal_to((True, False)), "Conversions do not clear only the idle profiles")
