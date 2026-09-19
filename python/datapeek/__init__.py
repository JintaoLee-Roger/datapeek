"""DataPeek's small, dependency-free renderer registration API."""
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Callable, Mapping

API_VERSION = 1


@dataclass
class Array:
    """Array or lazy sliceable data, optional display defaults and title.

    Use a contextmanager reader to keep files open and release resources.
    """
    data: Any
    options: Mapping[str, Any] = field(default_factory=dict)
    title: str | None = None


@dataclass(frozen=True)
class Renderer:
    id: str
    name: str
    extensions: tuple[str, ...]
    render: Callable[[Path, Mapping[str, Any]], Any]
    source: str
    kind: str = "figure"
    patterns: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    cache: bool = False
    file: str | None = None

    def matches(self, path):
        name = Path(path).as_posix()
        return (any(name.lower().endswith(e) for e in self.extensions)
                and (not self.patterns or any(fnmatchcase(name, p) for p in self.patterns))
                and not any(fnmatchcase(name, p) for p in self.exclude))

    def describe(self):
        return {"id": self.id, "name": self.name,
                "extensions": list(self.extensions), "source": self.source, "kind": self.kind,
                "patterns": list(self.patterns), "exclude": list(self.exclude), "cache": self.cache}


class Registry:
    def __init__(self):
        self.renderers: dict[str, Renderer] = {}
        self.source = "builtin"
        self.file = None

    def register(self, *, name: str, extensions: list[str], id: str | None = None, patterns=(), exclude=(), _kind="figure", cache=False):
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
            self.renderers[key] = Renderer(key, name, tuple(e.lower() for e in extensions), fn, self.source, _kind, tuple(patterns), tuple(exclude), cache or self.source=="builtin", self.file)
            return fn
        return decorate

    def reader(self, *, name, extensions, id=None, patterns=(), exclude=(), cache=False):
        """Register an array reader; quick/detail/3D reuse the same data source."""
        return self.register(name=name, extensions=extensions, id=id, patterns=patterns, exclude=exclude, _kind='array', cache=cache)


viewer = Registry()
