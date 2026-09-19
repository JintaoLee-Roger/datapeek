"""Personal DAS/seismic conventions. Copy into ~/.datapeek/readers/ to enable.

Not imported by the plugin unless explicitly installed as a user reader.
"""
import json
import re
from contextlib import ExitStack, contextmanager
from datapeek import viewer, Array
from datapeek.sampling import budget_bytes, EventView
from datapeek.scientific import integer

@viewer.reader(name='DAS / seismic examples',
               extensions=['.npz', '.h5', '.hdf5', '.zarr', '.szarr', '.slmdb', '.snpy', '.dat', '.0'],
               patterns=['*/das/*', '*/seismic/*', '*_h*x*x*.dat', '*.slmdb', '*.szarr', '*.snpy'],
               exclude=['*/das/part_*.zarr', '*/das/*/part_*.zarr'], id='geoscience', cache=True)
@contextmanager
def read_geoscience(path, options):
    import numpy as np
    if path.is_dir() and re.search(r'/das/(?:.*/)?part_[^/]+\.zarr/?$', path.as_posix(), re.I):
        raise ValueError('Expand data and preview an individual DAS event chunk, such as 0.0.0 or 1.0.0')
    with ExitStack() as stack:
        suffix = path.suffix.lower()
        title = options.get('title', path.name)
        time_axis = options.get('time_axis', 1)
        dt = options.get('dt')
        if time_axis not in (0, 1):
            raise ValueError('time_axis must be 0 or 1')
        if dt is not None and (not np.isfinite(dt) or dt <= 0):
            raise ValueError('dt must be a positive finite number')
        if suffix == '.npy':
            data = np.load(path, mmap_mode='r', allow_pickle=False)
        elif suffix == '.npz':
            archive = stack.enter_context(np.load(path, allow_pickle=False))
            key = options.get('dataset') or ('clean_strain_rate' if 'clean_strain_rate' in archive.files else 'data')
            if key not in archive.files:
                raise ValueError(f'Set dataset to one of {archive.files}')
            entry = archive.zip.getinfo(key + '.npy')
            if entry.file_size > budget_bytes(options):
                raise ValueError(f'NPZ member {key} expands to {entry.file_size / 1024**2:.1f} MiB, exceeding max_read_mib. Compressed NPZ cannot be randomly sampled; convert to NPY/Zarr or explicitly raise the budget.')
            import time
            started = time.perf_counter()
            data = archive[key]
            print(f'DataPeek NPZ decode: {time.perf_counter() - started:.4f}s; {data.nbytes / 1024**2:.2f} MiB', flush=True)
            if 'metadata_json' in archive.files and archive.zip.getinfo('metadata_json.npy').file_size > 1024**2:
                raise ValueError('metadata_json exceeds 1 MiB')
            meta = json.loads(str(archive['metadata_json'])) if 'metadata_json' in archive.files else {}
            if 'bbox_local' in archive.files and 't0' in archive.files:
                time_axis = options.get('time_axis', 0)
            if dt is None:
                dt = meta.get('acquisition', {}).get('dt_s')
                if not dt and meta.get('target_fs_hz'):
                    dt = 1 / meta['target_fs_hz']
            title += f' / {key}'
        elif suffix in ('.h5', '.hdf5'):
            import h5py
            f = stack.enter_context(h5py.File(path, 'r'))
            key = options.get('dataset', 'Acquisition/Raw[0]/RawData')
            if key not in f:
                keys = []
                f.visititems(lambda k, v: keys.append(k) if isinstance(v, h5py.Dataset) and v.ndim == 2 else None)
                raise ValueError(f'Set dataset to a 2D dataset: {keys}')
            data = f[key]
            # Raw data: no implicit mean removal or other preprocessing.
            rate = data.parent.attrs.get('OutputDataRate')
            if dt is None and rate:
                dt = 1 / float(rate)
            title += f' / {key}'
        elif suffix in ('.szarr', '.slmdb', '.snpy'):
            import seisvol
            data = seisvol.open_volume(path, mode='r', layer=options.get('dataset'))
            if callable(getattr(data, 'close', None)):
                stack.callback(data.close)
        elif suffix == '.dat':
            match = re.search(r'_h(\d+)x(\d+)x(\d+)\.dat$', path.name, re.I)
            if not match:
                raise ValueError('DAT filename must end in _h(nt)x(nx)x(ni).dat')
            nt, nx, ni = map(int, match.groups())
            dtype = np.dtype(options.get('dtype', '<f4'))
            if dtype.kind not in 'biuf' or path.stat().st_size != ni * nx * nt * dtype.itemsize:
                raise ValueError('DAT byte size does not match filename dimensions and dtype (default little-endian float32)')
            data = np.memmap(path, mode='r', dtype=dtype, shape=(ni, nx, nt))
        else:
            import zarr
            chunk = re.fullmatch(r'(\d+)\.0\.0', path.name)
            root = path.parent.parent if chunk else path
            group = zarr.open(str(root), mode='r')
            if hasattr(group, 'shape'):
                data = group
            else:
                keys = list(group.array_keys())
                key = options.get('dataset') or ('data' if 'data' in keys else 'imp' if 'imp' in keys else keys[0] if len(keys) == 1 else None)
                if key is None:
                    raise ValueError(f'Set dataset to one of {keys}')
                data = group[key]
                title += f' / {key}'
            if chunk or group.attrs.get('dims') == 'event_channel_time':
                if chunk and (path.parent.name != 'data' or tuple(data.chunks) != (1, data.shape[1], data.shape[2])):
                    raise ValueError('Chunk preview requires an event/channel/time store with one full event per chunk')
                event = integer({} if chunk else options, 'event', int(chunk[1]) if chunk else 0, data.shape[0])
                nt = int(group['valid_nt'][event]) if 'valid_nt' in group else data.shape[2]
                if not 0 < nt <= data.shape[2]:
                    raise ValueError("Invalid valid_nt")
                data = EventView(data, event, nt)
                dt = dt or (1 / float(group.attrs['fs']) if 'fs' in group.attrs else None)
                title += f' / event={event}'
        yield Array(data, {**options, 'kind': 'das' if len(data.shape)==2 else 'volume', 'cmap': 'seismic' if len(data.shape)==2 else 'gray', 'time_axis': time_axis, 'dt': dt}, title)

