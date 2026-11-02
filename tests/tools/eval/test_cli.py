import random
from pathlib import Path

import openpyxl
import yaml
from hamcrest import assert_that, contains_string, equal_to

from tools.eval.cli import main


def _declaration(path: Path, number: int, policy: str, rows: int) -> None:
    book = openpyxl.Workbook()
    sheet = book.worksheets[0]
    head: dict[tuple[int, int], str | int] = {
        (2, 10): f"№ {policy} от 26.08.2026 г.",
        (8, 1): "Декларация №",
        (8, 5): number,
        (11, 1): "Страхователь",
        (11, 4): "ООО «Тест»",
        (14, 1): "№ п/п",
        (14, 2): "Период страхования",
        (14, 4): "Наименование груза",
        (14, 13): "Страховая сумма",
        (14, 14): "Валюта",
        (15, 2): "начало",
        (15, 3): "окончание",
    }
    for (row, column), value in head.items():
        sheet.cell(row=row, column=column, value=value)
    for index in range(1, rows + 1):
        for column, value in ((1, index), (2, "14.09.2026"), (3, "30.09.2026"), (4, "мебель")):
            sheet.cell(row=15 + index, column=column, value=value)
        sheet.cell(row=15 + index, column=13, value=random.randint(1, 10**6))
        sheet.cell(row=15 + index, column=14, value="рублей")
    path.parent.mkdir(parents=True, exist_ok=True)
    book.save(path)


def _cards(folder: Path) -> Path:
    folder.mkdir()
    (folder / "cargo.yaml").write_text(
        'field: cargo\nforms:\n  psg: {order: 5, title: "Наименование груза"}\n', encoding="utf-8"
    )
    (folder / "sum.yaml").write_text(
        'field: sum\nforms:\n  psg: {order: 13, title: "Страховая сумма"}\n', encoding="utf-8"
    )
    return folder


def _gold(folder: Path, lines: str) -> Path:
    folder.mkdir()
    (folder / "35.csv").write_text(
        f"declaration,shipment,field,status,confidence\n{lines}", encoding="utf-8"
    )
    return folder


