"""Per-panel JSON-lines worker. Protocol on stdout; library logs on stderr."""
import argparse
import json
import os
from pathlib import Path
import sys
import traceback

os.environ['MPLBACKEND']='Agg'
protocol = sys.stdout
sys.stdout = sys.stderr


def main():
    from datapeek.detail import DetailSession
    parser=argparse.ArgumentParser()
    parser.add_argument('--request',required=True)
    args=parser.parse_args()
    request=json.loads(Path(args.request).read_text())
    session=None
    try:
        session=DetailSession(request['targetPath'],request.get('options',{}),renderer_id=request.get('rendererId'),workspace_root=request.get('workspaceRoot'),reader_paths=request.get('readerPaths'))
        # The JS runtime is produced by the selected Python Plotly installation.
        from plotly.offline import get_plotlyjs
        Path(request['assetDirectory'],'plotly.min.js').write_text(get_plotlyjs())
        protocol.write(json.dumps({'id':0,'result':session.info()})+'\n');protocol.flush()
        for line in sys.stdin:
            message=json.loads(line)
            try:
                action=message['action']
                if action=='sample':
                    result=session.sample(message.get('options',{}))
                elif action=='viser':
                    result=session.start_viser(message.get('options',{}))
                elif action=='stopViser':
                    if session.server:
                        session.server.stop();session.server=None
                    result={}
                else:
                    raise ValueError('Unknown detail action')
                protocol.write(json.dumps({'id':message['id'],'result':result},allow_nan=False)+'\n')
            except Exception as exc:
                traceback.print_exc()
                protocol.write(json.dumps({'id':message['id'],'error':str(exc)})+'\n')
            protocol.flush()
    except Exception as exc:
        traceback.print_exc()
        protocol.write(json.dumps({'id':0,'error':str(exc)})+'\n');protocol.flush()
    finally:
        if session:session.close()


if __name__=='__main__':main()
