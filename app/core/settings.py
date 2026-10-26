from pathlib import Path
from typing import Final, Protocol, final

from app.core.schema.environment import Environment


class Settings(Protocol):
    """Configuration of the service that the rest of the code asks questions about."""

    def database(self) -> str: ...

    def storage(self) -> Path: ...

    def jobs(self) -> int: ...

    def attempts(self) -> int: ...

    def poll(self) -> float: ...

    def timeout(self) -> float: ...

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

    def jobs(self) -> int:
        return self._environment.worker_max_jobs

    def attempts(self) -> int:
        return self._environment.worker_max_attempts

    def poll(self) -> float:
        return self._environment.worker_poll_interval

    def timeout(self) -> float:
        return self._environment.worker_job_timeout

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
