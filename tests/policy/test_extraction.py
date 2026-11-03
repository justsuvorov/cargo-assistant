import json
import random
import uuid
from datetime import date
from decimal import Decimal

from hamcrest import assert_that, empty, equal_to, has_item, has_length, is_not, raises

from app.llm.errors import MisconfiguredError
from app.llm.fake import FakeModel
from app.llm.ledger import Memory, Route
from app.llm.model import Strict
from app.policy.extraction import Extraction
from app.policy.package import Amendment, Paper
from app.policy.schema.profile import Sum
from tests.llm.stub import Scripted


class Sheet:
    """Fictional paper that reads as the given text."""

    def __init__(self, text: str) -> None:
        self._text = text

    def reference(self) -> str:
        return "Файл ГП"

    def text(self) -> str:
        return self._text


class Signed:
    """Fictional amendment with the given requisites."""

    def __init__(
        self, number: int, text: str, effective: date, scope: tuple[str, ...] = ()
    ) -> None:
        self._number = number
        self._text = text
        self._effective = effective
        self._scope = scope

    def reference(self) -> str:
        return f"Файл ДС {self._number}"

    def text(self) -> str:
        return self._text

    def number(self) -> int:
        return self._number

    def effective(self) -> date:
        return self._effective

    def scope(self) -> tuple[str, ...]:
        return self._scope


class Bundle:
    """Fictional package of a policy paper, its amendments and whatever else is given by name."""

    def __init__(
        self, policy: Paper, amendments: tuple[Amendment, ...] = (), **rest: tuple[str, ...]
    ) -> None:
        self._policy = policy
        self._amendments = amendments
        self._rest = rest

    def policy(self) -> Paper:
        return self._policy

    def amendments(self) -> tuple[Amendment, ...]:
        return self._amendments

    def conditions(self) -> tuple[str, ...]:
        return self._rest.get("conditions", ())

    def carriers(self) -> tuple[str, ...]:
        return self._rest.get("carriers", ())

    def problems(self) -> tuple[str, ...]:
        return self._rest.get("problems", ())


def passage(key: str, point: str = "", text: str = "", **values: list[object]) -> dict[str, object]:
    return {
        "key": key,
        "point": point,
        "text": text,
        "dates": values.get("dates", []),
        "amounts": values.get("amounts", []),
        "entries": values.get("entries", []),
    }


def reading(*passages: dict[str, object]) -> str:
    return json.dumps({"passages": passages}, ensure_ascii=False)


def test_takes_the_number_of_the_policy_from_its_text() -> None:
    number = uuid.uuid4().hex
    assert_that(
        Extraction(
            Bundle(Sheet(f"Генеральный полис № {number}")),
            FakeModel({"profile.policy": reading(passage("number", text=number))}),
        )
        .profile()
        .number,
        equal_to(number),
        "Number of the policy is not taken from its text",
    )


def test_takes_the_issue_date_of_the_policy_from_its_text() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("Полис № 7 от «22» декабря 2025 г.")),
            FakeModel(
                {"profile.policy": reading(passage("number", text="7", dates=["2025-12-22"]))}
            ),
        )
        .profile()
        .issued,
        equal_to(date(2025, 12, 22)),
        "Issue date of the policy is not taken from its text",
    )


def test_takes_the_insurer_of_the_policy_from_its_text() -> None:
    insurer = uuid.uuid4().hex
    assert_that(
        Extraction(
            Bundle(Sheet(f"Страхователь: {insurer}")),
            FakeModel({"profile.policy": reading(passage("insurer", text=insurer))}),
        )
        .profile()
        .insurer,
        equal_to(insurer),
        "Insurer of the policy is not taken from its text",
    )


