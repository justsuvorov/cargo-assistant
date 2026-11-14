import ssl
import threading
from typing import Final, Protocol, final

import httpx

from app.core.journal import Journal
from app.core.schema.environment import Environment
from app.llm.errors import MisconfiguredError


class Trust(Protocol):
    """Rule that tells the HTTP client which certificates of the gateway to believe."""

    def verify(self) -> ssl.SSLContext | bool: ...


@final
class Verified:
    """Trust that follows LLM_VERIFY_TLS and LLM_CA_BUNDLE."""

    __slots__ = ("_environment", "_journal")

    def __init__(self, environment: Environment, journal: Journal) -> None:
        self._environment: Final = environment
        self._journal: Final = journal

    def verify(self) -> ssl.SSLContext | bool:
        if not self._environment.llm_verify_tls:
            self._journal.warning(
                "Проверка TLS-сертификата модели отключена настройкой LLM_VERIFY_TLS",
                0,
                0,
            )
            return False
        context = ssl.create_default_context()
        if self._environment.llm_ca_bundle:
            try:
                context.load_verify_locations(self._environment.llm_ca_bundle)
            except OSError as error:
                raise MisconfiguredError(
                    f"Не удалось прочитать сертификат LLM_CA_BUNDLE="
                    f"{self._environment.llm_ca_bundle}: {error}"
                ) from error
        return context


class Pool(Protocol):
    """Resources shared by all models of one process."""

    def client(self) -> httpx.Client: ...

    def gate(self) -> threading.BoundedSemaphore: ...


@final
class Shared:
    """Pool that opens the single HTTP client of the process on first demand and keeps it, so
    building a model for every job does not leave a connection pool behind each of them."""

    __slots__ = ("_cell", "_gate", "_lock", "_trust")

    def __init__(self, trust: Trust, calls: int) -> None:
        self._trust: Final = trust
        self._gate: Final = threading.BoundedSemaphore(calls)
        self._lock: Final = threading.Lock()
        self._cell: Final[list[httpx.Client]] = []

    def client(self) -> httpx.Client:
        with self._lock:
            if not self._cell:
                self._cell.append(httpx.Client(verify=self._trust.verify()))
            return self._cell[0]

    def gate(self) -> threading.BoundedSemaphore:
        return self._gate
