import random

from hamcrest import assert_that, equal_to

from app.llm.text import Raw, Thoughtless, Unfenced


def test_removes_closed_reasoning_before_answer() -> None:
    answer = f'{{"n": {random.randint(1, 999)}}}'
    assert_that(
        Thoughtless(Raw(f"<think>сначала подумаю\nи ещё</think>\n{answer}")).text(),
        equal_to(answer),
        "Closed reasoning is not removed from the answer",
    )


def test_removes_unclosed_reasoning_up_to_the_end() -> None:
    answer = f'{{"n": {random.randint(1, 999)}}}'
    assert_that(
        Thoughtless(Raw(f"{answer}\n<think>бюджет кончился посреди мысли")).text(),
        equal_to(answer),
        "Unclosed reasoning is not cut off to the end of the text",
    )


def test_leaves_nothing_when_only_unclosed_reasoning_came() -> None:
    assert_that(
        Thoughtless(Raw("<think>рассуждаю и рассуждаю")).text(),
        equal_to(""),
        "Answer made of unclosed reasoning does not become empty",
    )


def test_removes_reasoning_before_stray_closing_tag() -> None:
    answer = f'{{"n": {random.randint(1, 999)}}}'
    assert_that(
        Thoughtless(Raw(f"шлюз срезал открывающий тег\n</think>{answer}")).text(),
        equal_to(answer),
        "Reasoning before a stray closing tag is not removed",
    )


def test_unwraps_fence_around_whole_answer() -> None:
    answer = f'{{"n": {random.randint(1, 999)}}}'
    assert_that(
        Unfenced(Raw(f"```json\n{answer}\n```")).text(),
        equal_to(answer),
        "Fence around the whole answer is not removed",
    )


def test_keeps_text_with_fence_inside_untouched() -> None:
    text = 'Вот ответ:\n```json\n{"n": 1}\n```'
    assert_that(
        Unfenced(Raw(text)).text(),
        equal_to(text),
        "Fence inside a longer text is not left alone",
    )