def test_keeps_the_requisites_of_the_policy_out_of_its_clauses() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("Полис № 7 от 22.12.2025, страхователь Икс")),
            FakeModel(
                {
                    "profile.policy": reading(
                        passage("number", text="7", dates=["2025-12-22"]),
                        passage("insurer", text="Икс"),
                    )
                }
            ),
        )
        .profile()
        .clauses,
        equal_to({}),
        "Requisites of the policy are not kept out of its clauses",
    )


def test_drops_a_requisite_of_the_policy_changed_by_an_amendment() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("Полис"), (Signed(2, "Пункт 1 принять: Игрек", date(2026, 3, 1)),)),
            FakeModel(
                {
                    "profile.policy": reading(),
                    "profile.amendment.2": reading(passage("insurer", "1", "Игрек")),
                }
            ),
        )
        .profile()
        .clauses,
        equal_to({}),
        "Requisite of the policy changed by an amendment is not dropped",
    )


def test_records_a_requisite_of_the_policy_changed_by_an_amendment() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("Полис"), (Signed(2, "Пункт 1 принять: Игрек", date(2026, 3, 1)),)),
            FakeModel(
                {
                    "profile.policy": reading(),
                    "profile.amendment.2": reading(passage("insurer", "1", "Игрек")),
                }
            ),
        )
        .profile()
        .problems,
        has_item("Файл ДС 2: документ меняет реквизит insurer полиса, его проверяет эксперт"),
        "Requisite of the policy changed by an amendment is not recorded in problems",
    )


def test_drops_a_policy_number_that_its_text_does_not_hold() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("Полис № 7")),
            FakeModel({"profile.policy": reading(passage("number", text=uuid.uuid4().hex))}),
        )
        .profile()
        .number,
        equal_to(""),
        "Policy number that its text does not hold is not dropped",
    )


def test_drops_an_insurer_that_its_text_does_not_hold() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("Страхователь: Икс")),
            FakeModel({"profile.policy": reading(passage("insurer", text=uuid.uuid4().hex))}),
        )
        .profile()
        .insurer,
        equal_to(""),
        "Insurer that its text does not hold is not dropped",
    )


def test_records_a_policy_number_that_its_text_does_not_hold() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("Полис № 7")),
            FakeModel({"profile.policy": reading(passage("number", text=uuid.uuid4().hex))}),
        )
        .profile()
        .problems[0],
        equal_to("Файл ГП: значение условия number не найдено в тексте документа и отброшено"),
        "Policy number that its text does not hold is not recorded in problems",
    )


def test_records_a_policy_without_a_number() -> None:
    assert_that(
        Extraction(Bundle(Sheet("Полис")), FakeModel({"profile.policy": reading()}))
        .profile()
        .problems,
        has_item("Файл ГП: номер полиса не определён, его заполняет эксперт"),
        "Policy without a number is not recorded in problems",
    )


def test_records_a_policy_without_an_issue_date() -> None:
    assert_that(
        Extraction(Bundle(Sheet("Полис")), FakeModel({"profile.policy": reading()}))
        .profile()
        .problems,
        has_item("Файл ГП: дата полиса не определена, её заполняет эксперт"),
        "Policy without an issue date is not recorded in problems",
    )


def test_records_a_policy_without_an_insurer() -> None:
    assert_that(
        Extraction(Bundle(Sheet("Полис")), FakeModel({"profile.policy": reading()}))
        .profile()
        .problems,
        has_item("Файл ГП: страхователь не определён, его заполняет эксперт"),
        "Policy without an insurer is not recorded in problems",
    )


def test_policy_wording_takes_effect_on_the_issue_date_of_the_policy() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("Полис № 7 от 22.12.2025, срок с 01.01.2025 по 31.12.2026")),
            FakeModel(
                {
                    "profile.policy": reading(
                        passage("number", text="7", dates=["2025-12-22"]),
                        passage("term", "6", dates=["2025-01-01", "2026-12-31"]),
                    )
                }
            ),
        )
        .profile()
        .clauses["term"][0]
        .effective,
        equal_to(date(2025, 12, 22)),
        "Policy wording does not take effect on the issue date of the policy",
    )


