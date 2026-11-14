from pydantic import PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(BaseSettings):
    """Every setting of the service as read from environment variables."""

    model_config = SettingsConfigDict(frozen=True, extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./cargo.db"
    storage_dir: str = "./storage"
    soffice_dir: str = ""
    soffice_cache_days: PositiveInt = 7
    llm_provider: str = "vsk"
    llm_allow_external: bool = False
    llm_api_url: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = ""
    llm_response_format: str = "prompt"
    llm_max_tokens: int = 16384
    llm_thinking_budget: int = 0
    llm_max_concurrency: PositiveInt = 4
    llm_timeout: float = 60.0
    llm_total_timeout: float = 300.0
    llm_retry_attempts: PositiveInt = 5
    llm_retry_pause: float = 5.0
    llm_empty_attempts: PositiveInt = 3
    llm_empty_pause: float = 1.0
    llm_verify_tls: bool = True
    llm_ca_bundle: str = ""
    anthropic_api_url: str = "https://api.anthropic.com/v1/messages"
    anthropic_api_key: SecretStr = SecretStr("")
    anthropic_model: str = "claude-sonnet-5-5"
    anthropic_effort: str = ""
    gemini_api_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = ""
    worker_max_jobs: int = 2
    semantic_threads: int = 0
    semantic_pack_size: PositiveInt = 100
    worker_poll_interval: float = 1.0
    worker_job_timeout: float = 600.0
    worker_max_attempts: int = 3
    worker_beat_interval: float = 30.0
    worker_purge_interval: float = 86400.0
    journal_retention_months: PositiveInt = 3
    app_version: str = ""
    cards_dir: str = "cards"
    prompts_version: str = ""
    keycloak_url: str = ""
    keycloak_realm: str = ""
    keycloak_client_id: str = ""
    keycloak_client_secret: SecretStr = SecretStr("")
    keycloak_role_user: str = "cargo_user"
    keycloak_role_expert: str = "cargo_expert"
    keycloak_role_admin: str = "cargo_admin"
    session_secret: SecretStr = SecretStr("")
    session_secure: bool = True
    session_hours: PositiveInt = 12
    app_base_url: str = ""
    auth_disabled: bool = False
    auth_dev_mode: bool = False
    auth_dev_user_id: str = "dev-user"

    def __init__(self, file: str = "") -> None:
        super().__init__(_env_file=file or None)
