"""Bounded preview cache for built-ins and opt-in custom array readers."""
import hashlib
from importlib.metadata import version, PackageNotFoundError
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time


def fingerprint(target):
    path = Path(target).resolve()
    # Any member of a Zarr store depends on the store metadata as well.
    for ancestor in path.parents:
        if ancestor.suffix.lower()=='.zarr':
            path = ancestor
            break
    digest = hashlib.sha256(str(path).encode())
    def add(item):
        stat = item.stat()
        digest.update(str((str(item.relative_to(path) if item != path else '.'), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)).encode())
    add(path)
    if path.is_dir():
        for root, dirs, files in os.walk(path):
            dirs.sort()
            for name in sorted(dirs + files):
                item = Path(root) / name
                if item.is_symlink():
                    raise ValueError('Cache disabled for stores containing symlinks')
                add(item)
    return digest.hexdigest()


class PreviewCache:
    def __init__(self, request):
        config = request['cache']
        self.root = Path(config['directory'])
        self.max_entries = max(1, min(10000, int(config.get('maxEntries', 100))))
        self.max_bytes = max(1, min(16384, int(config.get('maxMiB', 512)))) * 1024**2
        self.max_age = max(1, min(365, int(config.get('maxAgeDays', 7)))) * 86400
        self.source = fingerprint(request['targetPath'])
        code = hashlib.sha256()
        for p in sorted(p for p in Path(__file__).parent.iterdir() if p.suffix in ('.py', '.html', '.json')) + [Path(__file__).parent.parent / 'runner.py']:
            code.update(p.read_bytes())
        for filename in request.get('readerCodeFiles',[]):
            code.update(str(filename).encode())
            code.update(Path(filename).read_bytes())
        executable = Path(sys.executable).stat()
        versions = {}
        for name in ('numpy', 'matplotlib', 'h5py', 'zarr', 'seisvol', 'cigvis'):
            try:
                versions[name] = version(name)
            except PackageNotFoundError:
                versions[name] = None
        # Store freshness is shared, but every event file is a distinct preview.
        key = dict(target=str(Path(request['targetPath']).absolute()), dependencies=versions, source=self.source, code=code.hexdigest(), python=(sys.executable, sys.version, executable.st_mtime_ns), renderer=request['rendererId'], options=request.get('options', {}), limits=request.get('limits', {}))
        self.key = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.entry = self.root / self.key
        self.prune()

    def prune(self):
        now = time.time()
        entries = []
        for item in self.root.iterdir():
            if not item.is_dir() or item.is_symlink():
                continue
            try:
                age = now - item.stat().st_mtime
                if item.name.startswith('.pending-'):
                    if age > 86400:
                        shutil.rmtree(item, ignore_errors=True)
                    continue
                if not re.fullmatch('[0-9a-f]{64}', item.name):
                    continue
                size = sum(p.stat().st_size for p in item.iterdir() if p.is_file())
                if age > self.max_age:
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    entries.append((item.stat().st_mtime, size, item))
            except FileNotFoundError:
                continue
        total = sum(e[1] for e in entries)
        count = len(entries)
        for _, size, item in sorted(entries):
            if total <= self.max_bytes and count <= self.max_entries:
                break
            shutil.rmtree(item, ignore_errors=True)
            total -= size
            count -= 1

    def restore(self, directory):
        try:
            meta = json.loads((self.entry / 'meta.json').read_text())
            name = meta.get('name', 'figure.png')
            if name not in ('figure.png', 'quick.html'):
                return None
            source = self.entry / name
            content = source.read_bytes()
            if len(content) != meta['size'] or hashlib.sha256(content).hexdigest() != meta['sha256']:
                return None
            artifacts = directory / 'artifacts'
            artifacts.mkdir(exist_ok=True)
            (artifacts / name).write_bytes(content)
            try:
                os.utime(self.entry, None)
            except FileNotFoundError:
                pass
            print('DataPeek cache HIT', self.key, flush=True)
            return {'artifact': {'kind': 'image' if name == 'figure.png' else 'html', 'entry': 'artifacts/' + name, 'mimeType': 'image/png' if name == 'figure.png' else 'text/html', 'files': ['artifacts/' + name]}}
        except (OSError, ValueError, KeyError):
            return None

    def save(self, result, directory, target):
        if fingerprint(target) != self.source:
            return
        artifact = result['artifact']
        name = Path(artifact['entry']).name
        if not (artifact['kind'] == 'image' and name == 'figure.png' or artifact['kind'] == 'html' and name == 'quick.html' and artifact.get('files') == ['artifacts/quick.html']):
            return
        content = (directory / artifact['entry']).read_bytes()
        if len(content) > self.max_bytes:
            return
        pending = Path(tempfile.mkdtemp(prefix='.pending-', dir=self.root))
        try:
            (pending / name).write_bytes(content)
            (pending / 'meta.json').write_text(json.dumps({'name': name, 'size': len(content), 'sha256': hashlib.sha256(content).hexdigest()}))
            try:
                pending.rename(self.entry)
            except OSError:
                # Another process may have populated this key. Replace corrupt entries on next miss.
                if self.entry.exists():
                    shutil.rmtree(self.entry, ignore_errors=True)
                    pending.rename(self.entry)
                else:
                    raise
        finally:
            shutil.rmtree(pending, ignore_errors=True)
        self.prune()
