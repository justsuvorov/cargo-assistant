import random
import uuid
from datetime import date, timedelta
from decimal import Decimal

from hamcrest import assert_that, equal_to, raises

from app.domain.errors import UnreadableError
from app.domain.field import Blank
from app.domain.money import Amount
from app.domain.revision import Revision
from app.policy.schema.profile import Sum, Wording
from app.policy.wording import Edition, Editions, Gathered, Quoted


def test_amendment_governs_a_shipment_that_starts_on_the_day_it_takes_effect() -> None:
    day = _day()
    assert_that(
        _edition(_wording(effective=day, amendment=1)).governs(_Trip("1", day)),
        equal_to(True),
        "Amendment does not govern a shipment that starts on its first day",
    )


def test_amendment_leaves_a_shipment_that_starts_the_day_before_it_takes_effect() -> None:
    day = _day()
    wording = _wording(effective=day, amendment=random.randint(1, 30))
    assert_that(
        _edition(wording).governs(_Trip("1", day - timedelta(days=1))),
        equal_to(False),
        "Amendment does not leave a shipment that starts before its first day",
    )


def test_policy_wording_governs_a_shipment_that_starts_before_its_date() -> None:
    day = _day()
    assert_that(
        _edition(_wording(effective=day)).governs(_Trip("1", day - timedelta(days=400))),
        equal_to(True),
        "Policy wording does not govern a shipment that starts before its date",
    )


def test_policy_wording_needs_no_start_of_the_shipment() -> None:
    assert_that(
        _edition(_wording(effective=_day())).governs(_Undated()),
        equal_to(True),
        "Policy wording does not govern a shipment without a readable start",
    )


def test_amendment_cannot_say_whether_it_governs_a_shipment_without_a_start() -> None:
    edition = _edition(_wording(effective=_day(), amendment=1))
    assert_that(
        lambda: edition.governs(_Undated()),
        raises(UnreadableError),
        "Amendment does not refuse to judge a shipment without a readable start",
    )


def test_amendment_to_another_declaration_needs_no_start_of_the_shipment() -> None:
    assert_that(
        _edition(_wording(effective=_day(), amendment=1, scope=("777",))).governs(_Undated()),
        equal_to(False),
        "Amendment to another declaration does not leave a shipment without a start",
    )


def test_general_edition_keeps_governing_after_the_term_written_in_its_text() -> None:
    day = _day()
    wording = _wording(effective=day, amendment=1, dates=(day, day + timedelta(days=30)))
    assert_that(
        _edition(wording).governs(_Trip("1", day + timedelta(days=random.randint(31, 400)))),
        equal_to(True),
        "Edition does not keep governing after the term written in its text",
    )


def test_scoped_edition_governs_its_own_declaration() -> None:
    number = str(random.randint(100, 999))
    assert_that(
        _edition(_wording(scope=(number,))).governs(_Trip(number, _day())),
        equal_to(True),
        "Edition does not govern the declaration of its scope",
    )


def test_scoped_edition_leaves_another_declaration() -> None:
    number = random.randint(100, 499)
    assert_that(
        _edition(_wording(scope=(str(number),))).governs(_Trip(str(number + 500), _day())),
        equal_to(False),
        "Edition does not leave a declaration outside its scope",
    )


def test_scope_compares_declaration_numbers_by_digits_only() -> None:
    assert_that(
        tuple(
            _edition(_wording(scope=(written,))).governs(_Trip(declared, _day()))
            for written, declared in (
                ("70", "070"),
                ("070", "70"),
                ("Р-070", "70"),
                ("70", "Р-070"),
                ("р 070", "№ 070"),
            )
        ),
        equal_to((True, True, True, True, True)),
        "Edition does not compare declaration numbers by digits only",
    )


def test_scope_keeps_trailing_zeros_of_a_declaration_number() -> None:
    assert_that(
        _edition(_wording(scope=("70",))).governs(_Trip("700", _day())),
        equal_to(False),
        "Edition does not tell 70 from 700",
    )


def test_scope_without_digits_leaves_a_declaration_without_digits() -> None:
    assert_that(
        _edition(_wording(scope=("б/н",))).governs(_Trip("без номера", _day())),
        equal_to(False),
        "Edition does not leave a declaration when neither number has digits",
    )


def test_scope_reads_a_number_of_zeros_as_zero() -> None:
    assert_that(
        _edition(_wording(scope=("0",))).governs(_Trip("000", _day())),
        equal_to(True),
        "Edition does not read a number of zeros as zero",
    )


