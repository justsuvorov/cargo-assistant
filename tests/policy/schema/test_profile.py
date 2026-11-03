import random
import uuid
from datetime import date

from hamcrest import assert_that, equal_to, raises
from pydantic import ValidationError

from app.policy.schema.profile import Profile, Wording


def test_wording_concerns_every_declaration_by_default() -> None:
    assert_that(
        Wording(source=uuid.uuid4().hex, effective=date(2026, 1, random.randint(1, 28))).scope,
        equal_to("all"),
        "Wording does not concern every declaration by default",
    )


def test_wording_keeps_the_declarations_of_its_scope() -> None:
    number = str(random.randint(1, 999))
    assert_that(
        Wording.model_validate(
            {"source": "ДС 1", "effective": "2026-01-01", "scope": [number]}
        ).scope,
        equal_to((number,)),
        "Wording does not keep the declarations of its scope",
    )


def test_profile_rejects_an_unknown_field() -> None:
    body = {
        "number": uuid.uuid4().hex,
        "issued": "2026-01-01",
        "insurer": uuid.uuid4().hex,
        "clauses": {},
        "extra": True,
    }
    assert_that(
        lambda: Profile.model_validate(body),
        raises(ValidationError),
        "Profile does not reject an unknown field",
    )
