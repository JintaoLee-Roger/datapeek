"""One-shot runner. stdout/stderr are logs; response.json is the protocol."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import traceback
from html.parser import HTMLParser

# Load the bundled SDK before adding project paths.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from datapeek import viewer

os.environ["MPLBACKEND"] = "Agg"


class BackendError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def load_module(path, source):
    before = dict(viewer.renderers)
    viewer.source = source
    try:
        module_name = "_datapeek_" + hashlib.sha256(str(path).encode()).hexdigest()
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        # Compile source directly so immediate edits never reuse stale bytecode.
        exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    except Exception:
        viewer.renderers = before
        raise
    finally:
        viewer.source = "builtin"


def discover(root, selected=None):
    from datapeek import builtin  # noqa: F401
    diagnostics = []
    if not root:
        return diagnostics
    folder = Path(root) / ".datapeek"
    sys.path[:0] = [str(root), str(folder)]
    for path in sorted(folder.glob("*.py")):
        if path.name.startswith("_"):
            continue
        source = "workspace:" + path.name
        if selected and not selected.startswith(source + ":"):
            continue
        try:
            load_module(path, source)
        except Exception as exc:
            diagnostics.append({"source": source, "message": str(exc), "traceback": traceback.format_exc()})
    return diagnostics


class ExternalScripts(HTMLParser):
    """Externalize Python Plotly-generated scripts, preserving script order."""
    def __init__(self, directory):
        super().__init__(convert_charrefs=False)
        self.directory = directory
        self.parts = []
        self.script = None
        self.files = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            if any(k == "src" for k, _ in attrs):
                raise BackendError("UNSUPPORTED_RESULT", "External scripts are not supported")
            self.script = []
        else:
            self.parts.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if tag == "script" and self.script is not None:
            name = f"script-{len(self.files)}.js"
            (self.directory / name).write_text("".join(self.script), encoding="utf-8")
            self.files.append(name)
            self.parts.append(f'<script nonce="__DATA_NONCE__" src="__DATA_ASSET_{name}__"></script>')
            self.script = None
        else:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        (self.script if self.script is not None else self.parts).append(data)

    def handle_entityref(self, name):
        self.handle_data(f"&{name};")

    def handle_charref(self, name):
        self.handle_data(f"&#{name};")

    def handle_comment(self, data):
        self.parts.append(f"<!--{data}-->")

    def handle_decl(self, decl):
        self.parts.append(f"<!{decl}>")


def adapt(result, directory):
    # Avoid importing unused scientific libraries.
    if any(cls.__module__.startswith("matplotlib.") for cls in type(result).__mro__):
        from matplotlib.figure import Figure
        if isinstance(result, Figure):
            try:
                result.savefig(directory / "figure.png", dpi=150)
            finally:
                from matplotlib import pyplot
                pyplot.close(result)
            return {"kind": "image", "entry": "figure.png", "mimeType": "image/png", "files": ["figure.png"]}
    if any(cls.__module__.startswith("plotly.") for cls in type(result).__mro__):
        from plotly.basedatatypes import BaseFigure
        if isinstance(result, BaseFigure):
            from plotly.offline import get_plotlyjs
            import plotly.io as pio
            (directory / "plotly.min.js").write_text(get_plotlyjs(), encoding="utf-8")
            html = pio.to_html(result, include_plotlyjs=False, include_mathjax=False, full_html=True, default_width="100%", default_height="100vh", config={"responsive": True})
            parser = ExternalScripts(directory)
            parser.feed(html)
            parser.close()
            html = "".join(parser.parts).replace("<head>", '<head>__DATA_CSP__<script nonce="__DATA_NONCE__" src="__DATA_ASSET_plotly.min.js__"></script>', 1)
            (directory / "figure.html").write_text(html, encoding="utf-8")
            return {"kind": "html", "entry": "figure.html", "mimeType": "text/html", "files": ["figure.html", "plotly.min.js", *parser.files]}
    raise BackendError("UNSUPPORTED_RESULT", f"Return a matplotlib Figure or Python Plotly Figure, got {type(result).__name__}")


def run(request, directory):
    if request.get("protocolVersion") != 1:
        raise BackendError("PROTOCOL_ERROR", "Unsupported protocol version")
    operation = request.get("operation")
    if operation not in ("discover", "render"):
        raise BackendError("PROTOCOL_ERROR", "Unknown operation")
    diagnostics = discover(request.get("workspaceRoot"), request.get("rendererId") if operation == "render" else None)
    if operation == "discover":
        return {"renderers": [r.describe() for r in viewer.renderers.values()], "diagnostics": diagnostics}
    renderer_id = request["rendererId"]
    if renderer_id not in viewer.renderers:
        raise BackendError("RENDERER_NOT_FOUND", f"Cannot load {renderer_id}: {diagnostics}")
    options = request.get("options", {})
    if not isinstance(options, dict):
        raise BackendError("PROTOCOL_ERROR", "options must be an object")
    target = Path(request["targetPath"])
    if not target.is_absolute() or not target.is_file():
        raise BackendError("UNSUPPORTED_DATA", f"Not a readable file: {target}")
    artifacts = directory / "artifacts"
    artifacts.mkdir()
    result = viewer.renderers[renderer_id].render(target, options)
    artifact = adapt(result, artifacts)
    files = [artifacts / name for name in artifact["files"]]
    limit = request.get("limits", {}).get("maxArtifactBytes", 32 * 1024 * 1024)
    if sum(p.stat().st_size for p in files) > limit:
        raise BackendError("OUTPUT_TOO_LARGE", f"Visualization exceeds {limit} bytes; reduce data in your renderer")
    artifact["files"] = ["artifacts/" + name for name in artifact["files"]]
    artifact["entry"] = "artifacts/" + artifact["entry"]
    return {"artifact": artifact}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    args = parser.parse_args()
    request_path = Path(args.request).resolve()
    response = {"protocolVersion": 1, "requestId": None}
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
        response["requestId"] = request.get("requestId")
        response.update(run(request, request_path.parent), status="ok")
    except Exception as exc:
        code = getattr(exc, "code", "RENDER_FAILED")
        if isinstance(exc, ModuleNotFoundError):
            code = "DEPENDENCY_MISSING"
        elif isinstance(exc, ValueError):
            code = "UNSUPPORTED_DATA"
        response.update(status="error", error={"code": code, "message": str(exc), "traceback": traceback.format_exc()})
    temporary = request_path.parent / "response.tmp"
    temporary.write_text(json.dumps(response, ensure_ascii=True), encoding="utf-8")
    temporary.replace(request_path.parent / "response.json")


if __name__ == "__main__":
    main()
