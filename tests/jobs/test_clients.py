import random
import string
from pathlib import Path

from hamcrest import assert_that, equal_to

from app.jobs.clients import Clients


def word() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=8))


def describe(found: Clients) -> tuple[str, bool, tuple[str, ...], tuple[str, ...]]:
    return found.file(), found.chosen(), found.lines(), found.problems()


def text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_takes_the_file_of_the_conditions_folder(tmp_path: Path) -> None:
    folder, chosen = tmp_path / "f", tmp_path / "c"
    chosen.mkdir()
    one = word()
    text(folder / "Особые условия" / "u.txt", f"{one}\n")
    assert_that(
        describe(Clients(folder, chosen)),
        equal_to(("Особые условия/u.txt", False, (one,), ())),
        "Clients does not take the file of the folder of special conditions",
    )


def test_replaces_the_file_of_the_folder_by_the_chosen_one(tmp_path: Path) -> None:
    folder, chosen = tmp_path / "f", tmp_path / "c"
    one = word()
    text(folder / "Особые условия" / "u.txt", "старое\n")
    text(chosen / "новое.txt", f"{one}\n")
    assert_that(
        describe(Clients(folder, chosen)),
        equal_to(("новое.txt", True, (one,), ())),
        "Clients does not replace the file of the folder by the chosen one",
    )


def test_tells_that_there_is_no_file_at_all(tmp_path: Path) -> None:
    folder, chosen = tmp_path / "f", tmp_path / "c"
    folder.mkdir()
    chosen.mkdir()
    assert_that(
        describe(Clients(folder, chosen)),
        equal_to(("", False, (), ())),
        "Clients does not tell that no file of special conditions was given",
    )


def test_names_an_unreadable_chosen_file_as_a_problem(tmp_path: Path) -> None:
    folder, chosen = tmp_path / "f", tmp_path / "c"
    folder.mkdir()
    text(chosen / "пустой.txt", "")
    found = Clients(folder, chosen)
    assert_that(
        (found.lines(), len(found.problems())),
        equal_to(((), 1)),
        "Clients does not name an empty chosen file as a problem",
    )
