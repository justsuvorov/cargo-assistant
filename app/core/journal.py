from typing import Final, Protocol, final


class Sink(Protocol):
    """Destination of formatted log lines, such as a standard logger."""

    def info(self, msg: str, *args: object) -> None: ...

    def warning(self, msg: str, *args: object) -> None: ...

    def error(self, msg: str, *args: object) -> None: ...


class Journal(Protocol):
    """Log of events that always names the job and the declaration they belong to."""

    def info(self, message: str, job_id: int, declaration_id: int) -> None: ...

    def warning(self, message: str, job_id: int, declaration_id: int) -> None: ...

    def error(self, message: str, job_id: int, declaration_id: int) -> None: ...


@final
class LogJournal:
    """Journal that writes one-sentence Russian lines with job and declaration identifiers."""

    __slots__ = ("_sink",)

    def __init__(self, sink: Sink) -> None:
        self._sink: Final = sink

    def info(self, message: str, job_id: int, declaration_id: int) -> None:
        self._sink.info("%s, job_id=%d, declaration_id=%d", message, job_id, declaration_id)

    def warning(self, message: str, job_id: int, declaration_id: int) -> None:
        self._sink.warning("%s, job_id=%d, declaration_id=%d", message, job_id, declaration_id)

    def error(self, message: str, job_id: int, declaration_id: int) -> None:
        self._sink.error("%s, job_id=%d, declaration_id=%d", message, job_id, declaration_id)
