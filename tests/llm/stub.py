import json
import socket
import socketserver
import ssl
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

from app.llm.deadline import Deadline
from app.llm.errors import UnavailableError
from app.llm.messages import Message
from app.llm.provider import Answered, Reply
from app.llm.schema.shape import Shape


class Stub:
    """Local gateway script: answers in the given order, the last one repeating, and every
    request body, header set and path is remembered; a delayed answer is dropped once the
    gateway closes, so a hanging request never outlives its test."""

    def __init__(self, script: list[tuple[int, str, float]]) -> None:
        self.script = list(script)
        self.raw: list[str] = []
        self.headers: list[dict[str, str]] = []
        self.paths: list[str] = []
        self.lock = threading.Lock()
        self.closed = threading.Event()
        self.base = ""

    def url(self) -> str:
        return f"{self.base}/v1/chat/completions"

    def roles(self, index: int) -> list[str]:
        return [message["role"] for message in json.loads(self.raw[index])["messages"]]

    def take(self, path: str, headers: dict[str, str], body: bytes) -> tuple[int, str, float]:
        with self.lock:
            self.paths.append(path)
            self.headers.append(headers)
            self.raw.append(body.decode() or "{}")
            return self.script.pop(0) if len(self.script) > 1 else self.script[0]


class Handler(BaseHTTPRequestHandler):
    """Request handler that answers from the script of its stub."""

    def __init__(
        self,
        stub: Stub,
        request: socket.socket,
        address: tuple[str, int],
        server: socketserver.BaseServer,
    ) -> None:
        self.stub = stub
        super().__init__(request, address, server)

    def do_POST(self) -> None:
        self.answer(self.rfile.read(int(self.headers.get("Content-Length", "0"))))

    def do_GET(self) -> None:
        self.answer(b"")

    def answer(self, body: bytes) -> None:
        status, text, delay = self.stub.take(self.path, dict(self.headers.items()), body)
        if self.stub.closed.wait(delay):
            return
        payload = text.encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@contextmanager
def gateway(script: list[tuple[int, str, float]]) -> Iterator[Stub]:
    stub = Stub(script)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, stub))
    thread = threading.Thread(target=server.serve_forever, args=(0.01,), daemon=True)
    thread.start()
    stub.base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield stub
    finally:
        stub.closed.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def client() -> httpx.Client:
    return httpx.Client(verify=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT))


def refusal(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("Шлюз в тесте отказал в соединении", request=request)


def completion(content: str, tokens: tuple[int, int] = (11, 7)) -> str:
    return json.dumps(
        {
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": tokens[0], "completion_tokens": tokens[1]},
        },
        ensure_ascii=False,
    )


def silence() -> str:
    return json.dumps(
        {"choices": [{"index": 0, "message": {"role": "assistant", "content": None}}]}
    )


def envelope(text: str, tokens: tuple[int, int] = (13, 5)) -> str:
    return json.dumps(
        {
            "content": [{"type": "thinking", "thinking": ""}, {"type": "text", "text": text}],
            "usage": {"input_tokens": tokens[0], "output_tokens": tokens[1]},
            "stop_reason": "end_turn",
        },
        ensure_ascii=False,
    )


class Scripted:
    """Backend double that returns the given texts one after another, the last one repeating,
    and remembers every conversation it was given."""

    def __init__(self, texts: list[str]) -> None:
        self.texts = list(texts)
        self.calls = 0
        self.conversations: list[tuple[Message, ...]] = []
        self.shapes: list[str] = []

    def reply(self, messages: tuple[Message, ...], shape: Shape, deadline: Deadline) -> Reply:
        if not deadline.left():
            raise UnavailableError("Время ожидания модели в тесте истекло")
        self.calls += 1
        self.conversations.append(messages)
        self.shapes.append(shape.name())
        return Answered(self.texts.pop(0) if len(self.texts) > 1 else self.texts[0], (3, 2))


class Quiet:
    """Journal that drops every line, since logging is off in tests."""

    def info(self, message: str, job_id: int, declaration_id: int) -> None:
        pass

    def warning(self, message: str, job_id: int, declaration_id: int) -> None:
        pass

    def error(self, message: str, job_id: int, declaration_id: int) -> None:
        pass
