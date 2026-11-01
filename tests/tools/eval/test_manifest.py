import random
from pathlib import Path

from hamcrest import assert_that, contains_exactly, equal_to, raises

from tools.eval.gold import Folder
from tools.eval.manifest import Manifest, Part, Split


def test_manifest_gives_version(tmp_path: Path) -> None:
    version = f"v{random.randint(1, 99)}"
    (tmp_path / "m.yaml").write_text(f"version: {version}\ndeclarations: {{}}\n", encoding="utf-8")
    assert_that(
        Manifest(tmp_path / "m.yaml").version(),
        equal_to(version),
        "Manifest does not give the version of the gold",
    )


def test_manifest_finds_part_by_digits_of_number(tmp_path: Path) -> None:
    (tmp_path / "m.yaml").write_text(
        'version: v1\ndeclarations:\n  "005": {policy: Полис-1, part: holdout}\n', encoding="utf-8"
    )
    assert_that(
        Manifest(tmp_path / "m.yaml").part("5"),
        equal_to("holdout"),
        "Manifest does not find the part of a declaration by the digits of its number",
    )


def test_manifest_refuses_declaration_it_does_not_list(tmp_path: Path) -> None:
    (tmp_path / "m.yaml").write_text(
        'version: v1\ndeclarations:\n  "35": {policy: Полис-1, part: dev}\n', encoding="utf-8"
    )
    assert_that(
        lambda: Manifest(tmp_path / "m.yaml").part("97"),
        raises(LookupError),
        "Manifest does not refuse a declaration that it does not list",
    )


def test_manifest_refuses_policy_split_between_parts(tmp_path: Path) -> None:
    (tmp_path / "m.yaml").write_text(
        "version: v1\ndeclarations:\n"
        '  "76": {policy: Полис-2, part: dev}\n  "97": {policy: Полис-2, part: holdout}\n',
        encoding="utf-8",
    )
    assert_that(
        lambda: Manifest(tmp_path / "m.yaml").part("76"),
        raises(ValueError),
        "Manifest does not refuse declarations of one policy in different parts",
    )


def test_manifest_refuses_unknown_part(tmp_path: Path) -> None:
    (tmp_path / "m.yaml").write_text(
        'version: v1\ndeclarations:\n  "35": {policy: Полис-1, part: test}\n', encoding="utf-8"
    )
    assert_that(
        lambda: Manifest(tmp_path / "m.yaml").part("35"),
        raises(ValueError),
        "Manifest does not refuse a part other than dev and holdout",
    )


def test_part_keeps_only_declarations_of_chosen_part(tmp_path: Path) -> None:
    (tmp_path / "gold").mkdir()
    for number in ("35", "70", "97"):
        (tmp_path / "gold" / f"{number}.csv").write_text(
            f"declaration,shipment,field,status\n{number},{number},sum,match\n", encoding="utf-8"
        )
    (tmp_path / "m.yaml").write_text(
        "version: v1\ndeclarations:\n  '35': {policy: Полис-1, part: dev}\n"
        "  '070': {policy: Полис-2, part: holdout}\n  '97': {policy: Полис-3, part: dev}\n",
        encoding="utf-8",
    )
    assert_that(
        [
            sample.declaration()
            for sample in Part(
                Folder(tmp_path / "gold"), Manifest(tmp_path / "m.yaml"), frozenset({"dev"})
            ).samples()
        ],
        contains_exactly("35", "97"),
        "Part does not keep only the declarations of the chosen part",
    )


def test_split_keeps_known_part() -> None:
    assert_that(
        Split(
            {"70": {"policy": "Полис-1", "part": "holdout"}}, {"070": "A1", "35": "B2"}, 0.0
        ).entries()["070"]["part"],
        equal_to("holdout"),
        "Split does not keep the part that the manifest already gives",
    )


def test_split_gives_new_group_part_of_its_known_member() -> None:
    assert_that(
        Split(
            {"76": {"policy": "Полис-1", "part": "holdout"}}, {"76": "A1", "97": "a1 "}, 0.0
        ).entries()["97"]["part"],
        equal_to("holdout"),
        "Split does not give a new declaration the part of its policy group",
    )


def test_split_keeps_holdout_within_share() -> None:
    policies = {str(number): f"P{number % 7}" for number in range(1, 41)}
    assert_that(
        sum(
            1 for entry in Split({}, policies, 0.3).entries().values() if entry["part"] == "holdout"
        )
        <= 12,
        equal_to(True),
        "Split does not keep the holdout part within its share",
    )


def test_split_labels_policy_groups_without_numbers() -> None:
    assert_that(
        Split({}, {"5": "0000T00GR0000", "7": "0000T00GR0000"}, 0.3).entries()["7"]["policy"],
        equal_to("Полис-1"),
        "Split does not label a policy group without its number",
    )


def test_split_refuses_group_already_in_two_parts() -> None:
    known = {"1": {"policy": "x", "part": "dev"}, "2": {"policy": "y", "part": "holdout"}}
    assert_that(
        lambda: Split(known, {"1": "Z", "2": "Z"}, 0.3).entries(),
        raises(ValueError),
        "Split does not refuse a policy group whose declarations are already in two parts",
    )