def test_policy_wording_concerns_every_declaration() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("п. 5 | Грузы")),
            FakeModel({"profile.policy": reading(passage("object", "5", "Грузы"))}),
        )
        .profile()
        .clauses["object"][0]
        .scope,
        equal_to("all"),
        "Policy wording does not concern every declaration",
    )


def test_wordings_of_one_clause_differ_in_their_source() -> None:
    assert_that(
        [
            wording.source
            for wording in Extraction(
                Bundle(
                    Sheet("12.5. Лимит"),
                    (
                        Signed(26, "Подпункт 12.5. принять", date(2026, 3, 1)),
                        Signed(27, "Подпункт 12.5. принять", date(2026, 3, 1)),
                    ),
                ),
                FakeModel(
                    {
                        "profile.policy": reading(passage("limit", "12.5", "Лимит")),
                        "profile.amendment.26": reading(passage("limit", "12.5", "Лимит 26")),
                        "profile.amendment.27": reading(passage("limit", "12.5", "Лимит 27")),
                    }
                ),
            )
            .profile()
            .clauses["limit"]
        ],
        equal_to(["ГП п. 12.5", "ДС 26 п. 12.5", "ДС 27 п. 12.5"]),
        "Wordings of one clause do not differ in their source",
    )


def test_policy_wording_is_no_amendment() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("п. 5 | Грузы")),
            FakeModel({"profile.policy": reading(passage("object", "5", "Грузы"))}),
        )
        .profile()
        .clauses["object"][0]
        .amendment,
        equal_to(0),
        "Policy wording does not carry the amendment number zero",
    )


def test_policy_wording_refers_to_its_paper_and_point() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("п. 5 | Грузы")),
            FakeModel({"profile.policy": reading(passage("object", "5", "Грузы"))}),
        )
        .profile()
        .clauses["object"][0]
        .source,
        equal_to("ГП п. 5"),
        "Policy wording does not refer to its paper and point",
    )


def test_policy_wording_without_a_point_refers_to_its_paper() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("Грузы")),
            FakeModel({"profile.policy": reading(passage("object", text="Грузы"))}),
        )
        .profile()
        .clauses["object"][0]
        .source,
        equal_to("ГП"),
        "Policy wording without a point does not refer to its paper",
    )


def test_joins_the_passages_of_one_clause_into_one_wording() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("12. Лимит 100 000 рублей. 12.5. Лимит 200 000 рублей")),
            FakeModel(
                {
                    "profile.policy": reading(
                        passage("limit", "12", amounts=[{"value": "100000", "currency": "RUB"}]),
                        passage("limit", "12.5", amounts=[{"value": "200000", "currency": "RUB"}]),
                    )
                }
            ),
        )
        .profile()
        .clauses["limit"],
        has_length(1),
        "Passages of one clause are not joined into one wording",
    )


def test_joined_wording_refers_to_every_point() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("12. Лимит. 12.5. Лимит")),
            FakeModel(
                {
                    "profile.policy": reading(
                        passage("limit", "12", "Лимит"), passage("limit", "12.5", "Лимит")
                    )
                }
            ),
        )
        .profile()
        .clauses["limit"][0]
        .source,
        equal_to("ГП п. 12, 12.5"),
        "Joined wording does not refer to every point",
    )


def test_joined_wording_keeps_every_amount() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("12. Лимит 100 000 рублей. 12.5. Лимит 200 000 рублей")),
            FakeModel(
                {
                    "profile.policy": reading(
                        passage("limit", "12", amounts=[{"value": "100000", "currency": "RUB"}]),
                        passage("limit", "12.5", amounts=[{"value": "200000", "currency": "RUB"}]),
                    )
                }
            ),
        )
        .profile()
        .clauses["limit"][0]
        .amounts,
        has_length(2),
        "Joined wording does not keep every amount",
    )


