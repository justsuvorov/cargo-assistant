import random
import uuid
from collections.abc import Mapping
from pathlib import Path

from hamcrest import assert_that, equal_to, raises
from openpyxl import load_workbook

from app.domain.card import Card
from app.domain.declaration import Declaration
from app.domain.policy import Policy, Vacant
from app.domain.status import Match
from app.reports.errors import ReportError
from app.reports.report import Report, Stated
from app.rules.card import Ruled
from app.rules.cards import Cards
from app.rules.probe import Constant
from app.rules.rows import Rowwise
from app.rules.wording import Comments
from tests.rules.fakes import Mute, Paper, Profile


def _cards(form: str) -> tuple[Card, ...]:
    return Cards(Path(__file__).resolve().parents[2] / "cards", Mute()).cards(form)


def _vertical(number: str) -> Paper:
    return Paper(
        number,
        "vertical",
        (
            {
                "insurer": ("ООО «Тест»",),
                "policy": ("№ 0000T00GR0000 от 26.08.2026 г.",),
                "cargo": ("мясо, сыр",),
                "packaging": ("коробки, 10 мест, 100 кг",),
                "beneficiary": ("ООО «Получатель»",),
                "sum": ("7 492 870", "рублей"),
                "transport": ("Авто",),
                "departure": ("г. Первый",),
                "destination": ("г. Второй",),
                "period": ("21.09.2026", "30.09.2026"),
                "document": ("771-12306011 от 19.09.2026",),
                "carrier": ("ООО «Перевозчик»",),
                "sealing": ("да",),
            },
        ),
    )


def _row(cargo: str) -> Mapping[str, tuple[str, ...]]:
    return {
        "insurer": ("ООО «Тест»",),
        "policy": ("№ 0000T00GR0000 от 26.08.2026 г.",),
        "period_start": ("14.09.2026",),
        "period_end": ("30.09.2026",),
        "cargo": (cargo,),
        "beneficiary": ("нет",),
        "document_number": ("13444-2/Р",),
        "document_date": ("14.09.2026",),
        "transport": ("Авто",),
        "departure": ("г. Первый",),
        "destination": ("г. Второй",),
        "sum": ("1 000 000", "RUB"),
    }


def _sheet(declaration: Declaration, policy: Policy, folder: Path) -> tuple[tuple[str, ...], ...]:
    report = Report(declaration, policy, _cards(declaration.form()), Stated((), ()))
    report.save(folder / report.name())
    return tuple(
        tuple(str(value or "") for value in row)
        for row in load_workbook(folder / report.name())
        .worksheets[0]
        .iter_rows(min_row=2, values_only=True)
    )


def test_vertical_result_has_fifteen_rows_numbered_by_the_declaration(tmp_path: Path) -> None:
    number = str(random.randint(100, 999))
    assert_that(
        tuple((row[0], row[1]) for row in _sheet(_vertical(number), Vacant("1"), tmp_path)),
        equal_to(
            tuple(
                (number, title)
                for title in (
                    "Страхователь",
                    "№ Генерального полиса и дата",
                    "Полное наименование груза",
                    "Род упаковки, число мест, общий вес",
                    "Выгодоприобретатель",
                    "Страховая сумма",
                    "Транспорт",
                    "Пункт отправления",
                    "Пункт перегрузки (таможенного оформления)",
                    "Пункт назначения",
                    "Период страхования",
                    "Транспортный документ (ТТН/ЦМР)",
                    "Перевозчик",
                    "Пломбирование",
                    "Прочие сведения",
                )
            )
        ),
        "Report does not lay out the fifteen rows of the vertical form",
    )


def test_vertical_result_without_profile_decides_only_what_needs_no_policy(
    tmp_path: Path,
) -> None:
    assert_that(
        tuple(row[3] for row in _sheet(_vertical("200"), Vacant("1"), tmp_path)),
        equal_to(
            (
                "требует проверки",
                "требует проверки",
                "требует проверки",
                "совпадает",
                "совпадает",
                "требует проверки",
                "требует проверки",
                "требует проверки",
                "совпадает",
                "требует проверки",
                "требует проверки",
                "совпадает",
                "совпадает",
                "совпадает",
                "совпадает",
            )
        ),
        "Report does not leave to a person exactly the checks that need the policy",
    )


def test_table_result_has_thirteen_rows_per_shipment(tmp_path: Path) -> None:
    rows = _sheet(Paper("300", "psg", (_row("Бумага"), _row("Мех"))), Vacant("1"), tmp_path)
    assert_that(
        (len(rows), rows[0][0], rows[13][0], {row[1] for row in rows} & {"Перевозчик"}),
        equal_to((26, "300/1", "300/2", set())),
        "Report does not lay out thirteen rows per shipment of the table form",
    )


def test_table_result_without_profile_decides_only_what_needs_no_policy(
    tmp_path: Path,
) -> None:
    assert_that(
        tuple(
            row[3] for row in _sheet(Paper("301", "psg", (_row("Бумага"),)), Vacant("1"), tmp_path)
        ),
        equal_to(
            (
                "требует проверки",
                "требует проверки",
                "требует проверки",
                "требует проверки",
                "требует проверки",
                "не совпадает",
                "совпадает",
                "совпадает",
                "требует проверки",
                "требует проверки",
                "совпадает",
                "требует проверки",
                "требует проверки",
            )
        ),
        "Report does not leave to a person exactly the table checks that need the policy",
    )


def test_policy_checks_without_profile_name_the_missing_clause(tmp_path: Path) -> None:
    assert_that(
        _sheet(Paper("302", "psg", (_row("Бумага"),)), Vacant("1"), tmp_path)[12][4],
        equal_to("пункт «limit» не найден в профиле полиса"),
        "Report does not explain that the clause is missing from the profile",
    )


