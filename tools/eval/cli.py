import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import yaml

from app.domain.status import Match, Review, Status
from tools.eval.draft import Draft
from tools.eval.fields import Cards, Deck
from tools.eval.gold import Folder
from tools.eval.mask import Anonymity
from tools.eval.paper import Cases, Questions, Summary
from tools.eval.pipeline import Uniform
from tools.eval.report import Report
from tools.eval.rulings import Rulings
from tools.eval.session import Session
from tools.eval.sheet import Workbooks


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tools.eval", description="Эталон и прогон eval cargo-assistant"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="прогнать конвейер по эталону и вывести отчёт")
    run.add_argument("--gold", type=Path, default=Path("tests/gold/cases"))
    run.add_argument("--pipeline", choices=("stub", "match"), default="stub")
    run.add_argument("--out", type=Path, default=Path("-"))
    gold = commands.add_parser("gold", help="собрать черновой эталон из разметки ФСЦ")
    gold.add_argument("--source", type=Path, required=True)
    gold.add_argument("--cards", type=Path, default=Path("cards"))
    gold.add_argument("--settings", type=Path, default=Path("tests/gold/rulings.yaml"))
    gold.add_argument("--glossary", type=Path, default=Path("data/real/glossary.txt"))
    gold.add_argument("--out", type=Path, default=Path("tests/gold/cases"))
    gold.add_argument("--questions", type=Path, default=Path("docs/eval/questions.md"))
    gold.add_argument("--summary", type=Path, default=Path("docs/eval/summary.md"))
    mask = commands.add_parser("mask", help="обезличить текстовый файл в UTF-8")
    mask.add_argument("source", type=Path)
    mask.add_argument("target", type=Path)
    mask.add_argument("--glossary", type=Path, default=Path("data/real/glossary.txt"))
    args = parser.parse_args(argv)
    commands_by_name = {"run": _run, "gold": _gold, "mask": _mask}
    return commands_by_name[args.command](args)


def _run(args: argparse.Namespace) -> int:
    # @todo #3:30min Подключить reconcile через Pipeline после T-02 и профиля, вызовы — из LLMCall
    gold = Folder(args.gold)
    stubs: dict[str, tuple[str, Status]] = {
        "stub": ("пустой конвейер (все места эталона — «требует проверки»)", Review()),
        "match": ("контрольная заглушка (все места эталона — «совпадает»)", Match()),
    }
    title, status = stubs[args.pipeline]
    _emit(args.out, Report(title, gold, Session(gold, Uniform(gold, status)).laps()).text())
    return 0


def _gold(args: argparse.Namespace) -> int:
    settings = yaml.safe_load(args.settings.read_text(encoding="utf-8"))
    entries = Draft(
        Workbooks(args.source, tuple(settings["forms"])),
        Cards(Deck(args.cards).titles(), settings),
        Rulings(settings.get("rulings", ()), settings.get("broken", {})),
    ).entries()
    mask = Anonymity(
        (cell for entry in entries for cell in entry.cells()), _glossary(args.glossary)
    )
    Cases(args.out, mask).write(entries)
    Questions(args.questions, mask).write(entries)
    Summary(args.summary).write(entries)
    kinds = [entry.kind() for entry in entries]
    _emit(
        Path("-"),
        f"Строк MVP: {len(entries)}; в эталоне: {kinds.count('gold')}; "
        f"в вопросах: {kinds.count('question')}; исключено: {kinds.count('excluded')}\n",
    )
    return 0


def _mask(args: argparse.Namespace) -> int:
    text = args.source.read_text(encoding="utf-8")
    args.target.write_text(
        Anonymity(text.splitlines(), _glossary(args.glossary)).hide(text), encoding="utf-8"
    )
    return 0


def _glossary(path: Path) -> tuple[str, ...]:
    return tuple(path.read_text(encoding="utf-8").splitlines()) if path.exists() else ()


def _emit(path: Path, text: str) -> None:
    if str(path) == "-":
        sys.stdout.buffer.write(text.encode("utf-8"))
        sys.stdout.buffer.flush()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
