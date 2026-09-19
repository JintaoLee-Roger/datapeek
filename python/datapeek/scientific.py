"""Read-only DAS and seismic previews. Slice volumes before materializing data."""
import math
import time
from contextlib import contextmanager

from . import viewer
from .colors import color_limits, matplotlib_cmap
from .sampling import budget_bytes, read_sample


def integer(options, name, default, size):
    value = options.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < size:
        raise ValueError(f"{name} must be an integer in [0, {size - 1}]")
    return value


def prepare_panels(data, options, *, volume=False, time_axis=1, dt=None):
    import numpy as np
    shape = tuple(data.shape)
    if len(shape) != (3 if volume else 2) or min(shape) < 1 or np.dtype(data.dtype).kind not in 'biuf':
        raise ValueError(f'Expected nonempty real {3 if volume else 2}D data; got {shape}, {data.dtype}')
    limit = options.get('max_pixels', 512)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 16 <= limit <= 2048:
        raise ValueError('max_pixels must be an integer from 16 to 2048')
    steps = [max(1, (n + limit - 1) // limit) for n in shape]
    slices = [slice(None, None, s) for s in steps]
    budget = budget_bytes(options)
    read_seconds = 0.0
    read_bytes = 0
    if volume:
        threshold = options.get('large_volume_gb', 1.5)
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or threshold <= 0:
            raise ValueError('large_volume_gb must be positive')
        size = math.prod(shape) * np.dtype(data.dtype).itemsize
        selected = options.get('slices', ['iline'] if size > threshold * 1_000_000_000 else ['iline', 'xline', 'time'])
        if not isinstance(selected, list) or not selected or any(x not in ('iline', 'xline', 'time') for x in selected) or len(set(selected)) != len(selected):
            raise ValueError('slices must be a nonempty list of distinct iline, xline, time names')
        positions = [integer(options, key, n // 2, n) if key in selected else None for key, n in zip(('iline', 'xline', 'time'), shape)]
        panels = []
        for label in selected:
            axis = ('iline', 'xline', 'time').index(label)
            key = [slice(None)] * 3
            key[axis] = positions[axis]
            read = data.read_region if hasattr(data, 'read_region') else data.__getitem__
            started = time.perf_counter()
            full = np.array(read(tuple(key)), copy=True)
            seconds = time.perf_counter() - started
            read_seconds += seconds
            read_bytes += full.nbytes
            print(f'DataPeek full slice {label}: {seconds:.4f}s; shape={full.shape}; output={full.nbytes / 1024**2:.2f} MiB', flush=True)
            # Read every value in the slice, then reduce only the plotting buffer.
            display_steps = tuple(slice(None, None, max(1, (n + limit - 1) // limit)) for n in full.shape)
            values = full[display_steps].copy()
            del full
            remaining = [i for i in range(3) if i != axis]
            # Vertical sections: time down; horizontal section: iline down.
            if axis < 2:
                values = values.T
                xdim, ydim = remaining
            else:
                ydim, xdim = remaining
            panels.append((values, f'{label} = {positions[axis]} ({values.shape[0]}×{values.shape[1]} pixels)', ('iline', 'xline', 'time')[xdim], ('iline', 'xline', 'time')[ydim], shape[xdim]-1, shape[ydim]-1))
    else:
        values, read_seconds, read_bytes = read_sample(data, slices, budget, 'DAS')
        if time_axis == 0:
            values = values.T
        nt, nc = shape[time_axis], shape[1-time_axis]
        das = options.get('kind') == 'das'
        panels = [(values, 'DAS' if das else 'Array', ('Time (s)' if dt else 'Time index') if das else options.get('xlabel','Column index'), 'Channel index' if das else options.get('ylabel','Row index'), (nt-1) * dt if dt else nt-1, nc-1)]
    return panels, read_seconds, read_bytes


def draw(data, options, title, *, volume=False, time_axis=1, dt=None):
    import numpy as np
    from matplotlib.figure import Figure
    shape = tuple(data.shape)
    panels, read_seconds, read_bytes = prepare_panels(data, options, volume=volume, time_axis=time_axis, dt=dt)
    percentile = float(options.get('clip_percentile', 99))
    finite = np.concatenate([a[np.isfinite(a)].astype(float) for a, *_ in panels])
    vmin, vmax = color_limits(finite, options)
    fig = Figure(figsize=(6 * len(panels) + 2, 6) if volume else (12, 7), layout='constrained')
    axes = fig.subplots(1, len(panels), squeeze=False)[0]
    for ax, (values, name, xlabel, ylabel, width, height) in zip(axes, panels):
        im = ax.imshow(np.ma.masked_invalid(values), cmap=matplotlib_cmap(options.get('cmap', 'gray' if volume else 'seismic')), aspect='auto', origin='upper', extent=(0, width, height, 0), vmin=vmin, vmax=vmax, interpolation='nearest')
        ax.set(title=name, xlabel=xlabel, ylabel=ylabel)
    fig.colorbar(im, ax=list(axes), shrink=.8, label='Amplitude')
    read_kind = 'full slices' if volume else 'estimated read/decode'
    fig.suptitle(f'{title}\nshape={shape}, dtype={data.dtype}; sampled preview; clip={percentile:g}%\nread={read_seconds:.3f}s; {read_kind}={read_bytes / 1024**2:.1f} MiB')
    return fig


from .sources import open_source


@viewer.reader(name='Array container (NPZ / HDF5 / Zarr)', extensions=['.npz', '.h5', '.hdf5', '.zarr'], id='scientific')
@contextmanager
def read_container(path, options):
    from . import Array
    with open_source(path, options) as (data, resolved, title, _, __):
        yield Array(data, resolved, title)


def render_scientific(path, options):
    with open_source(path, options) as (data, resolved, title, time_axis, dt):
        return draw_array(data, resolved, title, time_axis=time_axis, dt=dt)


def draw_array(data, options, title, time_axis=1, dt=None):
    if len(data.shape) != 1:
        return draw(data, options, title, volume=len(data.shape)==3, time_axis=time_axis, dt=dt)
    import numpy as np
    from matplotlib.figure import Figure
    limit = 20000
    step = max(1, math.ceil(data.shape[0]/limit))
    key = (slice(None,None,step),)
    read = data.read_region if hasattr(data,'read_region') else data.__getitem__
    values = np.asarray(read(key))
    fig = Figure(figsize=(10,6), layout='constrained')
    ax=fig.subplots()
    ax.plot(np.arange(len(values))*step, values, linewidth=.9)
    ax.set(title=title, xlabel='Sample index', ylabel='Value')
    return fig
