from collections import Counter
from collections.abc import Mapping
from typing import Final, Protocol, final

from app.domain.status import Match, Mismatch, Review, Status
from app.domain.verdict import Verdict
from tools.eval.gold import Gold, Sample
from tools.eval.session import Lap


class Score(Protocol):
    """Counts of gold cases that a run answered right, answered with review or left unanswered."""

    def cases(self) -> int: ...

    def correct(self) -> int: ...

    def doubts(self) -> int: ...

    def missing(self) -> int: ...

    def row(self, title: str) -> str: ...

    def spread(self) -> str: ...


class Page(Protocol):
    """Text of a document produced by eval."""

    def text(self) -> str: ...


@final
class Tally:
    """Score of a group of gold cases against the first verdict found in the same place."""

    __slots__ = ("_answers", "_samples")

    def __init__(
        self, samples: tuple[Sample, ...], answers: Mapping[str, tuple[Verdict, ...]]
    ) -> None:
        self._samples: Final = samples
        self._answers: Final = answers

    def cases(self) -> int:
        return len(self._samples)

    def correct(self) -> int:
        return sum(1 for sample in self._samples for v in self._first(sample) if sample.agrees(v))

    def doubts(self) -> int:
        return sum(
            1
            for sample in self._samples
            for verdict in self._first(sample)
            if verdict.status().key() == Review().key()
        )

    def missing(self) -> int:
        return sum(1 for sample in self._samples if not self._first(sample))

    def row(self, title: str) -> str:
        total = max(self.cases(), 1)
        return (
            f"| {title} | {self.cases()} | {self.correct()} | {self.correct() / total:.1%} "
            f"| {self.doubts() / total:.1%} | {self.missing()} |"
        )

    def spread(self) -> str:
        return " ".join(self._hits(status) for status in (Match(), Mismatch(), Review()))

    def _hits(self, status: Status) -> str:
        expected = tuple(s for s in self._samples if s.status().key() == status.key())
        answered = tuple(
            sample
            for sample in self._samples
            for verdict in self._first(sample)
            if verdict.status().key() == status.key()
        )
        found = sum(1 for sample in answered if sample.status().key() == status.key())
        return f"{found}/{len(expected)} | {len(answered) - found} |"

    def _first(self, sample: Sample) -> tuple[Verdict, ...]:
        return tuple(
            verdict
            for verdict in self._answers.get(sample.declaration(), ())
            if sample.place().same(verdict.place())
        )[:1]


