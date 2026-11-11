from pathlib import Path
from typing import Final, Protocol, final

from app.core.schema.environment import Environment


class Settings(Protocol):
    """Configuration of the service that the rest of the code asks questions about."""

    def database(self) -> str: ...

    def storage(self) -> Path: ...

    def soffice(self) -> Path: ...

    def cache_days(self) -> int: ...

    def jobs(self) -> int: ...

    def attempts(self) -> int: ...

    def poll(self) -> float: ...

    def timeout(self) -> float: ...

    def beat(self) -> float: ...

    def purge(self) -> float: ...

    def months(self) -> int: ...

    def version(self) -> str: ...

    def cards(self) -> Path: ...

    def prompts(self) -> str: ...

    def model(self) -> str: ...

    def development(self) -> bool: ...

    def issuer(self) -> str: ...

    def audience(self) -> str: ...

    def certs(self) -> str: ...

    def role(self, name: str) -> str: ...


@final
class EnvSettings:
    """Settings taken from environment variables and never changed afterwards."""

    __slots__ = ("_environment",)

    def __init__(self, environment: Environment) -> None:
        self._environment: Final = environment

    def database(self) -> str:
        return self._environment.database_url

    def storage(self) -> Path:
        return Path(self._environment.storage_dir)

    def soffice(self) -> Path:
        return Path(self._environment.soffice_dir or self.storage() / "soffice")

    def cache_days(self) -> int:
        return self._environment.soffice_cache_days

    def jobs(self) -> int:
        return self._environment.worker_max_jobs

    def attempts(self) -> int:
        return self._environment.worker_max_attempts

    def poll(self) -> float:
        return self._environment.worker_poll_interval

    def timeout(self) -> float:
        return self._environment.worker_job_timeout

    def beat(self) -> float:
        return self._environment.worker_beat_interval

    def purge(self) -> float:
        return self._environment.worker_purge_interval

    def months(self) -> int:
        return self._environment.journal_retention_months

    def version(self) -> str:
        return self._environment.app_version

    def cards(self) -> Path:
        return Path(self._environment.cards_dir)

    def prompts(self) -> str:
        return self._environment.prompts_version

    def model(self) -> str:
        return {
            "anthropic": self._environment.anthropic_model,
            "gemini": self._environment.gemini_model,
        }.get(self._environment.llm_provider, self._environment.llm_model)

    def development(self) -> bool:
        return self._environment.auth_dev_mode

    def issuer(self) -> str:
        return f"{self._environment.keycloak_url}/realms/{self._environment.keycloak_realm}"

    def audience(self) -> str:
        return self._environment.keycloak_client_id

    def certs(self) -> str:
        return f"{self.issuer()}/protocol/openid-connect/certs"

    def role(self, name: str) -> str:
        return {
            "user": self._environment.keycloak_role_user,
            "expert": self._environment.keycloak_role_expert,
            "admin": self._environment.keycloak_role_admin,
        }[name]
