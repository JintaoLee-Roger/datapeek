"""DataPeek's small, dependency-free renderer registration API."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

API_VERSION = 1


@dataclass(frozen=True)
class Renderer:
    id: str
    name: str
    extensions: tuple[str, ...]
    render: Callable[[Path, Mapping[str, Any]], Any]
    source: str

    def describe(self):
        return {"id": self.id, "name": self.name,
                "extensions": list(self.extensions), "source": self.source}


class Registry:
    def __init__(self):
        self.renderers: dict[str, Renderer] = {}
        self.source = "builtin"

    def register(self, *, name: str, extensions: list[str], id: str | None = None):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Renderer name must be nonempty")
        if not isinstance(extensions, list) or any(
            not isinstance(ext, str) or not ext.startswith(".") or "/" in ext or "\\" in ext
            for ext in extensions
        ):
            raise ValueError("extensions must be a list of dotted file suffixes")

        def decorate(fn):
            local_id = id or fn.__name__
            if not isinstance(local_id, str) or not local_id or ":" in local_id:
                raise ValueError("Renderer id must be nonempty and cannot contain ':'")
            key = f"{self.source}:{local_id}"
            if key in self.renderers:
                raise ValueError(f"Duplicate renderer id: {key}")
            self.renderers[key] = Renderer(key, name, tuple(e.lower() for e in extensions), fn, self.source)
            return fn
        return decorate


viewer = Registry()
