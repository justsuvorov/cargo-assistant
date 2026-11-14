from typing import Final, final

from tools.lint.script import Script


@final
class Pairing:
    """Rule that every test file mirrors one production module.

    Tests of tests/deploy check release files and need no module.
    """

    __slots__ = ("_paths",)

    def __init__(self, paths: frozenset[str]) -> None:
        self._paths: Final = paths

    def violations(self, script: Script) -> tuple[str, ...]:
        if script.path().startswith("tests/deploy/"):
            return ()
        folder, _, name = script.path().removeprefix("tests/").rpartition("/")
        module = "/".join(filter(None, (folder, name.removeprefix("test_"))))
        if {f"app/{module}", module} & self._paths:
            return ()
        return (script.mark(1, f"Нет модуля app/{module} или {module} для этого теста"),)
