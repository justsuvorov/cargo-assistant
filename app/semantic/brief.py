import json
from typing import Protocol, final

from app.domain.semantics import Question
from app.llm.messages import Message, System, User

_INSTRUCTION = """Ты помогаешь эксперту страховой компании сверять декларацию на перевозку груза
с генеральным полисом по смыслу.

Тебе дан JSON с двумя списками:
- «пункты» — пункты полиса: номер, ссылка, текст пункта и правило проверки;
- «значения» — значения одного поля декларации: id, номер пункта и само значение.

Для каждого значения реши по тексту его пункта и правилу проверки:
- match — значение соответствует пункту;
- mismatch — значение явно противоречит пункту, например входит в исключения;
- review — решить уверенно нельзя: значение неполное или неоднозначное, текста пункта не
  хватает или правило велит передать значение эксперту.

Если сомневаешься — review. Не придумывай условий, которых нет в тексте пункта и в правиле.
Даты, суммы, лимиты, номера и заполненность полей не проверяй — это делает программа.

Ответь одним JSON-объектом: в «answers» по одному элементу на каждый id из «значений»:
id, status (match, mismatch или review) и comment — короткий комментарий для эксперта на
русском языке, не длиннее 200 символов. Для mismatch и review назови в комментарии ту часть
значения, которая определила статус."""


class Prompt(Protocol):
    """Conversation that puts the questions of one card before the model, and its version."""

    def messages(self, questions: tuple[Question, ...]) -> tuple[Message, ...]: ...

    def version(self) -> str: ...


def _point(question: Question) -> tuple[str, str, str]:
    return (question.clause().reference(), question.clause().text(), question.rule())


@final
class Brief:
    """Prompt that lists each clause with the rule of its card once and numbers the values;
    only the value, the clause and the rule reach the model, no other field of the
    declaration and nothing about the policy holder."""

    __slots__ = ()

    def messages(self, questions: tuple[Question, ...]) -> tuple[Message, ...]:
        points = tuple(dict.fromkeys(_point(question) for question in questions))
        return (
            System(_INSTRUCTION),
            User(
                json.dumps(
                    {
                        "пункты": [
                            {
                                "пункт": index,
                                "ссылка": point[0],
                                "текст": point[1],
                                "правило": point[2],
                            }
                            for index, point in enumerate(points, start=1)
                        ],
                        "значения": [
                            {
                                "id": index,
                                "пункт": points.index(_point(question)) + 1,
                                "значение": question.value(),
                            }
                            for index, question in enumerate(questions, start=1)
                        ],
                    },
                    ensure_ascii=False,
                    indent=1,
                )
            ),
        )

    def version(self) -> str:
        return "semantic-1"
