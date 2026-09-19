"""Opt-in real-data detailed-reader and browser-server smoke checks."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from smoke_real_data import CASES, ROOT

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='datapeek-detail-check-') as temp:
        for name,relative in CASES:
            folder=Path(temp)/name;folder.mkdir()
            request={'targetPath':'/home/jtli/data/'+relative,'options':{},'rendererId':'builtin:npy' if relative.endswith('.npy') else 'personal:geoscience.py:geoscience','readerPaths':[str(ROOT/'examples/readers')],'assetDirectory':str(folder)}
            p=folder/'request.json';p.write_text(json.dumps(request))
            messages='\n'.join(json.dumps({'id':i,'action':'sample','options':opts}) for i,opts in enumerate([{}, {'xrange':[0,.2] if name in ('marmousi','forge','ridgecrest','whale') else [10,30],'yrange':[20,40]}],1))+'\n'
            result=subprocess.run([sys.executable,str(ROOT/'python/detail_worker.py'),'--request',str(p)],input=messages,capture_output=True,text=True,timeout=120)
            lines=[json.loads(line) for line in result.stdout.splitlines()]
            assert len(lines)==3 and all('error' not in line for line in lines),(name,result.stdout[:1000],result.stderr[-1500:])
            print(name,lines[0]['result']['shape'],'ROI',lines[2]['result']['shape'],flush=True)
