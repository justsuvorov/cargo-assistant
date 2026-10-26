import random
import string
from pathlib import Path

from hamcrest import assert_that, raises

from app.domain.errors import UnreadableError
from app.ingest.doc import Doc


def test_refuses_doc_when_libreoffice_is_missing(tmp_path: Path) -> None:
    (tmp_path / "a.doc").write_bytes(b"x")
    missing = "".join(random.choices(string.ascii_lowercase, k=16))
    assert_that(
        lambda: Doc(tmp_path / "a.doc", missing).sheets(),
        raises(UnreadableError, "LibreOffice не установлен"),
        "Doc does not refuse a file when LibreOffice is missing",
    )