def test_empty_scope_concerns_every_declaration() -> None:
    assert_that(
        _edition(_wording(scope=())).governs(_Trip(str(random.randint(1, 999)), _day())),
        equal_to(True),
        "Edition with an empty scope does not concern every declaration",
    )


def test_scoped_edition_supersedes_a_general_one_that_took_effect_later() -> None:
    day = _day()
    own = _wording(source="ДС 1", effective=day, scope=("7",), amendment=1)
    general = _wording(source="ДС 2", effective=day + timedelta(days=9), amendment=2)
    assert_that(
        _edition(own, general).supersedes(_edition(general, own)),
        equal_to(True),
        "Edition to one declaration does not supersede a later general edition",
    )


def test_general_edition_leaves_a_scoped_one_in_place() -> None:
    day = _day()
    own = _wording(source="ДС 1", effective=day, scope=("7",), amendment=1)
    general = _wording(source="ДС 2", effective=day + timedelta(days=9), amendment=2)
    assert_that(
        _edition(general, own).supersedes(_edition(own, general)),
        equal_to(False),
        "General edition does not leave an edition to one declaration in place",
    )


def test_later_edition_supersedes_an_earlier_one_despite_a_smaller_number() -> None:
    day = _day()
    older = _wording(source="ДС 9", effective=day, amendment=9)
    newer = _wording(source="ДС 3", effective=day + timedelta(days=1), amendment=3)
    assert_that(
        _edition(newer, older).supersedes(_edition(older, newer)),
        equal_to(True),
        "Later edition does not supersede an earlier one with a greater number",
    )


def test_greater_number_supersedes_a_smaller_one_on_the_same_date() -> None:
    day = _day()
    smaller = _wording(source="ДС 20", effective=day, amendment=20)
    greater = _wording(source="ДС 23", effective=day, amendment=23)
    assert_that(
        _edition(greater, smaller).supersedes(_edition(smaller, greater)),
        equal_to(True),
        "Amendment 23 does not supersede amendment 20 of the same date",
    )


def test_smaller_number_leaves_a_greater_one_in_place_on_the_same_date() -> None:
    day = _day()
    smaller = _wording(source="ДС 20", effective=day, amendment=20)
    greater = _wording(source="ДС 23", effective=day, amendment=23)
    assert_that(
        _edition(smaller, greater).supersedes(_edition(greater, smaller)),
        equal_to(False),
        "Amendment 20 does not leave amendment 23 of the same date in place",
    )


def test_amendment_supersedes_the_policy_of_the_same_date() -> None:
    day = _day()
    policy = _wording(source="ГП п. 6", effective=day)
    amendment = _wording(source="ДС 1", effective=day, amendment=1)
    assert_that(
        _edition(amendment, policy).supersedes(_edition(policy, amendment)),
        equal_to(True),
        "Amendment does not supersede the policy of the same date",
    )


def test_editions_of_equal_rank_leave_each_other_in_place() -> None:
    day = _day()
    first = _wording(source="ДС 4 п. 1", effective=day, amendment=4)
    second = _wording(source="ДС 4 п. 2", effective=day, amendment=4)
    assert_that(
        _edition(first, second).supersedes(_edition(second, first)),
        equal_to(False),
        "Edition does not leave an edition of equal rank in place",
    )


def test_edition_leaves_a_revision_of_another_clause_in_place() -> None:
    day = _day()
    wording = _wording(source="ДС 5", effective=day + timedelta(days=1), amendment=5)
    assert_that(
        _edition(wording).supersedes(_edition(_wording(source="ГП п. 1", effective=day))),
        equal_to(False),
        "Edition does not leave a revision outside its clause in place",
    )


def test_editions_with_one_source_leave_each_other_in_place() -> None:
    day = _day()
    older = _wording(source="ДС 4", effective=day, amendment=4)
    newer = _wording(source="ДС 4", effective=day + timedelta(days=1), amendment=4)
    assert_that(
        _edition(newer, older).supersedes(_edition(older, newer)),
        equal_to(False),
        "Edition does not refuse to rank a revision with its own source",
    )


def test_edition_gives_a_clause_that_refers_to_its_source() -> None:
    source = uuid.uuid4().hex
    assert_that(
        _edition(_wording(source=source)).clause().reference(),
        equal_to(source),
        "Edition does not give a clause that refers to its source",
    )


def test_quoted_clause_gives_the_text() -> None:
    text = uuid.uuid4().hex
    assert_that(
        Quoted(_wording(text=text)).text(),
        equal_to(text),
        "Quoted clause does not give the text of the wording",
    )


