import random
import string
from datetime import date

from hamcrest import assert_that, equal_to

from app.policy.papers import Agreement, Opened


def _word() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=8))


def test_opened_paper_gives_reference_and_text() -> None:
    reference, text = _word(), _word()
    paper = Opened(reference, text)
    assert_that(
        (paper.reference(), paper.text()),
        equal_to((reference, text)),
        "Opened does not give the reference and the text it was made of",
    )


def test_agreement_gives_paper_and_stated_terms() -> None:
    reference, text = _word(), _word()
    effective = date(2025, 1, 2)
    agreement = Agreement(Opened(reference, text), 7, effective, ("12", "13"))
    assert_that(
        (
            agreement.reference(),
            agreement.text(),
            agreement.number(),
            agreement.effective(),
            agreement.scope(),
        ),
        equal_to((reference, text, 7, effective, ("12", "13"))),
        "Agreement does not give the paper and the terms it was made of",
    )
