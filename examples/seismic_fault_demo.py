"""DataPeek custom Figure example: imp -> reflectivity -> seismic + fault.

Installation
------------
1. From the repository root, copy this file to your personal reader directory:
       mkdir -p ~/.datapeek/readers
       cp examples/seismic_fault_demo.py ~/.datapeek/readers/
   Alternatively, put it in .datapeek/ at the VS Code workspace root for
   project-only use. No extension changes or data-folder settings are needed.
2. Right-click 00000.npz or the 00000.zarr directory -> Preview with DataPeek.
   Select "Demo: synthetic seismic + fault". If another reader was remembered,
   use "Choose Reader". Reopen the preview after editing the script.
3. Edit DEFAULTS below to choose an axis, slice, and wavelet; index=None selects
   the middle slice. You may also override options in datapeek.rendererOptions:
   Personal ID: personal:seismic_fault_demo.py:seismic_fault
   Workspace ID: workspace:seismic_fault_demo.py:seismic_fault

Requires numpy and matplotlib, plus zarr for Zarr input. The extension supplies
`datapeek` when loading this script; do not pip install datapeek.
This @viewer.register example returns its own Figure, including the overlay.
It does not expose array-reader Detailed View/3D controls, modify source data,
or install itself. Chinese instructions are in ../README.zh-CN.md.

Data and processing conventions
-------------------------------
* imp and fault have axes (iline, xline, time), in an NPZ archive or Zarr group.
* Default r[t] = (imp[t+1]-imp[t]) / (imp[t+1]+imp[t]); the last sample is zero.
  Use reflectivity='difference' for an unnormalized first difference instead.
* Convolve along the last axis with a zero-phase Ricker wavelet, using zero
  padding at the boundaries and retaining the original trace length.
* dt=0.002 seconds and frequency=25 Hz are example assumptions, not metadata.
* Values above fault_threshold are overlaid in red; zero is transparent.
  Fault IDs mark locations only and do not affect the synthetic amplitudes.
* Read one complete iline/xline section and process all its time traces.
  Zarr supports partial decoding. NPZ must sequentially decompress preceding
  data, but this reader never retains the whole volume. Prefer Zarr for speed.
  The NPZ example supports only real numeric arrays stored in C order.
"""
from pathlib import Path
import zipfile

from datapeek import viewer


DEFAULTS = {
    'axis': 'iline',           # 'iline' or 'xline'; time is always the last axis
    'index': None,             # None = middle slice; e.g. 120
    'dt': 0.002,               # Seconds; replace with the actual sampling interval
    'frequency': 25.0,         # Ricker peak frequency, Hz
    'duration': 0.128,         # Wavelet duration in seconds (rounded to an odd sample count)
    'reflectivity': 'normalized',  # Or 'difference'
    'clip_percentile': 99.0,   # Central percentile range; centered signals use min(abs(vmin), abs(vmax))
    'fault_threshold': 0.0,
    'fault_alpha': 0.55,
    'show_steps': False,       # True: also show impedance and reflectivity panels
}


def _header(stream):
    import numpy as np
    version = np.lib.format.read_magic(stream)
    if version not in ((1, 0), (2, 0)):
        raise ValueError(f'This example supports NPY header v1/v2; got {version}')
    read = np.lib.format.read_array_header_1_0 if version == (1, 0) else np.lib.format.read_array_header_2_0
    shape, fortran, dtype = read(stream)
    if len(shape) != 3 or min(shape) < 2 or fortran or dtype.kind not in 'biuf':
        raise ValueError('NPZ members must be real 3D C-order arrays with each dimension >= 2')
    return shape, dtype


def _npz_section(archive, name, axis, index, shape):
    """Slice a compressed .npy member with bounded memory; seek still decompresses."""
    import numpy as np
    with archive.open(name + '.npy') as stream:
        actual, dtype = _header(stream)
        if actual != shape:
            raise ValueError('imp and fault must have the same shape')
        offset = stream.tell()
        ni, nx, nt = shape

        def read_at(sample_offset, count):
            stream.seek(offset + sample_offset * dtype.itemsize)
            raw = stream.read(count * dtype.itemsize)
            if len(raw) != count * dtype.itemsize:
                raise ValueError(f'Incomplete data in {name}')
            return np.frombuffer(raw, dtype=dtype)

        if axis == 'iline':
            return read_at(index * nx * nt, nx * nt).reshape(nx, nt).astype('float32')
        result = np.empty((ni, nt), dtype='float32')
        for i in range(ni):
            result[i] = read_at((i * nx + index) * nt, nt)
        return result


