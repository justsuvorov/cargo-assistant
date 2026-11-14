from pathlib import Path

from hamcrest import assert_that, contains_exactly, equal_to
from openpyxl import Workbook

from app.policy.conditions import ClientFile, Joined, SharedFile


class _Written:
    def __init__(self, lines: tuple[str, ...]) -> None:
        self._lines = lines

    def conditions(self) -> tuple[str, ...]:
        return self._lines


def _book(path: Path, sheets: dict[str, list[list[str]]]) -> Path:
    book = Workbook()
    for name, rows in sheets.items():
        sheet = book.create_sheet(name)
        for row in rows:
            sheet.append(row)
    book.remove(book.worksheets[0])
    book.save(path)
    return path


_GP = [
    ["Наименование Страхователя", "№ Генерального полиса", "ОСОБЫЕ  условия"],
    ["Ромашка", "77 AB 01", "Без франшизы"],
    ["Ромашка", "77AB01", ""],
    ["Лютик", "99 ZZ 02", "Только морем"],
    ["Ромашка", "77ab01", "Курьерский груз исключён"],
]
_DEFENSE = [
    ["Страхователь", "Договор", "Перестрахование, при условии:", "Форма работы"],
    ["ООО «Оборона-1»", "55-DD", "сумма больше лимита", "по согласованию"],
]


def test_finds_conditions_of_policy_by_normalized_number(tmp_path: Path) -> None:
    found = SharedFile(_book(tmp_path / "a.xlsx", {"ГП": _GP})).find("77 ab 01", "")
    assert_that(
        [item.text() for item in found.items()],
        contains_exactly("Без франшизы", "Курьерский груз исключён"),
        "SharedFile does not find the non-blank conditions of the policy by its normalized number",
    )


def test_names_book_sheet_and_row_as_source(tmp_path: Path) -> None:
    found = SharedFile(_book(tmp_path / "fsc.xlsx", {"ГП": _GP})).find("99ZZ02", "")
    assert_that(
        found.items()[0].source(),
        equal_to("общий файл fsc.xlsx, лист «ГП», строка 4"),
        "SharedFile does not name the file, sheet and row of a condition",
    )


def test_finds_defense_row_by_contract_or_insurant(tmp_path: Path) -> None:
    shared = SharedFile(_book(tmp_path / "a.xlsx", {"оборонный": _DEFENSE}))
    assert_that(
        (
            shared.find("55 dd", "").items()[0].text(),
            shared.find("", "оао оборона-1").items()[0].text(),
            shared.find("00", "Другой").items(),
        ),
        equal_to(
            (
                "Оборонный сегмент: ООО «Оборона-1», перестрахование при условии "
                "«сумма больше лимита», форма работы «по согласованию»",
                "Оборонный сегмент: ООО «Оборона-1», перестрахование при условии "
                "«сумма больше лимита», форма работы «по согласованию»",
                (),
            )
        ),
        "SharedFile does not match the defense sheet by contract or insurant",
    )


def test_reports_absent_file_without_failing(tmp_path: Path) -> None:
    found = SharedFile(tmp_path / "none.xlsx").find("77AB01", "")
    assert_that(
        (found.items(), found.problems()),
        equal_to(((), ("общий файл особых условий none.xlsx не найден",))),
        "SharedFile does not report an absent file as a reason",
    )


def test_reports_not_configured_path() -> None:
    assert_that(
        SharedFile(Path("")).find("77AB01", "").problems(),
        contains_exactly("путь к общему файлу особых условий не задан"),
        "SharedFile does not report an empty path as a reason",
    )


def test_reports_absent_sheets_and_columns(tmp_path: Path) -> None:
    path = _book(tmp_path / "a.xlsx", {"ГП": [["Другое", "Ещё"], ["1", "2"]]})
    found = SharedFile(path).find("77AB01", "Ромашка")
    assert_that(
        (found.items(), len(found.problems())),
        equal_to(((), 2)),
        "SharedFile does not report each absent sheet and column as a reason",
    )


def test_reports_no_rows_for_policy(tmp_path: Path) -> None:
    found = SharedFile(_book(tmp_path / "a.xlsx", {"ГП": _GP, "ОБОРОННЫЙ": _DEFENSE})).find(
        "11XX11", "Нет такого"
    )
    assert_that(
        (found.items(), found.problems()),
        equal_to(((), ("в общем файле особых условий нет строк для этого полиса",))),
        "SharedFile does not report that no row matches the policy",
    )


def test_reports_broken_file_without_failing(tmp_path: Path) -> None:
    (tmp_path / "a.xlsx").write_text("не книга", encoding="utf-8")
    assert_that(
        SharedFile(tmp_path / "a.xlsx").find("77AB01", "").problems(),
        equal_to(("общий файл особых условий a.xlsx не читается",)),
        "SharedFile does not report an unreadable workbook as a reason",
    )


def test_client_file_gives_lines_that_prevail() -> None:
    found = ClientFile(_Written(("Первое", "  ", "Второе"))).find("77AB01", "")
    assert_that(
        [(item.text(), item.source(), item.prevails()) for item in found.items()],
        contains_exactly(("Первое", "файл клиента", True), ("Второе", "файл клиента", True)),
        "ClientFile does not give the non-blank lines as conditions that prevail",
    )


def test_client_file_without_lines_reports_reason() -> None:
    found = ClientFile(_Written(())).find("77AB01", "")
    assert_that(
        (found.items(), found.problems()),
        equal_to(((), ("файл особых условий клиента не найден или пуст",))),
        "ClientFile does not report a missing file as a reason",
    )


def test_joined_puts_client_conditions_first(tmp_path: Path) -> None:
    shared = SharedFile(_book(tmp_path / "a.xlsx", {"ГП": _GP}))
    found = Joined((ClientFile(_Written(("Своё",))), shared)).find("99ZZ02", "")
    assert_that(
        [(item.text(), item.prevails()) for item in found.items()],
        contains_exactly(("Своё", True), ("Только морем", False)),
        "Joined does not put the conditions of the client before the shared ones",
    )


def test_joined_keeps_problems_of_every_part(tmp_path: Path) -> None:
    found = Joined((ClientFile(_Written(())), SharedFile(tmp_path / "x.xlsx"))).find("1", "")
    assert_that(
        (found.items(), found.problems()),
        equal_to(
            (
                (),
                (
                    "файл особых условий клиента не найден или пуст",
                    "общий файл особых условий x.xlsx не найден",
                ),
            )
        ),
        "Joined does not keep the reasons of every part",
    )


def test_does_not_give_whole_workbook(tmp_path: Path) -> None:
    rows = [_GP[0]] + [[f"Клиент {n}", f"N{n}", f"Условие {n}"] for n in range(300)]
    found = SharedFile(_book(tmp_path / "a.xlsx", {"ГП": rows})).find("N7", "")
    assert_that(
        [item.text() for item in found.items()],
        equal_to(["Условие 7"]),
        "SharedFile does not give only the row of the policy and not the whole workbook",
    )
