import argparse
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import yaml

from app.declarations.declared import Declared
from app.domain.errors import UnreadableError
from app.domain.status import Match, Review
from app.ingest.source import Source
from tools.eval.draft import Draft
from tools.eval.fields import Cards, Deck
from tools.eval.gold import Folder, Gold, Held
from tools.eval.manifest import Manifest, Part, Split
from tools.eval.marking import Additions, Markings
from tools.eval.mask import Anonymity
from tools.eval.paper import Cases, Questions, Summary
from tools.eval.pipeline import Parsed, Pipeline, Uniform
from tools.eval.report import Report
from tools.eval.rulings import Rulings
from tools.eval.session import Session
from tools.eval.sheet import Workbooks
from tools.eval.shelf import Shelf
from tools.eval.template import Template

type Command = Callable[[argparse.Namespace], int]

_PARTS = {"dev": ("dev",), "holdout": ("holdout",), "all": ("dev", "holdout")}


def main(argv: Sequence[str]) -> int:
    args = _parser().parse_args(argv)
    commands: dict[str, Command] = {
        "run": _run,
        "template": _template,
        "load": _load,
        "split": _split,
        "gold": _gold,
        "mask": _mask,
    }
    try:
        return commands[args.command](args)
    except (OSError, LookupError, ValueError, UnreadableError) as error:
        sys.stderr.buffer.write(f"Ошибка: {error}\n".encode())
        sys.stderr.buffer.flush()
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.eval", description="Эталон и прогон eval cargo-assistant"
    )
    real = Path(os.environ.get("EVAL_REAL_DIR", "data/real"))
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="прогнать конвейер по эталону и вывести отчёт")
    run.add_argument("--gold", type=Path, default=Path("tests/gold/cases"))
    run.add_argument("--manifest", type=Path, default=Path("tests/gold/manifest.yaml"))
    run.add_argument("--part", choices=tuple(_PARTS), default="dev")
    run.add_argument("--pipeline", choices=("stub", "match", "parsed"), default="stub")
    run.add_argument("--real", type=Path, default=real)
    run.add_argument("--cards", type=Path, default=Path("cards"))
    run.add_argument("--out", type=Path, default=Path("-"))
    template = commands.add_parser("template", help="создать шаблон разметки по декларации")
    template.add_argument("declaration", type=Path)
    template.add_argument("--out", type=Path, default=Path())
    template.add_argument("--cards", type=Path, default=Path("cards"))
    load = commands.add_parser("load", help="проверить шаблоны разметки и записать эталон")
    load.add_argument("source", type=Path)
    load.add_argument("--gold", type=Path, default=Path("tests/gold/cases"))
    load.add_argument("--cards", type=Path, default=Path("cards"))
    load.add_argument("--glossary", type=Path, default=Path("data/real/glossary.txt"))
    split = commands.add_parser("split", help="разделить декларации эталона на dev и holdout")
    split.add_argument("--gold", type=Path, default=Path("tests/gold/cases"))
    split.add_argument("--manifest", type=Path, default=Path("tests/gold/manifest.yaml"))
    split.add_argument("--real", type=Path, default=real)
    split.add_argument("--share", type=float, default=0.3)
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
    return parser


def _run(args: argparse.Namespace) -> int:
    manifest = Manifest(args.manifest)
    gold = Held(Part(Folder(args.gold), manifest, frozenset(_PARTS[args.part])).samples())
    if not gold.samples():
        raise ValueError(f"В части {args.part} эталона {args.gold} нет ни одной строки")
    title, pipeline = _pipeline(args, gold)
    _emit(
        args.out,
        Report(
            title,
            f"версия {manifest.version()}, часть {args.part}",
            gold,
            Session(gold, pipeline).laps(),
        ).text(),
    )
    return 0


def _pipeline(args: argparse.Namespace, gold: Gold) -> tuple[str, Pipeline]:
    if args.pipeline == "parsed":
        return (
            "разбор деклараций app.declarations с заглушкой проверок (везде «требует проверки»)",
            Parsed(Shelf(args.real).catalog(), Deck(args.cards)),
        )
    stubs = {
        "stub": (
            "пустой конвейер (все места эталона — «требует проверки»)",
            Uniform(gold, Review()),
        ),
        "match": ("контрольная заглушка (все места эталона — «совпадает»)", Uniform(gold, Match())),
    }
    return stubs[args.pipeline]


def _template(args: argparse.Namespace) -> int:
    declaration = Declared(Source(args.declaration))
    target = args.out / f"{declaration.number()} – разметка.xlsx"
    Template(declaration, Deck(args.cards)).write(target)
    _emit(Path("-"), f"Шаблон разметки: {target}\n")
    return 0


def _load(args: argparse.Namespace) -> int:
    batch = Markings(
        args.source,
        {
            " ".join(title.split()): key
            for key, forms in Deck(args.cards).titles().items()
            for title in forms.values()
        },
    )
    problems = batch.problems()
    if problems:
        _emit(
            Path("-"),
            "".join(
                (
                    f"Ошибок разметки: {len(problems)}; эталон не записан\n",
                    *(f"{p}\n" for p in problems),
                )
            ),
        )
        return 1
    answers = batch.answers()
    Additions(
        args.gold,
        Anonymity(
            (cell for answer in answers for cell in answer.cells()), _glossary(args.glossary)
        ),
    ).write(answers)
    _emit(
        Path("-"),
        f"Строк разметки: {len(answers)}; спорных: {sum(1 for a in answers if not a.sure())}; "
        f"записаны декларации: {', '.join(dict.fromkeys(a.declaration() for a in answers))}\n",
    )
    return 0


def _split(args: argparse.Namespace) -> int:
    catalog = Shelf(args.real).catalog()
    policies = {
        declaration: Declared(Source(catalog.path(declaration))).policy()
        for declaration in dict.fromkeys(s.declaration() for s in Folder(args.gold).samples())
    }
    data = yaml.safe_load(args.manifest.read_text(encoding="utf-8"))
    entries = Split(data.get("declarations") or {}, policies, args.share).entries()
    args.manifest.write_text(
        yaml.safe_dump(
            {**data, "declarations": entries}, allow_unicode=True, sort_keys=False, width=100
        ),
        encoding="utf-8",
    )
    parts = [entry["part"] for entry in entries.values()]
    _emit(
        Path("-"),
        f"Деклараций: {len(parts)}; dev: {parts.count('dev')}; holdout: {parts.count('holdout')}; "
        f"полисов: {len({entry['policy'] for entry in entries.values()})}\n",
    )
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