def test_skips_a_passage_with_nothing_in_it() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("Полис"), (Signed(1, "Пункт 8 принять", date(2026, 3, 1)),)),
            FakeModel(
                {
                    "profile.policy": reading(),
                    "profile.amendment.1": reading(passage("transport", "8")),
                }
            ),
        )
        .profile()
        .clauses,
        equal_to({}),
        "Passage with nothing in it is not skipped",
    )


def test_amendment_number_comes_from_the_package() -> None:
    number = random.randint(1, 30)
    assert_that(
        Extraction(
            Bundle(Sheet("Полис"), (Signed(number, "Пункт 8 принять", date(2026, 3, 1)),)),
            FakeModel(
                {
                    "profile.policy": reading(),
                    f"profile.amendment.{number}": reading(passage("transport", "8", "Авиа")),
                }
            ),
        )
        .profile()
        .clauses["transport"][0]
        .amendment,
        equal_to(number),
        "Amendment number does not come from the package",
    )


def test_amendment_entry_into_force_comes_from_the_package() -> None:
    effective = date(random.randint(2000, 2030), random.randint(1, 12), random.randint(1, 28))
    assert_that(
        Extraction(
            Bundle(Sheet("Полис"), (Signed(1, "Пункт 8 принять", effective),)),
            FakeModel(
                {
                    "profile.policy": reading(),
                    "profile.amendment.1": reading(passage("transport", "8", "Авиа")),
                }
            ),
        )
        .profile()
        .clauses["transport"][0]
        .effective,
        equal_to(effective),
        "Entry into force of the amendment does not come from the package",
    )


def test_amendment_scope_comes_from_the_package() -> None:
    scope = (str(random.randint(1, 500)), str(random.randint(501, 999)))
    assert_that(
        Extraction(
            Bundle(Sheet("Полис"), (Signed(1, "Пункт 8 принять", date(2026, 3, 1), scope),)),
            FakeModel(
                {
                    "profile.policy": reading(),
                    "profile.amendment.1": reading(passage("transport", "8", "Авиа")),
                }
            ),
        )
        .profile()
        .clauses["transport"][0]
        .scope,
        equal_to(scope),
        "Scope of the amendment does not come from the package",
    )


def test_amendment_with_an_empty_scope_concerns_every_declaration() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("Полис"), (Signed(1, "Пункт 8 принять", date(2026, 3, 1)),)),
            FakeModel(
                {
                    "profile.policy": reading(),
                    "profile.amendment.1": reading(passage("transport", "8", "Авиа")),
                }
            ),
        )
        .profile()
        .clauses["transport"][0]
        .scope,
        equal_to("all"),
        "Amendment with an empty scope does not concern every declaration",
    )


def test_amendment_wording_refers_to_its_paper_and_point() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("Полис"), (Signed(4, "Пункт 8 принять", date(2026, 3, 1)),)),
            FakeModel(
                {
                    "profile.policy": reading(),
                    "profile.amendment.4": reading(passage("transport", "8", "Авиа")),
                }
            ),
        )
        .profile()
        .clauses["transport"][0]
        .source,
        equal_to("ДС 4 п. 8"),
        "Amendment wording does not refer to its paper and point",
    )


def test_amendment_adds_a_wording_to_the_clause_it_names() -> None:
    assert_that(
        Extraction(
            Bundle(
                Sheet("п. 8 Авто. п. 9 Россия"),
                (Signed(1, "Пункт 8 (Транспорт) принять: Авиа", date(2026, 3, 1)),),
            ),
            FakeModel(
                {
                    "profile.policy": reading(
                        passage("transport", "8", "Авто"), passage("territory", "9", "Россия")
                    ),
                    "profile.amendment.1": reading(passage("transport", "8", "Авиа")),
                }
            ),
        )
        .profile()
        .clauses["transport"],
        has_length(2),
        "Amendment does not add a wording to the clause it names",
    )


