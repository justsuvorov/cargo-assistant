import re
from collections.abc import Iterable
from typing import Final, Protocol, final


class Mask(Protocol):
    """Replacement of client names, tax numbers, policy numbers, addresses and persons by stubs."""

    def hide(self, text: str) -> str: ...


@final
class Anonymity:
    """Mask that numbers sensitive fragments of a corpus by kind in order of first appearance."""

    __slots__ = ("_corpus", "_glossary")

    def __init__(self, corpus: Iterable[str], glossary: Iterable[str]) -> None:
        self._corpus: Final = tuple(corpus)
        self._glossary: Final = tuple(
            sorted({name.strip() for name in glossary} - {""}, key=len, reverse=True)
        )

    def hide(self, text: str) -> str:
        stubs = self._stubs(text)
        return self._pattern().sub(lambda match: stubs[self._key(match)], text)

    def _stubs(self, text: str) -> dict[tuple[str, str], str]:
        found = tuple(
            dict.fromkeys(
                self._key(match)
                for source in (*self._corpus, text)
                for match in self._pattern().finditer(source)
            )
        )
        titles = self._titles()
        return {
            key: f"{titles[key[0]]}-{sum(1 for other in found[: index + 1] if other[0] == key[0])}"
            for index, key in enumerate(found)
        }

    def _key(self, match: re.Match[str]) -> tuple[str, str]:
        return (str(match.lastgroup), " ".join(match.group().casefold().split()))

    def _titles(self) -> dict[str, str]:
        return {
            "name": "Название",
            "mail": "Почта",
            "policy": "ГП",
            "inn": "ИНН",
            "company": "Организация",
            "person": "Лицо",
            "address": "Адрес",
        }

    def _pattern(self) -> re.Pattern[str]:
        opf = r"\b(?:ООО|ОАО|ЗАО|ПАО|НАО|АО|ТОО|ИП)\b"
        street = (
            r"(?i:ул\.|улица|пер\.|переулок|пр-д|проезд|просп\.|проспект|пр-т|шоссе|ш\.|наб\."
            r"|набережная|бульвар|б-р|пл\.|площадь)"
        )
        part = r",\s*(?:(?i:д\.|дом|корп\.|к\.|стр\.|эт\.|офис\.?|оф\.|вл\.?|кв\.)|\d)[^,;\n]*"
        names = "|".join(re.escape(name) for name in self._glossary) or r"(?!x)x"
        return re.compile(
            "|".join(
                (
                    rf"(?P<name>(?i:{names}))",
                    r"(?P<mail>[\w.+-]+@[\w-]+(?:\.[\w-]+)+)",
                    r"(?P<policy>\b\d{4}[0-9A-Z$]\d{2}[A-Z]{1,2}\d{4,5}\b)",
                    r"(?P<inn>(?:ИНН\s*:?\s*)?\b\d{10}(?:\d{2})?\b)",
                    rf"(?P<company>{opf}(?:\s+[А-ЯЁ]{{2,}})?\s*[«„“\"]"
                    r"(?:[^«»„“”\"\n]*«[^«»\n]*»[»“”\"]?|[^«»„“”\"\n]*[»“”\"])"
                    rf"|{opf}\s+[А-ЯЁA-Z][\w-]*(?:\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.)?"
                    r"|\b[A-Z][\w&'.-]*(?:\s+[A-Z][\w&'.-]*)*,?\s+"
                    r"(?:LLC|LTD|Ltd|Inc|GmbH|LLP|Co\.,?\s*Ltd)\b\.?)",
                    r"(?P<person>\b[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+[А-ЯЁ]\.\s?[А-ЯЁ]\."
                    r"|\b[А-ЯЁ]\.\s?[А-ЯЁ]\.\s?[А-ЯЁ][а-яё]+)",
                    rf"(?P<address>(?:\b[А-ЯЁ][а-яё-]+\s+)?\b{street}[^,;\n]*(?:{part})*"
                    r"|[^,;\n]*\b(?:Road|Street|Avenue|Building)\b[^,;\n]*"
                    r"|\b\d{6}\b)",
                )
            )
        )