def _manifest(path: Path, parts: dict[str, str]) -> Path:
    path.write_text(
        yaml.safe_dump(
            {
                "version": "v7",
                "log": [],
                "declarations": {
                    number: {"policy": f"Полис-{index}", "part": part}
                    for index, (number, part) in enumerate(parts.items())
                },
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return path


def _fill(path: Path, status: str, confidence: str) -> None:
    book = openpyxl.load_workbook(path)
    sheet = book["Разметка"]
    for row in range(2, sheet.max_row + 1):
        sheet.cell(row=row, column=4, value=status)
        sheet.cell(row=row, column=5, value="п. 12 ГП")
        sheet.cell(row=row, column=6, value="Сумма выше лимита ООО «Ромашка»")
        sheet.cell(row=row, column=7, value=confidence)
    book.save(path)


def test_run_writes_report_of_stub_pipeline(tmp_path: Path) -> None:
    (tmp_path / "gold").mkdir()
    (tmp_path / "gold" / "97.csv").write_text(
        "declaration,shipment,field,status,basis,note\n97,97,sum,mismatch,D-23,\n"
        "97,97,cargo,review,fsc-note,\n",
        encoding="utf-8",
    )
    main(
        [
            "run",
            "--gold",
            str(tmp_path / "gold"),
            "--manifest",
            str(_manifest(tmp_path / "manifest.yaml", {"97": "dev"})),
            "--out",
            str(tmp_path / "report.md"),
        ]
    )
    assert_that(
        (tmp_path / "report.md").read_text(encoding="utf-8"),
        contains_string("| **Итого** | 2 | 1 | 50.0% | 100.0% | 0 |"),
        "Run does not report the accuracy of the stub pipeline",
    )


def test_run_scores_match_baseline(tmp_path: Path) -> None:
    (tmp_path / "gold").mkdir()
    (tmp_path / "gold" / "97.csv").write_text(
        "declaration,shipment,field,status,basis,note\n97,97,sum,mismatch,D-23,\n"
        "97,97,cargo,match,fsc-ok,\n97,97,policy,match,fsc-ok,\n",
        encoding="utf-8",
    )
    main(
        [
            "run",
            "--gold",
            str(tmp_path / "gold"),
            "--manifest",
            str(_manifest(tmp_path / "manifest.yaml", {"097": "dev"})),
            "--pipeline",
            "match",
            "--out",
            str(tmp_path / "report.md"),
        ]
    )
    assert_that(
        (tmp_path / "report.md").read_text(encoding="utf-8"),
        contains_string("| **Итого** | 3 | 2 | 66.7% | 0.0% | 0 |"),
        "Run does not score the baseline that always answers match",
    )


def test_run_leaves_holdout_out_by_default(tmp_path: Path) -> None:
    gold = _gold(tmp_path / "gold", "35,35,sum,match,sure\n")
    (gold / "70.csv").write_text(
        "declaration,shipment,field,status\n70,70,sum,match\n70,70,cargo,match\n", encoding="utf-8"
    )
    main(
        [
            "run",
            "--gold",
            str(gold),
            "--manifest",
            str(_manifest(tmp_path / "manifest.yaml", {"35": "dev", "70": "holdout"})),
            "--out",
            str(tmp_path / "report.md"),
        ]
    )
    assert_that(
        (tmp_path / "report.md").read_text(encoding="utf-8"),
        contains_string("В расчёте: случаев 1, деклараций 1"),
        "Run does not leave the holdout part out by default",
    )


def test_run_counts_holdout_on_request(tmp_path: Path) -> None:
    gold = _gold(tmp_path / "gold", "35,35,sum,match,sure\n")
    (gold / "70.csv").write_text(
        "declaration,shipment,field,status\n70,70,sum,match\n70,70,cargo,match\n", encoding="utf-8"
    )
    main(
        [
            "run",
            "--gold",
            str(gold),
            "--manifest",
            str(_manifest(tmp_path / "manifest.yaml", {"35": "dev", "70": "holdout"})),
            "--part",
            "holdout",
            "--out",
            str(tmp_path / "report.md"),
        ]
    )
    assert_that(
        (tmp_path / "report.md").read_text(encoding="utf-8"),
        contains_string("Эталон: версия v7, часть holdout."),
        "Run does not count the holdout part with the gold version on request",
    )


def test_run_refuses_parsed_pipeline_without_real_folder(tmp_path: Path) -> None:
    assert_that(
        main(
            [
                "run",
                "--gold",
                str(_gold(tmp_path / "gold", "35,35/1,sum,match,sure\n")),
                "--manifest",
                str(_manifest(tmp_path / "manifest.yaml", {"35": "dev"})),
                "--pipeline",
                "parsed",
                "--real",
                str(tmp_path / "absent"),
                "--out",
                str(tmp_path / "report.md"),
            ]
        ),
        equal_to(1),
        "Run does not refuse the parsed pipeline without a folder of real declarations",
    )


def test_run_lists_places_that_parser_did_not_find(tmp_path: Path) -> None:
    _declaration(tmp_path / "real" / "35" / "35.xlsx", 35, "0000T00GR0000", 2)
    main(
        [
            "run",
            "--gold",
            str(_gold(tmp_path / "gold", "35,35/1,sum,review,sure\n35,35/3,sum,match,sure\n")),
            "--manifest",
            str(_manifest(tmp_path / "manifest.yaml", {"35": "dev"})),
            "--pipeline",
            "parsed",
            "--real",
            str(tmp_path / "real"),
            "--cards",
            str(_cards(tmp_path / "cards")),
            "--out",
            str(tmp_path / "report.md"),
        ]
    )
    assert_that(
        (tmp_path / "report.md").read_text(encoding="utf-8"),
        contains_string("- 35: нет ответа (1): 35/3 × sum"),
        "Run does not list a gold place that the parser did not find",
    )


def _rules(folder: Path) -> Path:
    folder.mkdir()
    (folder / "cargo.yaml").write_text(
        "field: cargo\nforms:\n  psg: {order: 5, title: Наименование груза}\n"
        "subject: Груз\nclause: none\ncheck: filled\nrule: Поле заполнено\nif_empty: mismatch\n"
        'comments: {match: "Заполнено", mismatch: "Пусто", review: "Проверить"}\nstatus: draft\n',
        encoding="utf-8",
    )
    return folder


def test_run_checks_declarations_by_rule_cards(tmp_path: Path) -> None:
    _declaration(tmp_path / "real" / "35" / "35.xlsx", 35, "0000T00GR0000", 2)
    main(
        [
            "run",
            "--gold",
            str(_gold(tmp_path / "gold", "35,35/1,cargo,match,sure\n35,35/2,cargo,match,sure\n")),
            "--manifest",
            str(_manifest(tmp_path / "manifest.yaml", {"35": "dev"})),
            "--pipeline",
            "checked",
            "--real",
            str(tmp_path / "real"),
            "--cards",
            str(_rules(tmp_path / "cards")),
            "--out",
            str(tmp_path / "report.md"),
        ]
    )
    assert_that(
        (tmp_path / "report.md").read_text(encoding="utf-8"),
        contains_string("| **Итого** | 2 | 2 | 100.0% | 0.0% | 0 |"),
        "Run does not check the declarations by the rule cards",
    )


def test_run_scores_fields_decided_without_policy_apart(tmp_path: Path) -> None:
    _declaration(tmp_path / "real" / "35" / "35.xlsx", 35, "0000T00GR0000", 1)
    main(
        [
            "run",
            "--gold",
            str(_gold(tmp_path / "gold", "35,35,cargo,match,sure\n")),
            "--manifest",
            str(_manifest(tmp_path / "manifest.yaml", {"35": "dev"})),
            "--pipeline",
            "checked",
            "--real",
            str(tmp_path / "real"),
            "--cards",
            str(_rules(tmp_path / "cards")),
            "--standalone",
            "cargo,sealing",
            "--out",
            str(tmp_path / "report.md"),
        ]
    )
    assert_that(
        (tmp_path / "report.md").read_text(encoding="utf-8"),
        contains_string("Поля: cargo, sealing."),
        "Run does not score the fields decided without a policy apart",
    )


def test_template_writes_marking_file_named_by_declaration(tmp_path: Path) -> None:
    number = random.randint(100, 999)
    _declaration(tmp_path / "d.xlsx", number, "0000T00GR0000", 2)
    main(
        [
            "template",
            str(tmp_path / "d.xlsx"),
            "--out",
            str(tmp_path / "out"),
            "--cards",
            str(_cards(tmp_path / "cards")),
        ]
    )
    assert_that(
        openpyxl.load_workbook(tmp_path / "out" / f"{number} – разметка.xlsx")["Разметка"].max_row,
        equal_to(5),
        "Template does not write one row per shipment and field into a file named by number",
    )


def test_load_writes_masked_gold_from_filled_templates(tmp_path: Path) -> None:
    _declaration(tmp_path / "d.xlsx", 35, "0000T00GR0000", 1)
    cards = _cards(tmp_path / "cards")
    main(
        ["template", str(tmp_path / "d.xlsx"), "--out", str(tmp_path / "in"), "--cards", str(cards)]
    )
    _fill(tmp_path / "in" / "35 – разметка.xlsx", "не совпадает", "уверен")
    main(
        [
            "load",
            str(tmp_path / "in"),
            "--gold",
            str(tmp_path / "gold"),
            "--cards",
            str(cards),
            "--glossary",
            str(tmp_path / "glossary.txt"),
        ]
    )
    assert_that(
        (tmp_path / "gold" / "35.csv").read_text(encoding="utf-8").splitlines()[1],
        equal_to("35,35,cargo,mismatch,sure,fsc-expert,п. 12 ГП,Сумма выше лимита Организация-1,"),
        "Load does not write a masked gold line from a filled template",
    )


def test_load_writes_nothing_when_marking_has_mistakes(tmp_path: Path) -> None:
    _declaration(tmp_path / "d.xlsx", 35, "0000T00GR0000", 1)
    cards = _cards(tmp_path / "cards")
    main(
        ["template", str(tmp_path / "d.xlsx"), "--out", str(tmp_path / "in"), "--cards", str(cards)]
    )
    _fill(tmp_path / "in" / "35 – разметка.xlsx", "почти совпадает", "уверен")
    main(["load", str(tmp_path / "in"), "--gold", str(tmp_path / "gold"), "--cards", str(cards)])
    assert_that(
        (tmp_path / "gold").exists(),
        equal_to(False),
        "Load does not refuse to write the gold when the marking has mistakes",
    )


def test_split_keeps_declarations_of_one_policy_in_one_part(tmp_path: Path) -> None:
    for number in (11, 12, 13):
        _declaration(tmp_path / "real" / f"{number}.xlsx", number, "0000T00GR0001", 1)
    _declaration(tmp_path / "real" / "14.xlsx", 14, "0000T00GR0002", 1)
    (tmp_path / "gold").mkdir()
    for number in (11, 12, 13, 14):
        (tmp_path / "gold" / f"{number}.csv").write_text(
            f"declaration,shipment,field,status\n{number},{number},sum,match\n", encoding="utf-8"
        )
    (tmp_path / "manifest.yaml").write_text("version: v1\nlog: []\n", encoding="utf-8")
    main(
        [
            "split",
            "--gold",
            str(tmp_path / "gold"),
            "--manifest",
            str(tmp_path / "manifest.yaml"),
            "--real",
            str(tmp_path / "real"),
        ]
    )
    entries = yaml.safe_load((tmp_path / "manifest.yaml").read_text(encoding="utf-8"))[
        "declarations"
    ]
    assert_that(
        len({entries[number]["part"] for number in ("11", "12", "13")}),
        equal_to(1),
        "Split does not keep the declarations of one policy in one part",
    )


def test_gold_builds_gold_from_marks(tmp_path: Path) -> None:
    (tmp_path / "source" / "97").mkdir(parents=True)
    book = openpyxl.Workbook()
    sheet = book.create_sheet("Лист1", 0)
    sheet.append(("Номер", "Поле", "Пункт", "Результат", "Комментарий", "ФСЦ"))
    sheet.append(("97", "Страховая сумма", "Лимит", "не совпадает", "ООО «Ромашка»", "верно"))
    book.save(tmp_path / "source" / "97" / "97 – результат проверки.xlsx")
    (tmp_path / "cards").mkdir()
    (tmp_path / "cards" / "sum.yaml").write_text(
        'field: sum\nforms:\n  vertical: {order: 6, title: "Страховая сумма"}\n', encoding="utf-8"
    )
    (tmp_path / "settings.yaml").write_text(
        'forms: {"97": vertical}\nunmapped: {}\n', encoding="utf-8"
    )
    main(
        [
            "gold",
            "--source",
            str(tmp_path / "source"),
            "--cards",
            str(tmp_path / "cards"),
            "--settings",
            str(tmp_path / "settings.yaml"),
            "--glossary",
            str(tmp_path / "glossary.txt"),
            "--out",
            str(tmp_path / "gold"),
            "--questions",
            str(tmp_path / "questions.md"),
            "--summary",
            str(tmp_path / "summary.md"),
        ]
    )
    assert_that(
        (tmp_path / "gold" / "97.csv").read_text(encoding="utf-8"),
        equal_to(
            "declaration,shipment,field,status,confidence,basis,clause,reason,note\n"
            "97,97,sum,mismatch,sure,fsc-ok,,,\n"
        ),
        "Gold does not build a gold line from a plain right mark",
    )


def test_mask_writes_masked_copy(tmp_path: Path) -> None:
    (tmp_path / "source.txt").write_text("Страхователь ООО «Ромашка»\n", encoding="utf-8")
    (tmp_path / "glossary.txt").write_text("Москва\n", encoding="utf-8")
    main(
        [
            "mask",
            str(tmp_path / "source.txt"),
            str(tmp_path / "target.txt"),
            "--glossary",
            str(tmp_path / "glossary.txt"),
        ]
    )
    assert_that(
        (tmp_path / "target.txt").read_text(encoding="utf-8"),
        equal_to("Страхователь Организация-1\n"),
        "Mask command does not write a masked copy",
    )
