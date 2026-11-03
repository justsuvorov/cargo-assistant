from pathlib import Path

from hamcrest import assert_that, contains_inanyorder, empty

from app.policy.layout import Layout


def _touch(root: Path, *names: str) -> None:
    for name in names:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(b"x")


def _names(root: Path, paths: tuple[Path, ...]) -> list[str]:
    return [path.relative_to(root).as_posix() for path in paths]


def test_takes_policy_files_lying_directly_in_the_policy_folder(tmp_path: Path) -> None:
    _touch(tmp_path, "a.docx", "ДС/1/b.docx")
    assert_that(
        _names(tmp_path, Layout(tmp_path).policies()),
        contains_inanyorder("a.docx"),
        "Layout does not take the files that lie directly in the policy folder",
    )


def test_takes_policy_files_from_subfolder_named_gp(tmp_path: Path) -> None:
    _touch(tmp_path, "ГП/a.docx", "ГП/inner/c.docx", "x.docx")
    assert_that(
        _names(tmp_path, Layout(tmp_path).policies()),
        contains_inanyorder("ГП/a.docx", "ГП/inner/c.docx", "x.docx"),
        "Layout does not take the files of the subfolder named GP",
    )


def test_takes_amendments_from_any_depth_of_the_folder_named_ds(tmp_path: Path) -> None:
    _touch(tmp_path, "ДС/1/a.docx", "ДС/b.doc", "ДС/2/deep/c.docx", "a.docx")
    assert_that(
        _names(tmp_path, Layout(tmp_path).amendments()),
        contains_inanyorder("ДС/1/a.docx", "ДС/b.doc", "ДС/2/deep/c.docx"),
        "Layout does not take the files of the folder of amendments at any depth",
    )


def test_matches_folder_names_in_any_letter_case(tmp_path: Path) -> None:
    _touch(tmp_path, "дс/a.docx", "ОСОБЫЕ УСЛОВИЯ/b.txt", "перевозчики/c.txt")
    layout = Layout(tmp_path)
    assert_that(
        _names(tmp_path, layout.amendments() + layout.conditions() + layout.carriers()),
        contains_inanyorder("дс/a.docx", "ОСОБЫЕ УСЛОВИЯ/b.txt", "перевозчики/c.txt"),
        "Layout does not match the names of folders in any letter case",
    )


def test_skips_service_files(tmp_path: Path) -> None:
    _touch(tmp_path, "ДС/1/Thumbs.db", "ДС/1/~$a.docx", "ДС/1/.hidden", "ДС/1/desktop.ini")
    assert_that(
        Layout(tmp_path).amendments(),
        empty(),
        "Layout does not skip thumbnails, lock files and hidden files",
    )


def test_takes_conditions_and_carriers_from_their_folders(tmp_path: Path) -> None:
    _touch(tmp_path, "Особые условия/a.txt", "Перевозчики/b.txt", "Прочее/c.txt")
    layout = Layout(tmp_path)
    assert_that(
        (_names(tmp_path, layout.conditions()), _names(tmp_path, layout.carriers())),
        contains_inanyorder(["Особые условия/a.txt"], ["Перевозчики/b.txt"]),
        "Layout does not take special conditions and carriers from their own folders",
    )


def test_gives_nothing_for_missing_folders(tmp_path: Path) -> None:
    layout = Layout(tmp_path)
    assert_that(
        layout.amendments() + layout.conditions() + layout.carriers() + layout.policies(),
        empty(),
        "Layout does not give an empty list for a policy folder that is empty",
    )
