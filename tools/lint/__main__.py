import sys
from pathlib import Path

from tools.lint.angry import Angry
from tools.lint.density import Density
from tools.lint.finality import Attributes, Finality, Statics
from tools.lint.interfaces import Declared, Interfaces
from tools.lint.naming import Names
from tools.lint.pairing import Pairing
from tools.lint.purity import Purity
from tools.lint.remarks import Remarks
from tools.lint.scope import Scoped
from tools.lint.script import Code


def main() -> int:
    root = Path.cwd()
    scripts = tuple(
        Code(path.relative_to(root).as_posix(), path.read_text(encoding="utf-8"))
        for folder in ("app", "tools", "tests", "migrations")
        for path in sorted((root / folder).rglob("*.py"))
    )
    boundary = ("app/jobs/*", "app/web/*", "migrations/*", "*/schema/*")
    production = ("app/*", "tools/*")
    rules = (
        Scoped(Remarks(r"# @todo #\d+:\d+(min|h) \S.*"), ("*",), ()),
        Scoped(Density(), ("*",), ()),
        Scoped(Finality(), production, boundary),
        Scoped(Statics(), production, boundary),
        Scoped(Attributes(4), production, boundary),
        Scoped(Interfaces(Declared(scripts)), production, boundary),
        Scoped(
            Names(
                r"(?:Analy[sz]|Build|Calculat|Check|Collect|Compar|Controll|Convert|Creat|Detect"
                r"|Dispatch|Evaluat|Execut|Export|Extract|Fetch|Format|Generat|Handl|Help|Import"
                r"|Listen|Load|Manag|Mapp|Match|Normaliz|Pars|Print|Process|Provid|Read|Render"
                r"|Resolv|Runn|Schedul|Select|Send|Serializ|Splitt|Upload|Validat|Work|Writ)"
                r"(?:er|or)$"
            ),
            production,
            (),
        ),
        Scoped(
            Purity(
                frozenset(
                    {"isinstance", "issubclass", "type", "getattr", "setattr", "hasattr", "vars"}
                    | {"delattr", "cast"}
                )
            ),
            ("app/*",),
            boundary,
        ),
        Scoped(
            Angry(
                r"\b(not|no|never|cannot|dont|doesnt|isnt|arent|wasnt|nothing|не|нет|без)\b",
                frozenset({"tmp_path"}),
            ),
            ("tests/*test_*.py",),
            (),
        ),
        Scoped(Pairing(frozenset(script.path() for script in scripts)), ("tests/*test_*.py",), ()),
    )
    problems = tuple(
        problem for script in scripts for rule in rules for problem in rule.violations(script)
    )
    sys.stdout.buffer.write("".join(f"{problem}\n" for problem in problems).encode())
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
