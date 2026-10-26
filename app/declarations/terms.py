import re
from collections.abc import Mapping
from functools import cache
from typing import Final, Protocol, final


class Phrase(Protocol):
    """Text of a label brought to the form in which labels in RU and EN are compared."""

    def text(self) -> str: ...


class Lexicon(Protocol):
    """Vocabulary of labels that answers which field key a label text names, empty if none."""

    def key(self, text: str) -> str: ...


@final
class Folded:
    """Label in lower case without list number, spaces around hyphens and closing colon."""

    __slots__ = ("_text",)

    def __init__(self, text: str) -> None:
        self._text: Final = text

    def text(self) -> str:
        lowered = self._text.casefold().replace("ё", "е")
        hyphened = re.sub(r"\s*-\s*", "-", lowered)
        spaced = re.sub(r"\s+", " ", hyphened).strip()
        return re.sub(r"^\d+\s*\.\s*", "", spaced).strip(" :*")


@cache
def _pattern(variants: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(
        "(?:" + "|".join(re.escape(Folded(variant).text()) for variant in variants) + r")(?!\w)"
    )


@final
class Terms:
    """Vocabulary where a label names a key if it starts with one of the variants of the key."""

    __slots__ = ("_table",)

    def __init__(self, table: Mapping[str, tuple[str, ...]]) -> None:
        self._table: Final = table

    def key(self, text: str) -> str:
        folded = Folded(text).text()
        return next(
            (key for key, variants in self._table.items() if _pattern(variants).match(folded)),
            "",
        )


@final
class VerticalTerms:
    """Labels of the fields of a vertical declaration in Russian and English."""

    __slots__ = ()

    def key(self, text: str) -> str:
        return Terms(
            {
                "cargo": (
                    "полное наименование груза",
                    "наименование груза",
                    "full description of cargo",
                    "description of cargo",
                    "cargo description",
                    "name of cargo",
                ),
                "packaging": ("род упаковки", "type of packaging", "packaging"),
                "beneficiary": ("выгодоприобретатель", "beneficiary"),
                "sum": ("страховая сумма", "sum insured", "insured amount", "insured sum"),
                "document": (
                    "товарно-транспортная накладная",
                    "транспортная накладная",
                    "consignment note",
                    "waybill",
                    "transport document",
                ),
                "transport": ("транспорт", "mode of transport", "type of transport", "transport"),
                "departure": ("пункт отправления", "point of departure", "place of departure"),
                "transshipment": (
                    "пункт перегрузки",
                    "point of transshipment",
                    "place of transshipment",
                ),
                "destination": ("пункт назначения", "point of destination", "place of destination"),
                "period": ("период страхования", "insurance period", "period of insurance"),
                "carrier": ("перевозчик", "carrier"),
                "sealing": ("пломбирование", "sealing"),
                "other": (
                    "прочие сведения",
                    "other information",
                    "other details",
                    "additional information",
                ),
            }
        ).key(text)


@final
class ColumnTerms:
    """Labels of the columns of a table declaration in Russian and English."""

    __slots__ = ()

    def key(self, text: str) -> str:
        return Terms(
            {
                "number": ("№ п/п", "№ пп", "п/п", "item no", "item", "no.", "#"),
                "period_start": ("начало", "start date", "start", "beginning", "begin"),
                "period_end": ("окончание", "end date", "end", "finish"),
                "cargo": (
                    "наименование груза",
                    "name of cargo",
                    "description of cargo",
                    "cargo description",
                    "cargo",
                ),
                "beneficiary": ("выгодоприобретатель", "beneficiary"),
                "document_number": (
                    "номер товарно-транспортного",
                    "номер ттд",
                    "номер ттн",
                    "transport document number",
                    "transport document no",
                    "consignment note number",
                    "consignment note no",
                    "waybill number",
                    "waybill no",
                ),
                "document_date": (
                    "дата товарно-транспортного",
                    "дата ттд",
                    "дата ттн",
                    "transport document date",
                    "consignment note date",
                    "waybill date",
                ),
                "transport": ("вид транспорта", "mode of transport", "type of transport"),
                "departure": (
                    "пункт отправления",
                    "point of departure",
                    "place of departure",
                    "departure",
                ),
                "transshipment": (
                    "пункт перегрузки",
                    "point of transshipment",
                    "place of transshipment",
                    "transshipment",
                ),
                "destination": (
                    "пункт назначения",
                    "point of destination",
                    "place of destination",
                    "destination",
                ),
                "sum": ("страховая сумма", "sum insured", "insured amount", "insured sum"),
                "currency": ("валюта", "currency"),
                "carrier": ("наименование перевозчика", "перевозчик", "carrier name", "carrier"),
            }
        ).key(text)
