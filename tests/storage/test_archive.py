import io
import struct
import zipfile
import zlib

from hamcrest import assert_that, contains_inanyorder, equal_to, raises

from app.storage.archive import Unzipped
from app.storage.errors import BrokenError, EscapeError


def packed(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def names(data: bytes) -> list[str]:
    return [file.name() for file in Unzipped(data).files()]


def test_keeps_unicode_names_without_recoding() -> None:
    assert_that(
        names(packed({"ДС/Файл один.doc": b"x"})),
        equal_to(["ДС/Файл один.doc"]),
        "Unzipped does not keep a Unicode name unchanged",
    )


def test_reads_cp866_names_of_entries_without_utf8_flag() -> None:
    placeholder = "AAAAAAAA"
    data = packed({placeholder: b"x"}).replace(
        placeholder.encode(), "Полис".encode("cp866").ljust(8, b"_")
    )
    assert_that(
        names(data),
        equal_to(["Полис___"]),
        "Unzipped does not read cp866 names",
    )


def test_keeps_name_from_unicode_path_field_without_utf8_flag() -> None:
    raw = b"AAAAAA"
    field = struct.pack("<BI", 1, zlib.crc32(raw)) + "Файл".encode()
    info = zipfile.ZipInfo("AAAAAA")
    info.extra = struct.pack("<HH", 0x7075, len(field)) + field
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(info, b"x")
    assert_that(
        names(buffer.getvalue()),
        equal_to(["Файл"]),
        "Unzipped does not keep the name from the Unicode path field",
    )


def test_refuses_entry_that_leads_out_of_the_folder() -> None:
    assert_that(
        lambda: Unzipped(packed({"../evil.doc": b"x"})).files(),
        raises(EscapeError),
        "Unzipped does not refuse a path with a parent segment",
    )


def test_drops_service_entries() -> None:
    assert_that(
        names(
            packed({"__MACOSX/._a.doc": b"x", "a.doc": b"x", "Thumbs.db": b"x", "~$a.doc": b"x"})
        ),
        contains_inanyorder("a.doc"),
        "Unzipped does not drop service files",
    )


def test_refuses_data_that_is_not_an_archive() -> None:
    assert_that(
        lambda: Unzipped(b"not a zip").files(),
        raises(BrokenError),
        "Unzipped does not refuse a broken archive",
    )
