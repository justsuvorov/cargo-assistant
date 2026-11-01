import random
import uuid
from datetime import date
from pathlib import Path
from typing import Final, final

import openpyxl
from hamcrest import assert_that, contains_exactly, equal_to, has_item

from app.declarations.fields import Read, Whole
from app.domain.field import Blank, Field
from app.domain.shipment import Shipment
from tools.eval.fields import Deck
from tools.eval.template import Columns, Template


@final
class _Shipment:
    __slots__ = ("_cargo", "_number")

    def __init__(self, number: str, cargo: str) -> None:
        self._number: Final = number
        self._cargo: Final = cargo

    def number(self) -> str:
        return self._number

    def declaration(self) -> str:
        return self._number.split("/")[0]

    def field(self, key: str) -> Field:
        return Read(key, Whole((self._cargo,))) if key == "cargo" else Blank(key)

    def start(self) -> date:
        return date(2026, 9, 14)


@final
class _Declaration:
    __slots__ = ("_form", "_shipments")

    def __init__(self, form: str, shipments: tuple[Shipment, ...]) -> None:
        self._form: Final = form
        self._shipments: Final = shipments

    def number(self) -> str:
        return self._shipments[0].declaration()

    def form(self) -> str:
        return self._form

    def policy(self) -> str:
        return ""

    def shipments(self) -> tuple[Shipment, ...]:
        return self._shipments


def _cards(folder: Path) -> Deck:
    folder.mkdir()
    (folder / "cargo.yaml").write_text(
        "field: cargo\nforms:\n  vertical: {order: 3, title: Полное наименование груза}\n"
        "  psg: {order: 5, title: Наименование груза}\n",
        encoding="utf-8",
    )
    (folder / "sum.yaml").write_text(
        "field: sum\nforms:\n  vertical: {order: 6, title: Страховая сумма}\n"
        "  psg: {order: 13, title: Страховая сумма}\n",
        encoding="utf-8",
    )
    (folder / "sealing.yaml").write_text(
        "field: sealing\nforms:\n  vertical: {order: 14, title: Пломбирование}\n", encoding="utf-8"
    )
    return Deck(folder)


def _rows(path: Path) -> list[tuple[str, ...]]:
    return [
        tuple("" if cell is None else str(cell) for cell in row)
        for row in openpyxl.load_workbook(path)["Разметка"].iter_rows(values_only=True)
    ]


def test_template_writes_fields_of_form_for_every_shipment(tmp_path: Path) -> None:
    Template(
        _Declaration("psg", (_Shipment("113/1", "мебель"), _Shipment("113/2", "посуда"))),
        _cards(tmp_path / "cards"),
    ).write(tmp_path / "t.xlsx")
    assert_that(
        [(row[0], row[1]) for row in _rows(tmp_path / "t.xlsx")[1:]],
        contains_exactly(
            ("113/1", "Наименование груза"),
            ("113/1", "Страховая сумма"),
            ("113/2", "Наименование груза"),
            ("113/2", "Страховая сумма"),
        ),
        "Template does not write the fields of the form for every shipment in order",
    )


def test_template_keeps_leading_zeros_of_single_shipment(tmp_path: Path) -> None:
    Template(
        _Declaration("vertical", (_Shipment("005", "мебель"),)), _cards(tmp_path / "cards")
    ).write(tmp_path / "t.xlsx")
    assert_that(
        _rows(tmp_path / "t.xlsx")[1][0],
        equal_to("005"),
        "Template does not keep the number of a single shipment as written",
    )


def test_template_shows_declared_value(tmp_path: Path) -> None:
    cargo = uuid.uuid4().hex
    Template(_Declaration("vertical", (_Shipment("7", cargo),)), _cards(tmp_path / "cards")).write(
        tmp_path / "t.xlsx"
    )
    assert_that(
        _rows(tmp_path / "t.xlsx")[1][2],
        equal_to(cargo),
        "Template does not show the declared value next to the field",
    )


def test_template_leaves_expert_columns_empty(tmp_path: Path) -> None:
    Template(
        _Declaration("vertical", (_Shipment("7", "мебель"),)), _cards(tmp_path / "cards")
    ).write(tmp_path / "t.xlsx")
    assert_that(
        {cell for row in _rows(tmp_path / "t.xlsx")[1:] for cell in row[3:]},
        equal_to({""}),
        "Template does not leave the columns of the expert empty",
    )


def test_template_offers_three_statuses_in_list(tmp_path: Path) -> None:
    Template(
        _Declaration("psg", (_Shipment(f"{random.randint(1, 99)}", "мебель"),)),
        _cards(tmp_path / "cards"),
    ).write(tmp_path / "t.xlsx")
    assert_that(
        [
            rule.formula1
            for rule in openpyxl.load_workbook(tmp_path / "t.xlsx")[
                "Разметка"
            ].data_validations.dataValidation
        ],
        has_item('"совпадает,не совпадает,требует проверки"'),
        "Template does not offer the three statuses in a list",
    )


def test_template_writes_instruction_sheet(tmp_path: Path) -> None:
    Template(_Declaration("psg", (_Shipment("35", "мебель"),)), _cards(tmp_path / "cards")).write(
        tmp_path / "t.xlsx"
    )
    assert_that(
        openpyxl.load_workbook(tmp_path / "t.xlsx").sheetnames,
        contains_exactly("Разметка", "Инструкция"),
        "Template does not write the instruction for the expert on a second sheet",
    )


def test_columns_follow_gold_requirements() -> None:
    assert_that(
        Columns().titles()[3:],
        contains_exactly(
            "Ожидаемый статус", "Пункт ГП / ДС", "Причина", "Уверенность", "Примечание"
        ),
        "Columns do not follow section 3 of the gold requirements",
    )
