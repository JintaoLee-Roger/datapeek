"""Measure built-in PNG cache miss/hit using the real files (read-only)."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from smoke_real_data import CASES, ROOT

if __name__ == '__main__':
    records = []
    with tempfile.TemporaryDirectory(prefix='datapeek-cache-bench-') as temp:
        root = Path(temp)
        for name, relative in CASES:
            if name not in ('whale', 'baiyun', 'fans'):
                continue
            for attempt in ('miss', 'hit'):
                folder = root / (name + '-' + attempt); folder.mkdir()
                request = dict(protocolVersion=1, requestId=name, operation='render', targetPath=str(Path('/home/jtli/data') / relative), rendererId='builtin:npy' if relative.endswith('.npy') else 'personal:geoscience.py:geoscience', readerPaths=[str(ROOT/'examples/readers')], options={}, cache=dict(enabled=True, directory=str(root/'cache')))
                (folder/'request.json').write_text(json.dumps(request))
                start = time.perf_counter()
                result = subprocess.run([sys.executable, str(ROOT/'python/runner.py'), '--request', str(folder/'request.json')], capture_output=True, text=True, check=True, timeout=120)
                seconds = time.perf_counter() - start
                response = json.loads((folder/'response.json').read_text())
                assert response['status'] == 'ok', response
                if attempt == 'hit':
                    assert 'cache HIT' in result.stdout and 'full slice' not in result.stdout and 'read DAS' not in result.stdout
                    assert (folder/'artifacts/figure.png').read_bytes() == (root/(name+'-miss')/'artifacts/figure.png').read_bytes()
                row = dict(case=name, cache=attempt, runner_seconds=round(seconds, 4), log=result.stdout.splitlines())
                records.append(row); print(json.dumps(row), flush=True)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(records, indent=2)+'\n')