def read_sections(path, axis, index):
    import numpy as np

    def position(shape):
        if len(shape) != 3 or min(shape) < 2:
            raise ValueError('Expected a 3D (iline, xline, time) array with each dimension >= 2')
        size = shape[0 if axis == 'iline' else 1]
        value = size // 2 if index is None else index
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < size:
            raise ValueError(f'index must be between 0 and {size-1}')
        return value

    if axis not in ('iline', 'xline'):
        raise ValueError('This example supports only iline or xline to preserve complete time traces')
    path = Path(path)
    if path.suffix.lower() == '.npz':
        with zipfile.ZipFile(path) as archive:
            with archive.open('imp.npy') as stream:
                shape, _ = _header(stream)
            index = position(shape)
            imp, fault = [_npz_section(archive, name, axis, index, shape) for name in ('imp', 'fault')]
    elif path.suffix.lower() == '.zarr':
        import zarr
        group = zarr.open_group(str(path), mode='r')
        shape = group['imp'].shape
        if group['fault'].shape != shape:
            raise ValueError('imp and fault must have the same shape')
        index = position(shape)
        key = (index, slice(None), slice(None)) if axis == 'iline' else (slice(None), index, slice(None))
        imp, fault = [np.asarray(group[name][key], dtype='float32') for name in ('imp', 'fault')]
    else:
        raise ValueError('This example supports only .npz and .zarr')
    if not np.isfinite(imp).all() or not np.isfinite(fault).all():
        raise ValueError('imp / fault contains NaN or Inf; handle these explicitly before plotting')
    return imp, fault, index


def synthetic(imp, dt, frequency, duration, method):
    import numpy as np
    if not all(np.isfinite(x) and x > 0 for x in (dt, frequency, duration)) or frequency >= .5 / dt:
        raise ValueError('dt, frequency, and duration must be positive; frequency must be below Nyquist')
    half = max(1, round(duration / (2 * dt)))
    if 2 * half + 1 > imp.shape[-1]:
        raise ValueError('Wavelet exceeds the time axis; reduce duration')
    t = np.arange(-half, half + 1) * dt
    u = (np.pi * frequency * t)**2
    wavelet = ((1 - 2 * u) * np.exp(-u)).astype('float32')
    reflection = np.zeros_like(imp, dtype='float32')
    difference = np.diff(imp, axis=-1)
    if method == 'normalized':
        denominator = imp[..., 1:] + imp[..., :-1]
        np.divide(difference, denominator, out=reflection[..., :-1], where=np.abs(denominator) > np.finfo('float32').eps)
    elif method == 'difference':
        reflection[..., :-1] = difference
    else:
        raise ValueError('reflectivity must be normalized or difference')
    seismic = np.apply_along_axis(lambda trace: np.convolve(trace, wavelet, mode='same'), -1, reflection)
    return reflection, seismic


@viewer.register(
    name='Demo: synthetic seismic + fault',
    extensions=['.npz', '.zarr'],
    patterns=['*/rgt_fault_imp_512v3/dataset/*.npz', '*/rgt_fault_imp_512v3/zarr/*.zarr'],
    id='seismic_fault',
)
def render(path, options):
    import numpy as np
    from matplotlib.figure import Figure
    from matplotlib.colors import ListedColormap

    cfg = {**DEFAULTS, **options}
    percentile, alpha = float(cfg['clip_percentile']), float(cfg['fault_alpha'])
    threshold = float(cfg['fault_threshold'])
    if not 0 < percentile <= 100 or not 0 <= alpha <= 1 or not np.isfinite(threshold):
        raise ValueError('clip_percentile must be in (0,100], fault_alpha in [0,1], and threshold finite')
    imp, fault, index = read_sections(path, cfg['axis'], cfg['index'])
    reflection, seismic = synthetic(imp, float(cfg['dt']), float(cfg['frequency']), float(cfg['duration']), cfg['reflectivity'])
    stages = [(seismic, 'Seismic + fault', 'gray')]
    if cfg['show_steps']:
        stages = [(imp, 'Impedance', 'viridis'), (reflection, 'Reflectivity', 'gray'), *stages]
    fig = Figure(figsize=(6 * len(stages), 7), layout='constrained')
    axes = fig.subplots(1, len(stages), squeeze=False)[0]
    # Half-sample extent puts pixel centers exactly at trace index and t = sample * dt.
    extent = (-.5, imp.shape[0]-.5, (imp.shape[1]-.5)*cfg['dt'], -.5*cfg['dt'])
    for ax, (values, title, cmap) in zip(axes, stages):
        limits = {}
        if title != 'Impedance':
            tail = (100 - percentile) / 2
            low, q25, median, q75, high = np.percentile(values, [tail, 25, 50, 75, 100-tail])
            if low < 0 < high and abs(median) <= .1 * (q75 - q25):
                va = min(abs(low), abs(high))
                low, high = -va, va
            if low == high:
                padding = max(abs(low)*1e-6, np.finfo('float32').eps)
                low, high = low-padding, high+padding
            limits = dict(vmin=low, vmax=high)
        ax.imshow(values.T, cmap=cmap, extent=extent, aspect='auto', interpolation='nearest', **limits)
        ax.set(title=title, xlabel='xline' if cfg['axis']=='iline' else 'iline', ylabel='Time (s)')
    mask = np.ma.masked_where(fault.T <= threshold, np.ones_like(fault.T))
    axes[-1].imshow(mask, cmap=ListedColormap(['#ff3030']), vmin=0, vmax=1, alpha=alpha,
                    extent=extent, aspect='auto', interpolation='nearest')
    fig.suptitle(f'{Path(path).name} · {cfg["axis"]} = {index}')
    return fig