def test_quoted_clause_gives_the_dates() -> None:
    days = (_day(), _day())
    assert_that(
        Quoted(_wording(dates=days)).dates(),
        equal_to(days),
        "Quoted clause does not give the dates of the wording",
    )


def test_quoted_clause_gives_sums_as_money() -> None:
    value = Decimal(random.randint(1, 900)) * 1000
    assert_that(
        Quoted(_wording(amounts=(Sum(value=value, currency="USD"),))).amounts()[0].text(),
        equal_to(Amount(value, "USD").text()),
        "Quoted clause does not give the sums of the wording as money",
    )


def test_quoted_clause_gives_the_entries() -> None:
    entries = (uuid.uuid4().hex, uuid.uuid4().hex)
    assert_that(
        Quoted(_wording(entries=entries)).entries(),
        equal_to(entries),
        "Quoted clause does not give the entries of the wording",
    )


def test_edition_supersedes_an_older_one_of_its_own_point() -> None:
    day = _day()
    older = _wording(source="ГП п. 5.2", point="5.2", effective=day)
    newer = _wording(source="ДС 1 п. 5.2", point="5.2", effective=day, amendment=1)
    assert_that(
        _edition(newer, older).supersedes(_edition(older, newer)),
        equal_to(True),
        "Edition does not supersede an older one of its own point",
    )


def test_edition_supersedes_an_older_one_of_a_nested_point() -> None:
    day = _day()
    nested = _wording(source="ДС 1 п. 5.2", point="5.2", effective=day, amendment=1)
    whole = _wording(source="ДС 2 п. 5", point="5", effective=day, amendment=2)
    assert_that(
        _edition(whole, nested).supersedes(_edition(nested, whole)),
        equal_to(True),
        "Edition of point 5 does not supersede an older one of point 5.2",
    )


def test_edition_without_a_point_supersedes_an_older_one_of_any_point() -> None:
    day = _day()
    nested = _wording(source="ГП п. 5.2", point="5.2", effective=day)
    whole = _wording(source="ДС 2", effective=day, amendment=2)
    assert_that(
        _edition(whole, nested).supersedes(_edition(nested, whole)),
        equal_to(True),
        "Edition of the whole clause does not supersede an older one of a point",
    )


def test_edition_of_a_nested_point_leaves_the_point_around_it() -> None:
    day = _day()
    whole = _wording(source="ГП п. 5", point="5", effective=day)
    nested = _wording(source="ДС 1 п. 5.2", point="5.2", effective=day, amendment=1)
    assert_that(
        _edition(nested, whole).supersedes(_edition(whole, nested)),
        equal_to(False),
        "Edition of point 5.2 does not leave point 5 in place",
    )


def test_edition_of_a_point_leaves_a_neighbouring_point() -> None:
    day = _day()
    neighbour = _wording(source="ГП п. 5.3", point="5.3", effective=day)
    edition = _wording(source="ДС 1 п. 5.2", point="5.2", effective=day, amendment=1)
    assert_that(
        _edition(edition, neighbour).supersedes(_edition(neighbour, edition)),
        equal_to(False),
        "Edition of point 5.2 does not leave point 5.3 in place",
    )


def test_edition_compares_points_by_parts_and_not_by_letters() -> None:
    day = _day()
    longer = _wording(source="ГП п. 5.10", point="5.10", effective=day)
    edition = _wording(source="ДС 1 п. 5.1", point="5.1", effective=day, amendment=1)
    assert_that(
        _edition(edition, longer).supersedes(_edition(longer, edition)),
        equal_to(False),
        "Edition of point 5.1 does not leave point 5.10 in place",
    )


def test_policy_wording_of_a_point_leaves_the_policy_wording_nested_in_it() -> None:
    day = _day()
    whole = _wording(source="ГП п. 5", point="5", effective=day)
    nested = _wording(source="ГП п. 5.2", point="5.2", effective=day)
    assert_that(
        _edition(whole, nested).supersedes(_edition(nested, whole)),
        equal_to(False),
        "Policy wording of point 5 does not leave its own point 5.2 in place",
    )


def test_edition_keeps_a_source_that_also_stands_for_another_point() -> None:
    day = _day()
    nested = _wording(source="ГП", point="5.2", effective=day)
    other = _wording(source="ГП", point="6", effective=day)
    edition = _wording(source="ДС 1 п. 5", point="5", effective=day, amendment=1)
    assert_that(
        _edition(edition, nested, other).supersedes(_edition(nested, edition, other)),
        equal_to(False),
        "Edition does not keep a source that also stands for another point",
    )