def test_clause_that_an_amendment_does_not_name_stays_from_the_policy() -> None:
    assert_that(
        [
            wording.source
            for wording in Extraction(
                Bundle(
                    Sheet("п. 8 Авто. п. 9 Россия"),
                    (Signed(1, "Пункт 8 (Транспорт) принять: Авиа", date(2026, 3, 1)),),
                ),
                FakeModel(
                    {
                        "profile.policy": reading(
                            passage("transport", "8", "Авто"),
                            passage("territory", "9", "Россия"),
                        ),
                        "profile.amendment.1": reading(passage("transport", "8", "Авиа")),
                    }
                ),
            )
            .profile()
            .clauses["territory"]
        ],
        equal_to(["ГП п. 9"]),
        "Clause that an amendment does not name does not stay from the policy",
    )


def test_drops_a_wording_of_a_clause_the_amendment_does_not_name() -> None:
    assert_that(
        Extraction(
            Bundle(
                Sheet("п. 9 Россия"),
                (Signed(1, "Пункт 8 (Транспорт) принять: Авиа", date(2026, 3, 1)),),
            ),
            FakeModel(
                {
                    "profile.policy": reading(passage("territory", "9", "Россия")),
                    "profile.amendment.1": reading(passage("territory", "9", "Весь мир")),
                }
            ),
        )
        .profile()
        .clauses["territory"],
        has_length(1),
        "Wording of a clause that the amendment does not name is not dropped",
    )


def test_records_a_wording_of_a_clause_the_amendment_does_not_name() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("Полис"), (Signed(3, "Пункт 8 принять: Авиа", date(2026, 3, 1)),)),
            FakeModel(
                {
                    "profile.policy": reading(),
                    "profile.amendment.3": reading(passage("territory", "9", "Весь мир")),
                }
            ),
        )
        .profile()
        .problems,
        has_item(
            "Файл ДС 3: документ не называет пункт 9, к которому модель отнесла условие territory, "
            "редакция отброшена"
        ),
        "Wording of a clause that the amendment does not name is not recorded in problems",
    )


def test_drops_a_wording_of_an_amendment_without_a_point() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("Полис"), (Signed(1, "Пункт 8 принять: Авиа", date(2026, 3, 1)),)),
            FakeModel(
                {
                    "profile.policy": reading(),
                    "profile.amendment.1": reading(passage("transport", text="Авиа")),
                }
            ),
        )
        .profile()
        .clauses,
        equal_to({}),
        "Wording of an amendment without a point is not dropped",
    )


def test_amendment_changes_several_clauses_at_once() -> None:
    points = {
        "beneficiary": "3",
        "object": "5",
        "term": "6",
        "transport": "8",
        "territory": "9",
        "limit": "12",
        "carrier_risk": "3.4.28",
    }
    assert_that(
        sorted(
            Extraction(
                Bundle(
                    Sheet("Полис"),
                    (
                        Signed(
                            1,
                            " ".join(f"Пункт {point} принять." for point in points.values()),
                            date(2026, 3, 1),
                        ),
                    ),
                ),
                FakeModel(
                    {
                        "profile.policy": reading(),
                        "profile.amendment.1": reading(
                            *(passage(key, point, "Текст") for key, point in points.items())
                        ),
                    }
                ),
            )
            .profile()
            .clauses
        ),
        equal_to(sorted(points)),
        "Amendment does not change several clauses at once",
    )


def test_amendment_of_requisites_adds_no_wording() -> None:
    assert_that(
        Extraction(
            Bundle(
                Sheet("п. 8 Авто"), (Signed(1, "Изменить банковские реквизиты", date(2026, 3, 1)),)
            ),
            FakeModel(
                {
                    "profile.policy": reading(passage("transport", "8", "Авто")),
                    "profile.amendment.1": reading(),
                }
            ),
        )
        .profile()
        .clauses["transport"],
        has_length(1),
        "Amendment of requisites does not leave the clauses of the policy alone",
    )


