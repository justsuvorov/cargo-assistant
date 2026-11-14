from typing import Final, Protocol, final

from app.core.journal import Journal
from app.core.schema.environment import Environment
from app.llm.chat import (
    Budget,
    Chat,
    Form,
    GoogleBudget,
    GuidedJson,
    JsonObject,
    JsonSchema,
    Prompted,
)
from app.llm.claude import Claude
from app.llm.deadline import Cadence, Rhythm
from app.llm.errors import MisconfiguredError
from app.llm.ledger import Ledger, Origin, Route
from app.llm.model import Model, Strict, Throttled
from app.llm.pool import Pool, Shared, Verified
from app.llm.probe import Inventory, Listing, Probe, Survey, Unlisted
from app.llm.provider import Backend, Insistent
from app.llm.wire import Bearer, Keyed, Patient


class Assembly(Protocol):
    """Composition of the model client from the settings of the process."""

    def model(self) -> Model: ...

    def probe(self, parallel: int) -> Survey: ...


@final
class Configured:
    """Assembly that reads LLM_PROVIDER and the settings of the chosen provider; it owns the one
    semaphore of the process, so a process builds exactly one assembly. External providers are
    refused unless LLM_ALLOW_EXTERNAL is true, because client data must stay in the VSK contour."""

    __slots__ = ("_environment", "_journal", "_ledger", "_pool")

    def __init__(self, environment: Environment, journal: Journal, ledger: Ledger) -> None:
        self._environment: Final = environment
        self._journal: Final = journal
        self._ledger: Final = ledger
        self._pool: Final[Pool] = Shared(
            Verified(environment, journal), environment.llm_max_concurrency
        )

    def model(self) -> Model:
        return Throttled(
            Strict(
                Insistent(
                    next(
                        iter(
                            self._providers(
                                Rhythm(
                                    self._environment.llm_retry_attempts,
                                    self._environment.llm_retry_pause,
                                )
                            ).values()
                        )
                    ),
                    Rhythm(self._environment.llm_empty_attempts, self._environment.llm_empty_pause),
                    self._journal,
                ),
                self._origin(),
                self._ledger,
                self._environment.llm_total_timeout,
            ),
            self._pool.gate(),
        )

    def probe(self, parallel: int) -> Survey:
        return Probe(self._providers(Rhythm(1, 0.0)), self._inventory(), self._origin(), parallel)

    def _providers(self, cadence: Cadence) -> dict[str, Backend]:
        builders = {"vsk": self._vsk, "anthropic": self._claude, "gemini": self._gemini}
        if self._environment.llm_provider not in builders:
            raise MisconfiguredError(
                f"Неизвестный провайдер модели LLM_PROVIDER={self._environment.llm_provider}, "
                "допустимы vsk, anthropic и gemini"
            )
        return builders[self._environment.llm_provider](cadence)

    def _vsk(self, cadence: Cadence) -> dict[str, Backend]:
        forms: dict[str, Form] = {
            "prompt": Prompted(),
            "json_object": JsonObject(),
            "json_schema": JsonSchema(),
            "guided_json": GuidedJson(),
        }
        chosen = self._environment.llm_response_format
        if chosen not in forms:
            raise MisconfiguredError(
                f"Неизвестный способ ограничить ответ LLM_RESPONSE_FORMAT={chosen}, "
                f"допустимы {', '.join(forms)}"
            )
        endpoint = Patient(
            Bearer(
                self._pool.client(),
                self._required(self._environment.llm_api_url, "LLM_API_URL"),
                self._required(self._environment.llm_api_key.get_secret_value(), "LLM_API_KEY"),
            ),
            cadence,
            self._environment.llm_timeout,
            self._journal,
        )
        return {
            name: Chat(
                endpoint,
                self._required(self._environment.llm_model, "LLM_MODEL"),
                self._environment.llm_max_tokens,
                Budget(self._environment.llm_thinking_budget, form)
                if self._environment.llm_thinking_budget > 0
                else form,
            )
            for name, form in ({chosen: forms[chosen]} | forms).items()
        }

    def _claude(self, cadence: Cadence) -> dict[str, Backend]:
        self._external("Anthropic")
        return {
            "output_config": Claude(
                Patient(
                    Keyed(
                        self._pool.client(),
                        self._environment.anthropic_api_url,
                        self._required(
                            self._environment.anthropic_api_key.get_secret_value(),
                            "ANTHROPIC_API_KEY",
                        ),
                    ),
                    cadence,
                    self._environment.llm_timeout,
                    self._journal,
                ),
                self._required(self._environment.anthropic_model, "ANTHROPIC_MODEL"),
                self._environment.llm_max_tokens,
                {"effort": self._environment.anthropic_effort}
                if self._environment.anthropic_effort
                else {},
            )
        }

    def _gemini(self, cadence: Cadence) -> dict[str, Backend]:
        self._external("Gemini")
        return {
            "json_schema": Chat(
                Patient(
                    Bearer(
                        self._pool.client(),
                        self._environment.gemini_api_url,
                        self._required(
                            self._environment.gemini_api_key.get_secret_value(), "GEMINI_API_KEY"
                        ),
                    ),
                    cadence,
                    self._environment.llm_timeout,
                    self._journal,
                ),
                self._required(self._environment.gemini_model, "GEMINI_MODEL"),
                self._environment.llm_max_tokens,
                GoogleBudget(self._environment.llm_thinking_budget, JsonSchema())
                if self._environment.llm_thinking_budget > 0
                else JsonSchema(),
            )
        }

    def _external(self, name: str) -> None:
        if not self._environment.llm_allow_external:
            raise MisconfiguredError(
                f"Провайдер {name} — внешний сервис, данные клиента туда отправлять нельзя; "
                "чтобы работать с ним на обезличенных или вымышленных данных, "
                "задайте LLM_ALLOW_EXTERNAL=true"
            )
        self._journal.warning(
            f"Выбран внешний провайдер модели {name}, отправляйте ему только "
            "обезличенные или вымышленные данные",
            0,
            0,
        )

    def _required(self, value: str, name: str) -> str:
        if not value:
            raise MisconfiguredError(
                f"Не задана переменная {name} для провайдера {self._environment.llm_provider}"
            )
        return value

    def _origin(self) -> Origin:
        return Route(
            self._environment.llm_provider,
            {
                "vsk": self._environment.llm_model,
                "anthropic": self._environment.anthropic_model,
                "gemini": self._environment.gemini_model,
            }.get(self._environment.llm_provider, ""),
        )

    def _inventory(self) -> Inventory:
        address = {
            "vsk": (self._environment.llm_api_url, self._environment.llm_api_key),
            "gemini": (self._environment.gemini_api_url, self._environment.gemini_api_key),
        }
        if self._environment.llm_provider not in address:
            return Unlisted()
        url, key = address[self._environment.llm_provider]
        return Listing(
            self._pool.client(),
            url.removesuffix("/").removesuffix("/chat/completions") + "/models",
            key.get_secret_value(),
        )