def test_edition_refuses_to_compare_a_point_that_is_no_number() -> None:
    day = _day()
    odd = _wording(source="ГП п. пять", point="пять", effective=day)
    edition = _wording(source="ДС 1 п. 5", point="5", effective=day, amendment=1)
    assert_that(
        lambda: _edition(edition, odd).supersedes(_edition(odd, edition)),
        raises(UnreadableError, "пять"),
        "Edition does not refuse to compare a point that is no number",
    )


def test_editions_treat_a_trailing_dot_of_a_point_as_nothing() -> None:
    day = _day()
    dotted = _wording(source="ГП п. 5.2.", point="5.2.", effective=day)
    edition = _wording(source="ДС 1 п. 5.2", point="5.2", effective=day, amendment=1)
    assert_that(
        Editions("object", (dotted, edition)).clause(_Trip("1", day)).reference(),
        equal_to("ДС 1 п. 5.2"),
        "Editions do not treat a trailing dot of a point as nothing",
    )


def test_gathered_clause_lists_the_sources_in_the_order_given() -> None:
    assert_that(
        Gathered(
            (_wording(source="ГП п. 5.9", point="5.9"), _wording(source="ДС 1", point="5.10"))
        ).reference(),
        equal_to("ГП п. 5.9, ДС 1"),
        "Gathered clause does not list the sources in the order given",
    )


def test_gathered_clause_names_a_shared_source_once() -> None:
    assert_that(
        Gathered((_wording(source="ГП", point="5"), _wording(source="ГП", point="6"))).reference(),
        equal_to("ГП"),
        "Gathered clause does not name a shared source once",
    )


def test_gathered_clause_joins_the_texts_by_lines_and_skips_the_empty_one() -> None:
    first, second = uuid.uuid4().hex, uuid.uuid4().hex
    assert_that(
        Gathered((_wording(text=first), _wording(), _wording(text=second))).text(),
        equal_to(f"{first}\n{second}"),
        "Gathered clause does not join the texts by lines",
    )


def test_gathered_clause_gives_every_date_once() -> None:
    first, second = date(2026, 1, 1), date(2026, 2, 2)
    assert_that(
        Gathered((_wording(dates=(first, second)), _wording(dates=(second,)))).dates(),
        equal_to((first, second)),
        "Gathered clause does not give every date once",
    )


def test_gathered_clause_gives_every_sum_once_as_money() -> None:
    assert_that(
        tuple(
            amount.text()
            for amount in Gathered(
                (
                    _wording(amounts=(Sum(value=Decimal("5"), currency="USD"),)),
                    _wording(amounts=(Sum(value=Decimal("5.00"), currency="USD"),)),
                    _wording(amounts=(Sum(value=Decimal("7"), currency="EUR"),)),
                )
            ).amounts()
        ),
        equal_to((Amount(Decimal("5"), "USD").text(), Amount(Decimal("7"), "EUR").text())),
        "Gathered clause does not give every sum once as money",
    )


def test_gathered_clause_gives_every_entry_once() -> None:
    first, second = uuid.uuid4().hex, uuid.uuid4().hex
    assert_that(
        Gathered((_wording(entries=(first, second)), _wording(entries=(second,)))).entries(),
        equal_to((first, second)),
        "Gathered clause does not give every entry once",
    )


def _day() -> date:
    return date(2026, random.randint(1, 12), random.randint(1, 28))


def _wording(**values: object) -> Wording:
    return Wording.model_validate({"source": "ГП п. 1", "effective": date(2000, 1, 1), **values})


def _edition(wording: Wording, *peers: Wording) -> Revision:
    return Edition(wording, (wording, *peers))


class _Trip:
    """Shipment of a declaration that starts on a given day."""

    __slots__ = ("_declaration", "_start")

    def __init__(self, declaration: str, start: date) -> None:
        self._declaration = declaration
        self._start = start

    def number(self) -> str:
        return self._declaration

    def declaration(self) -> str:
        return self._declaration

    def field(self, key: str) -> Blank:
        return Blank(key)

    def start(self) -> date:
        return self._start


class _Undated:
    """Shipment whose start date cannot be read."""

    __slots__ = ()

    def number(self) -> str:
        return "1"

    def declaration(self) -> str:
        return "1"

    def field(self, key: str) -> Blank:
        return Blank(key)

    def start(self) -> date:
        raise UnreadableError("Не найдена дата начала периода страхования")
