import hashlib
import os
import random
import shutil
import string
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from docx import Document
from hamcrest import assert_that, contains_string, equal_to, raises

from app.domain.errors import UnreadableError
from app.ingest.book import Sheet
from app.ingest.doc import Doc, Profiles


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


def test_takes_over_stale_lock_of_dead_process(tmp_path: Path) -> None:
    lock = tmp_path / "lock-0"
    lock.mkdir()
    old = time.time() - 3600
    os.utime(lock, (old, old))
    with Profiles(tmp_path, 1).lease() as profile:
        taken = profile
    assert_that(taken, equal_to(tmp_path / "profile-0"), "Stale lock is not taken over")


def make_doc(folder: Path, name: str) -> Path:
    document = Document()
    for line in range(20):
        document.add_paragraph(f"Вымышленный пункт {name}.{line}")
    source = folder / f"{name}.docx"
    document.save(str(source))
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
            str(source),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    return folder / f"{name}.doc"


@pytest.mark.timeout(120)
@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice is not installed")
def test_converts_two_documents_in_parallel_on_own_profiles(tmp_path: Path) -> None:
    docs = [make_doc(tmp_path, "one"), make_doc(tmp_path, "two")]
    started = time.perf_counter()
    with ThreadPoolExecutor(2) as pool:
        texts = list(
            pool.map(lambda path: text(Doc(path, "soffice", tmp_path / "h").sheets()), docs)
        )
    assert_that(
        [("one" in texts[0]), ("two" in texts[1]), time.perf_counter() - started < 60],
        equal_to([True, True, True]),
        "Parallel conversions do not both read their documents",
    )
