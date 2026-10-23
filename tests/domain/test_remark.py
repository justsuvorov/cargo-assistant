import uuid

from hamcrest import assert_that, equal_to

from app.domain.remark import Note


def test_note_keeps_its_comment() -> None:
    comment = f"Входит в срок действия ГП {uuid.uuid4().hex}"
    assert_that(
        Note(comment, "п. 6 ГП").comment(), equal_to(comment), "Note does not keep its comment"
    )


def test_note_keeps_its_reference() -> None:
    reference = f"п. {uuid.uuid4().int % 30} ГП в ред. ДС 4"
    assert_that(
        Note("", reference).reference(), equal_to(reference), "Note does not keep its reference"
    )