def test_drops_a_date_that_the_document_does_not_hold() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("Срок с 01.09.2026 по 31.12.2026")),
            FakeModel(
                {
                    "profile.policy": reading(
                        passage("term", "6", dates=["2026-09-01", "2027-12-31"])
                    )
                }
            ),
        )
        .profile()
        .clauses["term"][0]
        .dates,
        equal_to((date(2026, 9, 1),)),
        "Date that the document does not hold is not dropped",
    )


def test_records_a_date_that_the_document_does_not_hold() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("Срок с 01.09.2026")),
            FakeModel(
                {
                    "profile.policy": reading(
                        passage("term", "6", dates=["2026-09-01", "2027-12-31"])
                    )
                }
            ),
        )
        .profile()
        .problems[0],
        equal_to("Файл ГП: дата 31.12.2027 условия term не найдена в тексте документа и отброшена"),
        "Date that the document does not hold is not recorded in problems",
    )


def test_keeps_a_date_written_with_a_month_word() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("Срок с «01» сентября 2026 г.")),
            FakeModel({"profile.policy": reading(passage("term", "6", dates=["2026-09-01"]))}),
        )
        .profile()
        .clauses["term"][0]
        .dates,
        equal_to((date(2026, 9, 1),)),
        "Date written with a month word is not kept",
    )


def test_drops_a_sum_that_the_document_does_not_hold() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("Лимит 200 000 000,00 рублей")),
            FakeModel(
                {
                    "profile.policy": reading(
                        passage(
                            "limit",
                            "12",
                            "Лимит",
                            amounts=[{"value": "900000000", "currency": "RUB"}],
                        )
                    )
                }
            ),
        )
        .profile()
        .clauses["limit"][0]
        .amounts,
        empty(),
        "Sum that the document does not hold is not dropped",
    )


def test_records_a_sum_that_the_document_does_not_hold() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("Лимит 200 000 000,00 рублей")),
            FakeModel(
                {
                    "profile.policy": reading(
                        passage("limit", "12", amounts=[{"value": "900000000", "currency": "RUB"}])
                    )
                }
            ),
        )
        .profile()
        .problems[0],
        equal_to(
            "Файл ГП: сумма 900000000 RUB условия limit не найдена в тексте документа и отброшена"
        ),
        "Sum that the document does not hold is not recorded in problems",
    )


def test_keeps_a_sum_with_spaces_and_kopecks() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("Лимит 200 000 000,00 рублей")),
            FakeModel(
                {
                    "profile.policy": reading(
                        passage("limit", "12", amounts=[{"value": "200000000", "currency": "RUB"}])
                    )
                }
            ),
        )
        .profile()
        .clauses["limit"][0]
        .amounts,
        equal_to((Sum(value=Decimal("200000000"), currency="RUB"),)),
        "Sum with spaces and kopecks is not kept",
    )


def test_checks_a_date_of_an_amendment_against_the_text_of_this_amendment() -> None:
    assert_that(
        Extraction(
            Bundle(
                Sheet("Срок по 31.12.2026"),
                (Signed(1, "Пункт 6 принять: срок по 31.03.2027", date(2026, 3, 1)),),
            ),
            FakeModel(
                {
                    "profile.policy": reading(),
                    "profile.amendment.1": reading(
                        passage("term", "6", "срок", dates=["2026-12-31"])
                    ),
                }
            ),
        )
        .profile()
        .clauses["term"][0]
        .dates,
        empty(),
        "Date of an amendment is not checked against the text of this amendment",
    )


