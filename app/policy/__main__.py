import argparse
import logging
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from app.core.journal import LogJournal
from app.core.schema.environment import Environment
from app.domain.errors import UnreadableError
from app.llm.assembly import Configured
from app.llm.errors import MisconfiguredError
from app.llm.ledger import Memory
from app.llm.model import Model
from app.policy.directory import Directory
from app.policy.extraction import Extraction


def build(folder: Path, model: Model, out: Path, report: TextIO) -> int:
    started = time.perf_counter()
    try:
        package = Directory(folder).package()
    except UnreadableError as error:
        report.write(f"{error}\n")
        return 1
    read = time.perf_counter()
    profile = Extraction(package, model).profile()
    done = time.perf_counter()
    text = profile.model_dump_json(indent=2)
    if out.name:
        out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.buffer.write(f"{text}\n".encode())
    report.write(f"Чтение пакета заняло {read - started:.1f} с, извлечение {done - read:.1f} с\n")
    report.write(f"Проблем: {len(profile.problems)}\n")
    for problem in profile.problems:
        report.write(f"  - {problem}\n")
    return 0


def main(arguments: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.policy",
        description="Черновик профиля полиса из папки; модель берётся из настроек LLM_*",
    )
    parser.add_argument("command", choices=("build",), help="build — собрать черновик профиля")
    parser.add_argument("folder", type=Path, help="папка полиса: ГП в корне, ДС в папке «ДС»")
    parser.add_argument("--out", type=Path, default=Path(), help="файл для черновика (JSON)")
    parser.add_argument("--env", default=".env", help="файл с переменными окружения")
    given = parser.parse_args(list(arguments) if arguments else sys.argv[1:])
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        model = Configured(
            Environment(given.env), LogJournal(logging.getLogger("policy")), Memory()
        ).model()
    except MisconfiguredError as error:
        sys.stderr.write(f"{error}\n")
        return 2
    return build(given.folder, model, given.out, sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
