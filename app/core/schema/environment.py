from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(BaseSettings):
    """Every setting of the service as read from environment variables."""

    model_config = SettingsConfigDict(frozen=True, extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./cargo.db"
    storage_dir: str = "./storage"
    llm_api_url: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = ""
    llm_max_tokens: int = 4096
    llm_thinking_budget: int = 0
    llm_max_concurrency: int = 4
    llm_timeout: float = 120.0
    worker_max_jobs: int = 2
    worker_poll_interval: float = 1.0
    worker_job_timeout: float = 600.0
    worker_max_attempts: int = 3
    keycloak_url: str = ""
    keycloak_realm: str = ""
    keycloak_client_id: str = ""
    keycloak_role_user: str = "cargo_user"
    keycloak_role_expert: str = "cargo_expert"
    keycloak_role_admin: str = "cargo_admin"
    auth_dev_mode: bool = False

    def __init__(self, file: str = "") -> None:
        super().__init__(_env_file=file or None)
