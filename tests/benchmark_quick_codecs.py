"""Compare transport codecs on existing quick-preview artifacts (no source I/O).
Usage: python tests/benchmark_quick_codecs.py /tmp/datapeek-canvas-final output.json
PNG candidates encode sampled indices only, not the legacy Matplotlib figure.
"""
import base64
import io
import json
from pathlib import Path
import re
import statistics
import sys
import time
import zlib
import numpy as np
from PIL import Image

rows=[]
for path in sorted(Path(sys.argv[1]).glob('*/artifacts/quick.html')):
    data=json.loads(re.search(r'const data=(.*);',path.read_text()).group(1))
    arrays=[]
    for p in data['panels']:
        b=base64.b64decode(p['pixels'])
        if p.get('compressed'):b=zlib.decompress(b)
        arrays.append(np.frombuffer(b,dtype='uint8').reshape(p['rows'],p['cols']))
    for codec in ('raw','deflate1','png1','png6'):
        times=[]
        for _ in range(10):
            start=time.perf_counter();outputs=[]
            for a in arrays:
                if codec=='raw':outputs.append(a.tobytes())
                elif codec=='deflate1':outputs.append(zlib.compress(a.tobytes(),1))
                else:
                    out=io.BytesIO();Image.fromarray(a).save(out,format='PNG',compress_level=int(codec[-1]));outputs.append(out.getvalue())
            times.append(time.perf_counter()-start)
        rows.append(dict(case=path.parents[1].name,codec=codec,bytes=sum(map(len,outputs)),medianSeconds=statistics.median(times)))
Path(sys.argv[2]).write_text(json.dumps(rows,indent=2))
print(json.dumps(rows,indent=2))