def test_saved_rows_are_the_verdicts_of_the_cards(tmp_path: Path) -> None:
    paper = Paper("303", "psg", (_row("Бумага"), _row("Бумага")))
    cards = _cards("psg")
    verdicts = {card.field(): card.verdicts(paper, Vacant("1")) for card in cards}
    assert_that(
        _sheet(paper, Vacant("1"), tmp_path),
        equal_to(
            tuple(
                (
                    shipment.number(),
                    card.title("psg"),
                    card.subject(),
                    verdicts[card.field()][index].status().text(),
                    verdicts[card.field()][index].remark().comment(),
                )
                for index, shipment in enumerate(paper.shipments())
                for card in cards
            )
        ),
        "Report does not save the verdicts of the cards row by row",
    )


def test_status_cells_are_coloured(tmp_path: Path) -> None:
    report = Report(_vertical("304"), Vacant("1"), _cards("vertical"), Stated((), ()))
    report.save(tmp_path / report.name())
    sheet = load_workbook(tmp_path / report.name()).worksheets[0]
    assert_that(
        {
            str(sheet.cell(row, 4).value): sheet.cell(row, 4).fill.fgColor.rgb
            for row in range(2, sheet.max_row + 1)
        },
        equal_to({"совпадает": "FFD6F0D6", "требует проверки": "FFFFF3CD"}),
        "Report does not colour match green and review yellow",
    )


def test_mismatch_cell_is_red(tmp_path: Path) -> None:
    report = Report(Paper("305", "psg", (_row("Бумага"),)), Vacant("1"), _cards("psg"), Stated((), ()))
    report.save(tmp_path / report.name())
    assert_that(
        load_workbook(tmp_path / report.name()).worksheets[0].cell(7, 4).fill.fgColor.rgb,
        equal_to("FFF0D6D6"),
        "Report does not colour a mismatch red",
    )


def test_header_follows_the_answer_form(tmp_path: Path) -> None:
    report = Report(_vertical("306"), Vacant("1"), _cards("vertical"), Stated((), ()))
    report.save(tmp_path / report.name())
    assert_that(
        tuple(cell.value for cell in load_workbook(tmp_path / report.name()).worksheets[0][1]),
        equal_to(
            (
                "Номер декларации/строки",
                "Наименование поля в декларации",
                "С каким пунктом Ген. полиса сверено",
                "Результат проверки\n(совпадает/не совпадает)",
                "Комментарий по сверке",
            )
        ),
        "Report does not write the header of the answer form",
    )


def test_second_sheet_lists_the_special_conditions_with_source_and_priority(
    tmp_path: Path,
) -> None:
    rows = (
        (f"Условие {uuid.uuid4().hex}", "файл клиента", "выше"),
        (f"Условие {uuid.uuid4().hex}", "общий файл", "обычный"),
    )
    report = Report(_vertical("307"), Vacant("1"), _cards("vertical"), Stated(rows, ()))
    report.save(tmp_path / report.name())
    sheet = load_workbook(tmp_path / report.name())["Особые условия"]
    assert_that(
        tuple(sheet.iter_rows(values_only=True)),
        equal_to((("Условие", "Источник", "Приоритет"), *rows)),
        "Report does not list the conditions with their source and priority on the second sheet",
    )


def test_second_sheet_tells_the_reasons_when_there_are_no_conditions(tmp_path: Path) -> None:
    reason = uuid.uuid4().hex
    report = Report(_vertical("310"), Vacant("1"), _cards("vertical"), Stated((), (reason, "ещё")))
    report.save(tmp_path / report.name())
    sheet = load_workbook(tmp_path / report.name())["Особые условия"]
    assert_that(
        tuple(sheet.iter_rows(min_row=2, values_only=True)),
        equal_to(((f"Особые условия не найдены: {reason}; ещё", None, None),)),
        "Report does not give the reasons in one row when no conditions are found",
    )


def test_slash_in_the_number_does_not_break_the_file_name(tmp_path: Path) -> None:
    report = Report(_vertical("13444-2/Р"), Vacant("1"), _cards("vertical"), Stated((), ()))
    report.save(tmp_path / report.name())
    assert_that(
        tuple(path.name for path in tmp_path.iterdir()),
        equal_to(("13444-2_Р – результат проверки.xlsx",)),
        "Report does not replace the slash in the file name",
    )


class _Silent:
    """Check that gives no verdicts at all."""

    def verdicts(self, _declaration: Declaration, _policy: Policy) -> tuple[()]:
        return ()


def test_card_without_a_verdict_for_a_row_fails_loudly(tmp_path: Path) -> None:
    report = Report(
        _vertical("308"),
        Vacant("1"),
        (Ruled("sealing", {"vertical": "Пломбирование"}, "НЕ ОБЯЗАТЕЛЕН", _Silent()),),
        Stated((), ()),
    )
    assert_that(
        lambda: report.save(tmp_path / report.name()),
        raises(ReportError, "sealing"),
        "Report does not fail when a card gives no verdict for a row",
    )


def test_unrelated_cards_fail_loudly(tmp_path: Path) -> None:
    report = Report(
        Paper("309", "psg", (_row("Бумага"),)),
        Vacant("1"),
        (
            Ruled(
                "sealing",
                {"vertical": "Пломбирование"},
                "НЕ ОБЯЗАТЕЛЕН",
                Rowwise("sealing", Constant(Match(), "filled"), Comments({"match": ""}), Mute()),
            ),
        ),
        Stated((), ()),
    )
    assert_that(
        lambda: report.save(tmp_path / report.name()),
        raises(ReportError, "psg"),
        "Report does not fail when no card serves the form",
    )
