"""Real worker / Viser lifecycle check, with an isolated small volume."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import urllib.request
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory() as temp:
    folder=Path(temp)
    data=folder/'volume.npy';np.save(data,np.arange(12*13*14,dtype='float32').reshape(12,13,14))
    request=folder/'request.json';request.write_text(json.dumps({'targetPath':str(data),'options':{},'assetDirectory':str(folder)}))
    proc=subprocess.Popen([sys.executable,str(ROOT/'python/detail_worker.py'),'--request',str(request)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    def call(action,options={}):
        proc.stdin.write(json.dumps({'id':1,'action':action,'options':options})+'\n');proc.stdin.flush()
        response=json.loads(proc.stdout.readline());assert 'error' not in response,response
        return response['result']
    try:
        assert 'result' in json.loads(proc.stdout.readline())
        port=call('viser',{'slices':['iline','xline','time']})['port']
        assert urllib.request.urlopen(f'http://127.0.0.1:{port}',timeout=10).status==200
        call('stopViser')
        with socket.socket() as sock:assert sock.connect_ex(('127.0.0.1',port))!=0
        port=call('viser',{'slices':['iline']})['port']
        proc.stdin.close();proc.wait(timeout=20)
        with socket.socket() as sock:assert sock.connect_ex(('127.0.0.1',port))!=0
        assert proc.returncode==0
        print('Worker lifecycle passed: start, HTTP, stop, restart, stdin close releases port.')
    finally:
        if proc.poll() is None:proc.kill();proc.wait()
