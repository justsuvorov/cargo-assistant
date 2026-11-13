import json
from pathlib import Path
from typing import Final, Protocol, final

import yaml


class Manifests(Protocol):
    """Release files of a repository, asked about as one set of Kubernetes objects."""

    def kinds(self) -> frozenset[str]: ...

    def value(self, kind: str, name: str, path: str) -> str: ...

    def names(self, kind: str, name: str, path: str) -> tuple[str, ...]: ...

    def text(self, path: str) -> str: ...


@final
class Folder:
    """Manifests read from the yaml files of a folder below the root of the repository."""

    __slots__ = ("_folder", "_root")

    def __init__(self, root: Path, folder: str) -> None:
        self._root: Final = root
        self._folder: Final = folder

    def kinds(self) -> frozenset[str]:
        return frozenset(str(json.loads(text)["kind"]) for text in self._documents())

    def value(self, kind: str, name: str, path: str) -> str:
        node = json.loads(self._found(kind, name))
        for step in path.split("."):
            node = node[int(step) if step.isdigit() else step]
        return str(node)

    def names(self, kind: str, name: str, path: str) -> tuple[str, ...]:
        node = json.loads(self._found(kind, name))
        for step in path.split("."):
            node = node[int(step) if step.isdigit() else step]
        return tuple(str(key) for key in node)

    def text(self, path: str) -> str:
        return (self._root / path).read_text(encoding="utf-8")

    def _found(self, kind: str, name: str) -> str:
        return next(
            text
            for text in self._documents()
            if json.loads(text)["kind"] == kind
            and name in ("", json.loads(text)["metadata"]["name"])
        )

    def _documents(self) -> tuple[str, ...]:
        return tuple(
            json.dumps(document)
            for path in sorted((self._root / self._folder).glob("*.yaml"))
            if path.name != "secret.yaml"
            for document in yaml.safe_load_all(path.read_text(encoding="utf-8"))
            if document
        )