def test_stays_a_draft_when_an_answer_breaks_the_schema() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("Полис"), (Signed(5, "Пункт 8 принять", date(2026, 3, 1)),)),
            FakeModel({"profile.policy": reading(), "profile.amendment.5": '{"passages": "нет"}'}),
        )
        .profile()
        .problems,
        has_item(
            "Файл ДС 5: ответ модели дважды не прошёл проверку по схеме, документ не прочитан"
        ),
        "Answer that breaks the schema is not recorded in problems",
    )


def test_keeps_the_other_documents_when_one_amendment_fails() -> None:
    assert_that(
        Extraction(
            Bundle(
                Sheet("Полис"),
                (
                    Signed(1, "Пункт 8 принять", date(2026, 3, 1)),
                    Signed(2, "Пункт 8 принять", date(2026, 4, 1)),
                ),
            ),
            FakeModel(
                {
                    "profile.policy": reading(),
                    "profile.amendment.1": "не JSON",
                    "profile.amendment.2": reading(passage("transport", "8", "Авиа")),
                }
            ),
        )
        .profile()
        .clauses["transport"][0]
        .amendment,
        equal_to(2),
        "Other documents are not kept when one amendment fails",
    )


def test_keeps_the_amendments_when_the_policy_fails() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("Полис"), (Signed(1, "Пункт 8 принять", date(2026, 3, 1)),)),
            FakeModel(
                {
                    "profile.policy": "не JSON",
                    "profile.amendment.1": reading(passage("transport", "8", "Авиа")),
                }
            ),
        )
        .profile()
        .clauses["transport"][0]
        .amendment,
        equal_to(1),
        "Amendments are not kept when the policy fails",
    )


def test_stays_a_draft_when_the_policy_fails() -> None:
    assert_that(
        Extraction(Bundle(Sheet("Полис")), FakeModel({"profile.policy": "не JSON"}))
        .profile()
        .problems[0],
        equal_to("Файл ГП: ответ модели дважды не прошёл проверку по схеме, документ не прочитан"),
        "Failure of the policy is not recorded in problems",
    )


def test_stays_a_draft_when_the_model_does_not_answer() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("Полис")), Strict(Scripted([reading()]), Route("vsk", "m"), Memory(), 0.0)
        )
        .profile()
        .problems[0],
        equal_to("Файл ГП: модель не ответила, документ не прочитан"),
        "Silence of the model is not recorded in problems",
    )


def test_settings_error_of_the_client_is_not_hidden() -> None:
    extraction = Extraction(Bundle(Sheet("Полис")), FakeModel({}))
    assert_that(
        extraction.profile,
        raises(MisconfiguredError),
        "Settings error of the client does not fail loudly",
    )


def test_asks_again_only_once_after_invalid_json() -> None:
    backend = Scripted(["не JSON"])
    Extraction(Bundle(Sheet("Полис")), Strict(backend, Route("vsk", "m"), Memory(), 5.0)).profile()
    assert_that(backend.calls, equal_to(2), "Client does not ask exactly once more")


def test_records_a_document_after_a_second_invalid_json() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("Полис")),
            Strict(Scripted(["не JSON"]), Route("vsk", "m"), Memory(), 5.0),
        )
        .profile()
        .problems[0],
        equal_to("Файл ГП: ответ модели дважды не прошёл проверку по схеме, документ не прочитан"),
        "Second invalid JSON is not recorded in problems",
    )


def test_reads_a_document_after_a_repeat_that_helped() -> None:
    assert_that(
        Extraction(
            Bundle(Sheet("п. 5 | Грузы")),
            Strict(
                Scripted(["не JSON", reading(passage("object", "5", "Грузы"))]),
                Route("vsk", "m"),
                Memory(),
                5.0,
            ),
        )
        .profile()
        .clauses["object"][0]
        .text,
        equal_to("Грузы"),
        "Document is not read after a repeat that helped",
    )


