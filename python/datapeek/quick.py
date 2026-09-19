"""Static Canvas preview: no figure renderer, PNG encoder or plotting JS runtime."""
import base64
import json
import zlib
from pathlib import Path

from .colors import color_limits, matplotlib_cmap
from .scientific import prepare_panels


def encode(data):
    return base64.b64encode(data).decode('ascii')


def payload(data, options, title, time_axis=1, dt=None):
    import numpy as np
    result = dict(title=title, shape=list(data.shape), dtype=str(data.dtype), panels=[])
    if len(data.shape) == 1:
        step = max(1, (data.shape[0] + 19999) // 20000)
        read = data.read_region if hasattr(data, 'read_region') else data.__getitem__
        values = np.asarray(read((slice(None, None, step),)), dtype='<f8')
        finite = values[np.isfinite(values)]
        low, high = (float(finite.min()), float(finite.max())) if finite.size else (-1., 1.)
        if low == high:
            padding = max(abs(low)*1e-6, np.finfo(float).eps)
            low, high = low-padding, high+padding
        result.update(line=encode(values.tobytes()), step=step, limits=[low,high])
        return result
    panels, seconds, size = prepare_panels(data, options, volume=len(data.shape)==3, time_axis=time_axis, dt=dt)
    low, high = color_limits(np.concatenate([a.ravel() for a,*_ in panels]), options)
    name = options.get('cmap', 'gray' if len(data.shape)==3 else 'seismic')
    palettes = json.loads(Path(__file__).with_name('quick_luts.json').read_text())
    if name in palettes:
        lut = np.asarray(palettes[name], dtype=np.uint8)
    else:
        import matplotlib
        cmap = matplotlib_cmap(name)
        if isinstance(cmap,str):
            cmap = matplotlib.colormaps[cmap]
        lut = cmap(np.linspace(0,1,256), bytes=True)
    result.update(limits=[low,high], lut=encode(lut.tobytes()), readSeconds=seconds, readBytes=size, cmap=name)
    for values, label, xlabel, ylabel, width, height in panels:
        # One byte per displayed sample. NaNs are transparent, infinities match masked_invalid.
        valid = np.isfinite(values)
        scaled = (values.astype(float)-low)/(high-low)
        indices = np.minimum(np.clip(np.nan_to_num(scaled),0,1)*256,255).astype(np.uint8)
        raw = indices.tobytes()
        packed = zlib.compress(raw, level=1)
        compressed = len(raw) - len(packed) > max(8192, len(raw)*.1)
        result['panels'].append(dict(label=label, xlabel=xlabel, ylabel=ylabel, width=width, height=height,
            rows=values.shape[0], cols=values.shape[1], pixels=encode(packed if compressed else raw), compressed=compressed,
            mask=None if valid.all() else encode(valid.astype(np.uint8).tobytes())))
    return result


def render(data, options, title, directory, time_axis=1, dt=None):
    values = payload(data, options, title, time_axis, dt)
    template = Path(__file__).with_name('quick.html').read_text()
    # No data or reader-provided text is interpreted as HTML or JavaScript.
    encoded = json.dumps(values, ensure_ascii=True, allow_nan=False).replace('<', r'\u003c').replace('>', r'\u003e').replace('&', r'\u0026')
    (directory/'quick.html').write_text(template.replace('__QUICK_PAYLOAD__', encoded), encoding='utf-8')
    return dict(kind='html', entry='quick.html', mimeType='text/html', files=['quick.html'])
