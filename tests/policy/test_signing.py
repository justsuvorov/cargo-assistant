from datetime import date

from hamcrest import assert_that, contains_exactly, equal_to

from app.policy.papers import Opened
from app.policy.signing import Signing


def _text(
    title: str = "Дополнительное соглашение № 9X13GR0001-D00004",
    signed: str = "«26» ноября 2020 г.",
    effective: str = "«27» ноября 2020 г. и действует по «03» декабря 2021 г.",
    declarations: str = "для перевозки по декларации № 154 об отгрузке:",
) -> str:
    return "\n".join(
        (
            title,
            "к Генеральному полису страхования грузов № 9X13GR0001 от 20.10.20217 г.",
            f"г. Город\t\t\t\t{signed}",
            "Страховщик действует на основании Доверенности № 5 от «01» июля 2020 г.",
            declarations,
            f"Настоящее Дополнительное соглашение вступает в силу с {effective}",
        )
    )


def test_reads_number_effective_date_and_scope_of_signed_amendment() -> None:
    outcome = Signing(Opened("ДС/a.docx", _text())).survey()
    amendment = outcome.items()[0]
    assert_that(
        (amendment.number(), amendment.effective(), amendment.scope(), outcome.problems()),
        equal_to((4, date(2020, 11, 27), ("154",), ())),
        "Signing does not read the number, effective date and scope of a signed amendment",
    )


def test_keeps_reference_and_text_of_the_paper() -> None:
    amendment = Signing(Opened("ДС/a.docx", _text())).survey().items()[0]
    assert_that(
        (amendment.reference(), amendment.text()),
        equal_to(("ДС/a.docx", _text())),
        "Signing does not keep the reference and the text of the paper",
    )


def test_excludes_draft_without_dates_and_names_it() -> None:
    outcome = Signing(
        Opened(
            "ДС/d.docx",
            _text(
                title="Дополнительное соглашение № 9X13GR0001-D00024",
                signed="«     »            2026 г.",
                effective="  .  .2026 г. и действует до окончания периода страхования",
            ),
        )
    ).survey()
    assert_that(
        (outcome.items(), outcome.problems()),
        equal_to(
            (
                (),
                (
                    "ДС 24 (ДС/d.docx) исключено как проект: не указана дата подписания"
                    " и вступления",
                ),
            )
        ),
        "Signing does not exclude a draft and name it in problems",
    )


def test_excludes_amendment_that_has_only_signing_date() -> None:
    outcome = Signing(Opened("a.docx", _text(effective="  .  .2026 г."))).survey()
    assert_that(
        (outcome.items(), outcome.problems()),
        equal_to(
            (
                (),
                ("ДС 4 (a.docx) исключено как проект: не указана дата вступления",),
            )
        ),
        "Signing does not exclude an amendment whose entry into force is blank",
    )


def test_keeps_amendment_that_enters_into_force_before_signing_and_names_it() -> None:
    outcome = Signing(
        Opened("a.docx", _text(signed="«16» октября 2025 г.", effective="19.11.2024 г."))
    ).survey()
    assert_that(
        (len(outcome.items()), outcome.problems()),
        equal_to(
            (
                1,
                ("ДС 4 (a.docx): дата вступления 19.11.2024 раньше даты подписания 16.10.2025",),
            )
        ),
        "Signing does not keep an amendment that enters into force before signing",
    )


def test_excludes_amendment_whose_number_cannot_be_read() -> None:
    outcome = Signing(Opened("a.docx", _text(title="Дополнительное соглашение к полису"))).survey()
    assert_that(
        (outcome.items(), outcome.problems()),
        equal_to(
            (
                (),
                ("В файле a.docx не прочитан номер ДС, документ исключён из пакета",),
            )
        ),
        "Signing does not exclude an amendment whose number cannot be read",
    )


def test_excludes_amendment_whose_declarations_are_blank() -> None:
    outcome = Signing(
        Opened("a.docx", _text(declarations="для перевозки по декларации №           об отгрузке"))
    ).survey()
    assert_that(
        (outcome.items(), outcome.problems()),
        equal_to(
            (
                (),
                (
                    "ДС 4 (a.docx) исключено: область действия названа, но номера деклараций"
                    " не читаются",
                ),
            )
        ),
        "Signing does not exclude an amendment whose declaration numbers are blank",
    )


def test_amendment_without_declarations_concerns_the_whole_policy() -> None:
    amendment = Signing(
        Opened("a.docx", _text(declarations="Пункт 6 принять в следующей редакции:"))
    ).survey()
    assert_that(
        [len(item.scope()) for item in amendment.items()],
        contains_exactly(0),
        "Signing does not give an empty scope to an amendment that names no declaration",
    )


def test_names_different_declarations_of_text_and_attachment() -> None:
    text = (
        _text() + "\nПриложение\n1. Приложение № 1 - Декларация № 528 об отгрузке от 06.07.2026 г."
    )
    outcome = Signing(Opened("ДС/a.docx", text)).survey()
    assert_that(
        (outcome.items()[0].scope(), outcome.problems()),
        equal_to(
            (
                ("154", "528"),
                (
                    "ДС 4 (ДС/a.docx): в тексте названа декларация 154, а в приложении 528,"
                    " ДС отнесено к обеим",
                ),
            )
        ),
        "Signing does not apply the amendment to both declarations and name the mismatch",
    )


def test_gives_no_problem_when_text_and_attachment_name_one_declaration() -> None:
    text = (
        _text() + "\nПриложение\n1. Приложение № 1 - Декларация № 154 об отгрузке от 06.07.2026 г."
    )
    outcome = Signing(Opened("ДС/a.docx", text)).survey()
    assert_that(
        (outcome.items()[0].scope(), outcome.problems()),
        equal_to((("154",), ())),
        "Signing does not give an empty problem list when text and attachment name one declaration",
    )
