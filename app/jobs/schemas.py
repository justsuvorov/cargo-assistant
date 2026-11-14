from typing import Final, Protocol, final

from pydantic import ValidationError

from app.jobs.errors import SchemaVersionError
from app.policy.schema.profile import Profile


class Step(Protocol):
    """Conversion of a saved profile body from one schema version to the next one."""

    def source(self) -> int: ...

    def apply(self, body: dict[str, object]) -> dict[str, object]: ...


class Stored(Protocol):
    """Saved profile body that is read as a profile of the current schema."""

    def profile(self) -> Profile: ...


@final
class Upgraded:
    """Stored body read through the chain of steps «version N → N+1» up to the current schema;
    a body without a version was saved by schema 1, a newer or unreachable version is an error."""

    __slots__ = ("_body", "_steps")

    def __init__(self, body: dict[str, object], steps: tuple[Step, ...] = ()) -> None:
        self._body: Final = body
        self._steps: Final = {step.source(): step for step in steps}

    def profile(self) -> Profile:
        current = Profile.model_fields["schema_version"].default
        version = self._version()
        body = dict(self._body)
        while version != current:
            if version not in self._steps:
                raise SchemaVersionError(
                    f"Профиль сохранён по схеме версии {version}, а сервис читает версию {current}"
                )
            body = {**self._steps[version].apply(body), "schema_version": version + 1}
            version += 1
        try:
            return Profile.model_validate(body)
        except ValidationError as error:
            raise SchemaVersionError(
                f"Профиль версии {version} не соответствует схеме: {error.error_count()} ошибок"
            ) from error

    def _version(self) -> int:
        raw = str(self._body.get("schema_version", 1))
        try:
            return int(raw)
        except ValueError as error:
            raise SchemaVersionError(f"Версия схемы профиля не число: {raw}") from error
