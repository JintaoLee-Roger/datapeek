"""Opt-in real-file benchmarks, isolated processes; never evicts OS caches."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from smoke_real_data import CASES, ROOT

CHILD = '''import runpy, resource, sys, time
sys.argv = sys.argv[1:]
start = time.perf_counter()
runpy.run_path(sys.argv[0], run_name="__main__")
print("BENCH " + __import__('json').dumps(dict(process_seconds=time.perf_counter()-start, peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)))
'''

if __name__ == '__main__':
    results = []
    with tempfile.TemporaryDirectory(prefix='datapeek-bench-') as temp:
        for name, relative in CASES:
            modes = [None, ['iline', 'xline'], ['iline', 'xline', 'time']] if name in ('volume_zarr', 'baiyun', 'channels', 'fans') else [None]
            for mode in modes:
                folder = Path(temp) / f'{name}-{len(results)}'
                folder.mkdir()
                request = dict(protocolVersion=1, requestId=name, operation='render', targetPath=str(Path('/home/jtli/data') / relative), rendererId='builtin:npy' if relative.endswith('.npy') else 'personal:geoscience.py:geoscience', readerPaths=[str(ROOT/'examples/readers')], options={'slices': mode} if mode else {})
                (folder / 'request.json').write_text(json.dumps(request))
                start = time.perf_counter()
                completed = subprocess.run([sys.executable, '-c', CHILD, str(ROOT/'python/runner.py'), '--request', str(folder/'request.json')], capture_output=True, text=True, timeout=120)
                if completed.returncode:
                    raise RuntimeError(completed.stderr)
                wall = time.perf_counter()-start
                response = json.loads((folder/'response.json').read_text())
                lines = completed.stdout.splitlines()
                stats = json.loads(next(line[6:] for line in lines if line.startswith('BENCH ')))
                row = dict(case=name, slices=mode, wall_seconds=round(wall, 4), **stats, status=response['status'], read_log=[x for x in lines if x.startswith('DataPeek')])
                if response['status'] != 'ok':
                    row['error'] = response['error']['message']
                results.append(row)
                print(json.dumps(row), flush=True)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(results, indent=2)+'\n')
