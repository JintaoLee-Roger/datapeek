"""Opt-in smoke test: python tests/smoke_real_data.py [output_directory]."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ('zhoushan', 'das/Zhoushan_events/16/event/16-annotations_pos_000005.npz'),
    ('ridgecrest', 'das/earthquake/Ridgecrest/part_00.zarr/data/99.0.0'),
    ('whale', 'das/earthquake/North-C1-LR-P1kHz-GL50m-Sp24m-FS200Hz-ReceiveFiber_2021-11-05T07_31_00-0700/North-C1-LR-P1kHz-GL50m-Sp24m-FS200Hz-ReceiveFiber_2021-11-05T165911Z.h5'),
    ('marmousi', 'das/forge/marmousi_multiregion_600_v3_fmm_721/event_000149.npz'),
    ('forge', 'das/forge/real_event_npz/2022/event/forge2022_event_00266.npz'),
    ('volume_zarr', 'seismic/rgt_fault_imp_512v3/zarr/00376.zarr'),
    ('baiyun', 'seismic/seismic_data/baiyun/sx_cut.npy'),
    ('channels', 'seismic/seismic_data/channels/channels_origin_h651x601x401.dat'),
    ('fans', 'seismic/seismic_data/selected/hz_fans-v2.slmdb'),
]

if __name__ == '__main__':
    output = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix='datapeek-real-')).resolve()
    for name, relative in CASES:
        folder = output / name
        folder.mkdir(parents=True, exist_ok=True)
        request = dict(protocolVersion=1, requestId=name, operation='render', targetPath=str(Path('/home/jtli/data') / relative), rendererId='builtin:npy' if relative.endswith('.npy') else 'personal:geoscience.py:geoscience', readerPaths=[str(ROOT/'examples/readers')], options={})
        (folder / 'request.json').write_text(json.dumps(request))
        subprocess.run([sys.executable, str(ROOT / 'python/runner.py'), '--request', str(folder / 'request.json')], check=True, timeout=120)
        response = json.loads((folder / 'response.json').read_text())
        if response['status'] != 'ok':
            raise RuntimeError(f'{name}: {response}')
        print(name, folder / response['artifact']['entry'], flush=True)
