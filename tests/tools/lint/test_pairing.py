from hamcrest import assert_that, empty, has_length

from tools.lint.pairing import Pairing
from tools.lint.script import Code


def test_pairing_finds_application_module() -> None:
    assert_that(
        Pairing(frozenset({"app/domain/status.py"})).violations(
            Code("tests/domain/test_status.py", "")
        ),
        empty(),
        "Pairing does not find the application module",
    )


def test_pairing_finds_tool_module() -> None:
    assert_that(
        Pairing(frozenset({"tools/lint/script.py"})).violations(
            Code("tests/tools/lint/test_script.py", "")
        ),
        empty(),
        "Pairing does not find the tool module",
    )


def test_pairing_rejects_orphan_test() -> None:
    assert_that(
        Pairing(frozenset({"app/domain/status.py"})).violations(
            Code("tests/domain/test_statuses.py", "")
        ),
        has_length(1),
        "Pairing does not reject a test without a module",
    )


def test_pairing_skips_deployment_tests() -> None:
    assert_that(
        Pairing(frozenset()).violations(Code("tests/deploy/test_manifests.py", "")),
        empty(),
        "Pairing does not skip tests of release files",
    )


def test_pairing_rejects_orphan_test_outside_deployment_folder() -> None:
    assert_that(
        Pairing(frozenset()).violations(Code("tests/core/test_manifests.py", "")),
        has_length(1),
        "Pairing does not reject an orphan test outside the deployment folder",
    )