@final
class Report:
    """Eval report: accuracy and review share by field, time and model calls by declaration.

    Only sure gold lines are scored; disputed ones still count as gold places when the report
    lists places that the pipeline missed or answered beyond the gold.
    """

    __slots__ = ("_edition", "_gold", "_laps", "_title")

    def __init__(self, title: str, edition: str, gold: Gold, laps: tuple[Lap, ...]) -> None:
        self._title: Final = title
        self._edition: Final = edition
        self._gold: Final = gold
        self._laps: Final = laps

    def text(self) -> str:
        everything = self._gold.samples()
        samples = tuple(sample for sample in everything if sample.sure())
        return "\n".join(
            (
                f"# Отчёт eval: {self._title}",
                "",
                *self._preamble(samples, len(everything) - len(samples)),
                "",
                "## Точность по полям",
                "",
                "«Найдено» — сколько строк с этим ожидаемым статусом получили его в ответе; "
                "«лишних» — сколько строк получили этот статус, хотя эталон ждёт другой "
                "(диагностика, методика точности не меняется, D-25).",
                "",
                *self._fields(samples),
                "",
                "## Точность по ожидаемому статусу",
                "",
                "Доля найденных случаев каждого ожидаемого статуса: заглушка «всё совпадает» "
                "набирает высокую общую точность, но не находит ни одного «не совпадает».",
                "",
                *self._statuses(samples),
                "",
                "## Декларации",
                "",
                *self._declarations(samples),
                "",
                *self._budget(everything),
                "",
                "## Места эталона и ответа",
                "",
                "«Нет ответа» — место есть в эталоне (в том числе в спорной строке), но ответа "
                "в нём нет; «лишний» — ответ в месте, которого нет в эталоне.",
                "",
                *(self._gaps(everything) or ("Расхождений мест нет.",)),
                "",
            )
        )

    def _answers(self) -> dict[str, tuple[Verdict, ...]]:
        return {lap.declaration(): lap.verdicts() for lap in self._laps}

    def _preamble(self, samples: tuple[Sample, ...], disputed: int) -> tuple[str, ...]:
        expected = Counter(sample.status().text() for sample in samples)
        declarations = len({sample.declaration() for sample in samples})
        return (
            "Сравнение только с эталоном. Единица — строка «поле × перевозка». "
            "«Требует проверки» засчитывается, только если эталон ожидает «требует проверки».",
            "",
            f"Эталон: {self._edition}.",
            "",
            f"В расчёте: случаев {len(samples)}, деклараций {declarations}; спорных строк "
            f"вне расчёта {disputed}. Ожидается: "
            + ", ".join(
                f"«{text}» {count} ({count / max(len(samples), 1):.1%})"
                for text, count in sorted(expected.items())
            )
            + ".",
        )

    def _header(self, title: str) -> str:
        return f"| {title} | Случаев | Верно | Точность | Ответ «требует проверки» | Нет ответа |"

    def _fields(self, samples: tuple[Sample, ...]) -> tuple[str, ...]:
        answers = self._answers()
        return (
            self._header("Поле")
            + " «совпадает»: найдено | лишних | «не совпадает»: найдено | лишних "
            "| «требует проверки»: найдено | лишних |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|",
            *(
                tally.row(field) + " " + tally.spread()
                for field in sorted({sample.place().field() for sample in samples})
                for tally in (
                    Tally(tuple(s for s in samples if s.place().field() == field), answers),
                )
            ),
            Tally(samples, answers).row("**Итого**") + " " + Tally(samples, answers).spread(),
        )

    def _statuses(self, samples: tuple[Sample, ...]) -> tuple[str, ...]:
        answers = self._answers()
        return (
            self._header("Ожидается"),
            "|---|---|---|---|---|---|",
            *(
                Tally(tuple(s for s in samples if s.status().text() == text), answers).row(text)
                for text in sorted({sample.status().text() for sample in samples})
            ),
        )

    def _declarations(self, samples: tuple[Sample, ...]) -> tuple[str, ...]:
        answers = self._answers()
        return (
            f"{self._header('Декларация')} Время, с | Вызовов LLM |",
            "|---|---|---|---|---|---|---|---|",
            *(
                Tally(
                    tuple(s for s in samples if s.declaration() == lap.declaration()), answers
                ).row(lap.declaration())
                + f" {lap.seconds():.3f} | {lap.calls()} |"
                for lap in self._laps
            ),
        )

    def _budget(self, everything: tuple[Sample, ...]) -> tuple[str, ...]:
        slowest = max(self._laps, key=lambda lap: lap.seconds())
        mean = sum(lap.seconds() for lap in self._laps) / len(self._laps)
        return (
            f"Время на декларацию: среднее {mean:.3f} с, "
            f"максимум {slowest.seconds():.3f} с (декл. {slowest.declaration()}).",
            "",
            f"Вызовов LLM: всего {sum(lap.calls() for lap in self._laps)}, "
            f"максимум на декларацию {max(lap.calls() for lap in self._laps)}.",
            "",
            f"Ответов вне эталона: {sum(len(self._extra(lap, everything)) for lap in self._laps)}.",
        )

    def _gaps(self, everything: tuple[Sample, ...]) -> tuple[str, ...]:
        return tuple(
            f"- {lap.declaration()}: {text}"
            for lap in self._laps
            for missing in (self._missing(lap, everything),)
            for extra in (self._extra(lap, everything),)
            for text in (
                *(f"причина: {fault}" for fault in lap.faults()),
                *((f"нет ответа ({len(missing)}): {', '.join(missing)}",) if missing else ()),
                *((f"лишних ({len(extra)}): {', '.join(extra)}",) if extra else ()),
            )
        )

    def _missing(self, lap: Lap, everything: tuple[Sample, ...]) -> tuple[str, ...]:
        return tuple(
            f"{sample.place().shipment()} × {sample.place().field()}"
            for sample in everything
            if sample.declaration() == lap.declaration()
            if not any(sample.place().same(verdict.place()) for verdict in lap.verdicts())
        )

    def _extra(self, lap: Lap, everything: tuple[Sample, ...]) -> tuple[str, ...]:
        own = tuple(s for s in everything if s.declaration() == lap.declaration())
        return tuple(
            f"{verdict.place().shipment()} × {verdict.place().field()}"
            for verdict in lap.verdicts()
            if not any(sample.place().same(verdict.place()) for sample in own)
        )
