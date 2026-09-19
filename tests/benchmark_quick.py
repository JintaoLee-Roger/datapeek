"""Opt-in Linux real-data benchmark. Evicts only named source files (advisory), never global caches.
Each trial launches a fresh Python. Python/library files remain warm; no claim of cold boot.
Usage: python tests/benchmark_quick.py /tmp/results.json
"""
import ctypes
import json
import mmap
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
CASES={
 'ridgecrest': '/home/jtli/data/das/earthquake/Ridgecrest/part_00.zarr/data/7.0.0',
 'baiyun': '/home/jtli/data/seismic/seismic_data/baiyun/sx_cut.npy',
 'channels': '/home/jtli/data/seismic/seismic_data/channels/channels_origin_h651x601x401.dat',
}

def residency(path):
    with open(path,'rb') as f:
        size=os.fstat(f.fileno()).st_size
        with mmap.mmap(f.fileno(),0,access=mmap.ACCESS_COPY) as memory:
            pages=(size+mmap.PAGESIZE-1)//mmap.PAGESIZE
            vector=(ctypes.c_ubyte*pages)()
            address=ctypes.addressof(ctypes.c_char.from_buffer(memory))
            libc=ctypes.CDLL(None,use_errno=True)
            if libc.mincore(ctypes.c_void_p(address),ctypes.c_size_t(size),vector):
                raise OSError(ctypes.get_errno(),'mincore')
            return dict(residentPages=sum(v&1 for v in vector),pages=pages)

def evict(path):
    with open(path,'rb') as f:
        os.posix_fadvise(f.fileno(),0,0,os.POSIX_FADV_DONTNEED)
    return residency(path)

def run(folder,target,backend,cache=False):
    folder.mkdir()
    req=dict(protocolVersion=1,requestId=folder.name,operation='render',targetPath=target,
        rendererId='personal:geoscience.py:geoscience',readerPaths=[str(ROOT/'examples/readers')],
        options=dict(backend=backend),cache=dict(enabled=cache,directory=str(folder.parent/'cache')))
    file=folder/'request.json';file.write_text(json.dumps(req))
    start=time.perf_counter()
    proc=subprocess.run([sys.executable,str(ROOT/'python/runner.py'),'--request',str(file)],capture_output=True,text=True,check=True)
    seconds=time.perf_counter()-start
    response=json.loads((folder/'response.json').read_text())
    if response['status']!='ok':raise RuntimeError(response)
    return dict(seconds=seconds,artifactBytes=sum((folder/p).stat().st_size for p in response['artifact']['files']),logs=proc.stdout)

def main():
    results=[]
    with tempfile.TemporaryDirectory(prefix='datapeek-speed-') as tmp:
        base=Path(tmp);count=0
        for name,target in CASES.items():
            for rep in range(3):
                # Alternate ordering to reduce load/order bias. Each warm run follows its own cold run.
                for backend in (['matplotlib','canvas'] if rep%2==0 else ['canvas','matplotlib']):
                    before=evict(target)
                    for state in ['source_eviction_requested','source_warm']:
                        count+=1
                        before=residency(target)
                        r=run(base/str(count),target,backend)
                        r.update(case=name,backend=backend,state=state,rep=rep,residencyBefore=before,residencyAfter=residency(target))
                        results.append(r)
                        print(name,backend,state,round(r['seconds'],3),before,flush=True)
            for backend in ['matplotlib','canvas']:
                count+=1;run(base/str(count),target,backend,True)
                for rep in range(3):
                    count+=1;r=run(base/str(count),target,backend,True)
                    assert 'cache HIT' in r['logs']
                    r.update(case=name,backend=backend,state='preview_cache_hit',rep=rep);results.append(r)
    report=dict(notes='Fresh Python per trial. Library/metadata files warm. Source-only fadvise DONTNEED verified with mincore; storage/server caches uncontrolled. No VS Code/SSH/UI time included.',trials=results,summary=[])
    for name in CASES:
        for backend in ['matplotlib','canvas']:
            for state in ['source_eviction_requested','source_warm','preview_cache_hit']:
                rows=[r for r in results if (r['case'],r['backend'],r['state'])==(name,backend,state)]
                report['summary'].append(dict(case=name,backend=backend,state=state,medianSeconds=statistics.median(r['seconds'] for r in rows),artifactBytes=rows[0]['artifactBytes']))
    Path(sys.argv[1]).write_text(json.dumps(report,indent=2))
    print(json.dumps(report['summary'],indent=2))
if __name__=='__main__':main()
