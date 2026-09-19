"""Generic array containers. No dataset-specific conventions or preprocessing."""
from contextlib import contextmanager, ExitStack
from pathlib import Path
from . import Array, viewer
from .sampling import budget_bytes


def choose(names, options):
    key = options.get('dataset')
    if key is None and len(names) == 1:
        return names[0]
    if key not in names:
        raise ValueError('Specify dataset in reader options. Available arrays: ' + ', '.join(names))
    return key


@contextmanager
def open_source(path, options):
    import numpy as np
    with ExitStack() as stack:
        suffix = path.suffix.lower()
        title = options.get('title', path.name)
        if suffix == '.npy':
            data = np.load(path, mmap_mode='r', allow_pickle=False)
        elif suffix == '.npz':
            archive = stack.enter_context(np.load(path, allow_pickle=False))
            key = choose(archive.files, options)
            if archive.zip.getinfo(key + '.npy').file_size > budget_bytes(options):
                raise ValueError('Compressed NPZ cannot be randomly sampled; member exceeds max_read_mib. Convert to NPY/Zarr or explicitly raise the budget.')
            data = archive[key]
            title += ' / ' + key
        elif suffix in ('.h5', '.hdf5'):
            import h5py
            f = stack.enter_context(h5py.File(path, 'r'))
            names = []
            f.visititems(lambda k,v: names.append(k) if isinstance(v,h5py.Dataset) and v.ndim in (1,2,3) else None)
            key = choose(names, options)
            data = f[key]
            title += ' / ' + key
        elif suffix == '.zarr':
            import zarr
            group = zarr.open(str(path), mode='r')
            if hasattr(group, 'shape'):
                data = group
            else:
                key = options.get('dataset') or choose(list(group.array_keys()), options)
                data = group[key]
                title += ' / ' + key
        else:
            raise ValueError('No built-in array reader for this file. Add a custom reader in .datapeek/*.py or ~/.datapeek/readers/*.py.')
        yield data, options, title, options.get('time_axis', 1), options.get('dt')


@contextmanager
def open_array(path, options, renderer_id=None, workspace_root=None, reader_paths=None):
    """Resolve a reader and manage resources for both quick and detailed views."""
    from runner import discover
    if renderer_id is None:
        renderer_id = 'builtin:npy' if Path(path).suffix.lower()=='.npy' else 'builtin:scientific'
    diagnostics = discover(workspace_root, renderer_id, reader_paths)
    renderer = viewer.renderers.get(renderer_id)
    if renderer is None or renderer.kind != 'array':
        raise ValueError(f'Array reader unavailable: {renderer_id}. {diagnostics}')
    with ExitStack() as stack:
        result = renderer.render(Path(path), options)
        if hasattr(result, '__enter__') and hasattr(result, '__exit__'):
            result = stack.enter_context(result)
        source = result if isinstance(result, Array) else Array(result)
        data = source.data
        import numpy as np
        if not hasattr(data, 'shape') or not hasattr(data, 'dtype'):
            raise ValueError('A reader must return an array with shape, dtype and slicing, or Array(data, options, title)')
        if len(data.shape) not in (1,2,3) or min(data.shape)<1 or np.dtype(data.dtype).kind not in 'biuf':
            raise ValueError(f'Expected a nonempty real 1D/2D/3D array; got {data.shape}, {data.dtype}')
        resolved = {'cmap':'gray', **source.options, **options}
        if resolved.get('demean'):
            raise ValueError('Implicit demean is no longer supported. Put preprocessing with a fixed reference in your custom reader, or remove demean to view raw values.')
        time_axis = resolved.get('time_axis', 1)
        dt = resolved.get('dt')
        if isinstance(time_axis,bool) or time_axis not in (0,1):
            raise ValueError('time_axis must be 0 or 1')
        if dt is not None and (isinstance(dt,bool) or not isinstance(dt,(int,float)) or not np.isfinite(dt) or dt<=0):
            raise ValueError('dt must be a positive finite number')
        yield data, resolved, resolved.get('title',source.title or Path(path).name), time_axis, dt
