from pathlib import Path

import openpyxl
from hamcrest import assert_that, contains_string, equal_to

from tools.eval.cli import main


def test_run_writes_report_of_stub_pipeline(tmp_path: Path) -> None:
    (tmp_path / "gold").mkdir()
    (tmp_path / "gold" / "97.csv").write_text(
        "declaration,shipment,field,status,basis,note\n97,97,sum,mismatch,D-23,\n"
        "97,97,cargo,review,fsc-note,\n",
        encoding="utf-8",
    )
    main(["run", "--gold", str(tmp_path / "gold"), "--out", str(tmp_path / "report.md")])
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
        equal_to("declaration,shipment,field,status,basis,note\n97,97,sum,mismatch,fsc-ok,\n"),
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