def test_asks_the_model_by_the_schema_of_a_reading() -> None:
    backend = Scripted([reading()])
    Extraction(
        Bundle(Sheet("Полис"), (Signed(1, "Пункт 8", date(2026, 3, 1)),)),
        Strict(backend, Route("vsk", "m"), Memory(), 5.0),
    ).profile()
    assert_that(
        backend.shapes,
        equal_to(["Reading", "Reading"]),
        "Model is not asked by the schema of a reading",
    )


def test_gives_the_model_the_text_of_the_document() -> None:
    text = uuid.uuid4().hex
    backend = Scripted([reading()])
    Extraction(Bundle(Sheet(text)), Strict(backend, Route("vsk", "m"), Memory(), 5.0)).profile()
    assert_that(
        backend.conversations[0][-1].text(),
        equal_to(text),
        "Model is not given the text of the document",
    )


def test_tells_the_model_about_a_policy_and_an_amendment_differently() -> None:
    backend = Scripted([reading()])
    Extraction(
        Bundle(Sheet("Полис"), (Signed(1, "Пункт 8", date(2026, 3, 1)),)),
        Strict(backend, Route("vsk", "m"), Memory(), 5.0),
    ).profile()
    assert_that(
        backend.conversations[0][0].text(),
        is_not(equal_to(backend.conversations[1][0].text())),
        "Model is not told about a policy and an amendment differently",
    )


def test_asks_the_model_once_for_each_document() -> None:
    count = random.randint(0, 30)
    model = FakeModel(
        {
            "profile.policy": reading(),
            **{f"profile.amendment.{number}": reading() for number in range(1, count + 1)},
        }
    )
    Extraction(
        Bundle(
            Sheet("Полис"),
            tuple(Signed(number, "Текст", date(2026, 3, 1)) for number in range(1, count + 1)),
        ),
        model,
    ).profile()
    assert_that(model.count(), equal_to(count + 1), "Model is not asked once for each document")


def test_asks_the_model_once_for_a_document_that_fails() -> None:
    count = random.randint(1, 30)
    model = FakeModel(
        {
            "profile.policy": "не JSON",
            **{f"profile.amendment.{number}": "не JSON" for number in range(1, count + 1)},
        }
    )
    Extraction(
        Bundle(
            Sheet("Полис"),
            tuple(Signed(number, "Текст", date(2026, 3, 1)) for number in range(1, count + 1)),
        ),
        model,
    ).profile()
    assert_that(
        model.count(),
        equal_to(count + 1),
        "Model is not asked once for a document that fails",
    )


def test_moves_the_problems_of_the_package() -> None:
    problem = uuid.uuid4().hex
    assert_that(
        Extraction(
            Bundle(Sheet("Полис"), problems=(problem,)),
            FakeModel({"profile.policy": reading()}),
        )
        .profile()
        .problems[0],
        equal_to(problem),
        "Problems of the package are not moved to the profile",
    )


def test_moves_the_conditions_of_the_package() -> None:
    condition = uuid.uuid4().hex
    assert_that(
        Extraction(
            Bundle(Sheet("Полис"), conditions=(condition,)),
            FakeModel({"profile.policy": reading()}),
        )
        .profile()
        .conditions,
        equal_to((condition,)),
        "Conditions of the package are not moved to the profile",
    )


def test_moves_the_carriers_of_the_package_into_their_clause() -> None:
    carrier = uuid.uuid4().hex
    assert_that(
        Extraction(
            Bundle(Sheet("Полис"), carriers=(carrier,)),
            FakeModel({"profile.policy": reading()}),
        )
        .profile()
        .clauses["carriers"][0]
        .entries,
        equal_to((carrier,)),
        "Carriers of the package are not moved into their clause",
    )


def test_package_without_carriers_has_no_clause_of_carriers() -> None:
    assert_that(
        Extraction(Bundle(Sheet("Полис")), FakeModel({"profile.policy": reading()}))
        .profile()
        .clauses,
        equal_to({}),
        "Package without carriers does not leave the clause of carriers out",
    )
