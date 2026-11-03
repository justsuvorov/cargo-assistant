from hamcrest import assert_that, contains_exactly, empty, equal_to

from app.policy.title import Title


def test_recognizes_policy_by_its_first_line() -> None:
    assert_that(
        Title("Генеральный полис № 9X13GR0001 страхования грузов\nг. Город").policy(),
        equal_to(True),
        "Title does not recognize a general policy by its first line",
    )


def test_recognizes_english_policy() -> None:
    assert_that(
        Title("General Cargo Insurance Policy No. 5\nCity").policy(),
        equal_to(True),
        "Title does not recognize an English general policy",
    )


def test_attachment_to_policy_is_not_a_policy() -> None:
    assert_that(
        Title("Приложение № 3 к Генеральному полису № 9X13GR0001 от 01.01.2020").policy(),
        equal_to(False),
        "Title does not tell an attachment that mentions a policy from the policy",
    )


def test_skips_blank_lines_before_the_title() -> None:
    assert_that(
        Title("\n  \nГенеральный полис № 1").policy(),
        equal_to(True),
        "Title does not skip blank lines before the first line",
    )


def test_amendment_is_not_a_policy() -> None:
    assert_that(
        Title("Дополнительное соглашение № 9X13GR0001-D00004\nк Генеральному полису").policy(),
        equal_to(False),
        "Title does not tell an amendment from a general policy",
    )


def test_recognizes_amendment_and_reads_number_after_suffix_d() -> None:
    title = Title("Дополнительное соглашение № 9X13GR0001-D00012\nк Генеральному полису")
    assert_that(
        (title.amendment(), title.number()),
        equal_to((True, (12,))),
        "Title does not read the number of an amendment after the suffix D",
    )


def test_reads_number_when_a_space_stands_before_the_dash() -> None:
    assert_that(
        Title("Дополнительное соглашение № 9X13GR0001 -D00016").number(),
        contains_exactly(16),
        "Title does not read a number with a space before the dash",
    )


def test_reads_plain_number_without_policy_prefix() -> None:
    assert_that(
        Title("Дополнительное соглашение № 7 к полису").number(),
        contains_exactly(7),
        "Title does not read a plain number of an amendment",
    )


def test_reads_number_of_english_amendment() -> None:
    title = Title("Additional Agreement No. 9X13GR0001-D00003\nto the General Policy")
    assert_that(
        (title.amendment(), title.number()),
        equal_to((True, (3,))),
        "Title does not read an English amendment with its number",
    )


def test_gives_no_number_when_the_title_has_none() -> None:
    assert_that(
        Title("Дополнительное соглашение\nк полису").number(),
        empty(),
        "Title does not leave the number empty for an amendment that has none",
    )
