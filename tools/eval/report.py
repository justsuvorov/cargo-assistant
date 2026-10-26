from collections import Counter
from collections.abc import Mapping
from typing import Final, Protocol, final

from app.domain.status import Review
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

    def _first(self, sample: Sample) -> tuple[Verdict, ...]:
        return tuple(
            verdict
            for verdict in self._answers.get(sample.declaration(), ())
            if verdict.place().same(sample.place())
        )[:1]


@final
class Report:
    """Eval report: accuracy and review share by field, time and model calls by declaration."""

    __slots__ = ("_gold", "_laps", "_title")

    def __init__(self, title: str, gold: Gold, laps: tuple[Lap, ...]) -> None:
        self._title: Final = title
        self._gold: Final = gold
        self._laps: Final = laps

    def text(self) -> str:
        samples = self._gold.samples()
        return "\n".join(
            (
                f"# Отчёт eval: {self._title}",
                "",
                *self._preamble(samples),
                "",
                "## Точность по полям",
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
                *self._budget(samples),
                "",
            )
        )

    def _answers(self) -> dict[str, tuple[Verdict, ...]]:
        return {lap.declaration(): lap.verdicts() for lap in self._laps}

    def _preamble(self, samples: tuple[Sample, ...]) -> tuple[str, ...]:
        expected = Counter(sample.status().text() for sample in samples)
        declarations = len({sample.declaration() for sample in samples})
        return (
            "Сравнение только с эталоном. Единица — строка «поле × перевозка». "
            "«Требует проверки» засчитывается, только если эталон ожидает «требует проверки».",
            "",
            f"Эталон: случаев {len(samples)}, деклараций {declarations}. Ожидается: "
            + ", ".join(
                f"«{text}» {count} ({count / len(samples):.1%})"
                for text, count in sorted(expected.items())
            )
            + ".",
        )

    def _header(self, title: str) -> str:
        return f"| {title} | Случаев | Верно | Точность | Ответ «требует проверки» | Нет ответа |"

    def _fields(self, samples: tuple[Sample, ...]) -> tuple[str, ...]:
        answers = self._answers()
        return (
            self._header("Поле"),
            "|---|---|---|---|---|---|",
            *(
                Tally(tuple(s for s in samples if s.place().field() == field), answers).row(field)
                for field in sorted({sample.place().field() for sample in samples})
            ),
            Tally(samples, answers).row("**Итого**"),
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

    def _budget(self, samples: tuple[Sample, ...]) -> tuple[str, ...]:
        places = {
            (sample.declaration(), sample.place().shipment(), sample.place().field())
            for sample in samples
        }
        extra = sum(
            1
            for lap in self._laps
            for verdict in lap.verdicts()
            if (lap.declaration(), verdict.place().shipment(), verdict.place().field())
            not in places
        )
        slowest = max(self._laps, key=lambda lap: lap.seconds())
        mean = sum(lap.seconds() for lap in self._laps) / len(self._laps)
        return (
            f"Время на декларацию: среднее {mean:.3f} с, "
            f"максимум {slowest.seconds():.3f} с (декл. {slowest.declaration()}).",
            "",
            f"Вызовов LLM: всего {sum(lap.calls() for lap in self._laps)}, "
            f"максимум на декларацию {max(lap.calls() for lap in self._laps)}.",
            "",
            f"Ответов вне эталона: {extra}.",
        )
