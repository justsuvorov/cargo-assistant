# Требования к коду (исходный текст заказчика)

Текст обязателен для оркестратора и всех субагентов. Применение к Python — в разделе
«Требования к коду» файла [CLAUDE.md](../CLAUDE.md) и в [decisions.md](decisions.md) (D-13).

```markdown
# Be Quality Dogmatic

Keep chat replies and your answers easy to comprehend.

## Tools

Use GNU (GNU's Not Unix) tools such as `gsed`, `gfind`, `ggrep`, and `gcat`.
Commit changes with `courier:commit-changes-to-git` skill.
Submit pull requests with `courier:submit-a-pull-request` skill.
File issues with `bugscribe:submit-an-issue` skill.

## Discipline

Write concise, direct, human prose.
Speak plain English in full sentences, avoiding jargon, slang, and shorthand.
Push back on technical mistakes, deferring to users on vision and architecture.
Stay on scope, refactoring only what tasks require.
Design top-down, whole before parts, composition before ingredients.
Never work around design obstacles, stopping to ask me instead.

## Workflow

Pull from Git before changes, push back only with explicit user permission.
Name each branch after its GitHub issue integer, asking when unsure.
Always practice TDD (test-driven development), reproducing bugs before fixing.
Invest in unit tests until bugs reproduce, trusting intuition over debugging.
Log extensively when problems stay hard.

## Changes

Tolerate upstream bugs, suggesting issues and waiting for fixes.
Keep changes focused and minimal.
Leave puzzles for later, following Puzzle Driven Development.
Flag smells and refactoring, suggesting issues rather than fixing silently.
Fix style violations in code, trusting checkers rather than suppressing them.

## Code

Favor aesthetics over functionality.
Skip inline comments.
Prepend classes with plain-text docblocks explaining purpose, not usage.
Name variables as single nouns.
Inline single-use expressions, dropping unnecessary local variables.
Name methods as single nouns or verbs, separating commands from queries.
Pack method bodies without blank lines.

## Style

Keep error and log messages to one sentence with context.
Strip trailing periods from messages.
Follow "Paired Brackets" and "Monotonic Indentation".

## Objects

Honor Elegant Objects and SOLID (single, open, Liskov, interface, dependency).
Follow DDD (domain-driven design) and YAGNI (you arent gonna need it).
Apply SRP (single-responsibility) and DRY (dont repeat yourself).
Favor failing immediately over failing silently.
Allow only assignments in one primary constructor, delegating from secondaries.
Compose objects instead of inheriting implementation.
Reject -er names and utility classes.
Make every class final, holding one to four attributes.

## Methods

Build only immutable objects, freezing attributes after assignment.
Drop static methods, public static literals, setters, and getters.
Declare methods in interfaces first, exposing nothing public outside them.
Reject null returns and arguments.
Skip type introspection, casting, and reflection.

## Tests

Follow "Angry Tests".
Place one assertion per test, as its last statement.
Phrase each failure message negatively.
Keep tests short, verifying one behavior with one statement.
Map test files one-to-one with feature files, naming tests as sentences.
Spell "cannot" and "dont" without apostrophes.
Isolate tests from shared attributes, setUp, tearDown, constants, and cleanup.

## Fixtures

Provide custom arguments to tested objects, not defaults.
Skip irrelevant code, side effects, accessors, constructors, and errors.
Favor fakes and stubs over mocks.
Use Hamcrest matchers with irregular, random inputs.
Inline brief fixtures, generating bulky ones at runtime.
Create fixture objects against duplication, using temporary directories.
Keep filesystem, sockets, and memory unmocked.

## Runtime

Disable logging in tests.
Bound every wait with timeouts.
Test concurrency, retrying flaky blocks.
Assume no Internet, using ephemeral ports.
```

## Что проверяется автоматически

| Проверка | Инструмент |
|---|---|
| Форматирование, стиль, `print`, сложность ≤ 6, неиспользуемый код, docblock класса | `ruff format`, `ruff check` |
| Типы, `Final`, отсутствие явного `Any` | `mypy --strict` |
| `@final`, `__slots__`, ≤ 4 приватных атрибута, нет static/class-методов | `tools.lint` (Finality, Statics, Attributes) |
| Публичный метод объявлен в Protocol | `tools.lint` (Interfaces) |
| Нет имён на -er | `tools.lint` (Names) |
| Нет `isinstance`/`type`/`getattr`/`cast` и `None` в `app/` вне границ | `tools.lint` (Purity) |
| Комментарии — только пазлы `# @todo #N:Xmin текст`; нет `noqa`/`type: ignore` | `tools.lint` (Remarks) |
| Нет пустых строк в телах функций | `tools.lint` (Density) |
| Один `assert_that` последней строкой, отрицательное сообщение, без апострофов, без общих фикстур | `tools.lint` (Angry) |
| Тестовый файл соответствует модулю | `tools.lint` (Pairing) |
| Таймаут на тест, логирование выключено | `pytest-timeout`, `tests/conftest.py` |
