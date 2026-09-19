"""Consistent automatic color limits for static, detailed and 3D viewers."""
import math


def color_limits(values, options):
    import numpy as np
    if options.get('vmin') is not None or options.get('vmax') is not None:
        low, high = options.get('vmin'), options.get('vmax')
        if any(isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x) for x in (low, high)) or low >= high:
            raise ValueError('Manual color limits require finite vmin < vmax')
        return float(low), float(high)
    percentile = float(options.get('clip_percentile', 99))
    if not 0 < percentile <= 100:
        raise ValueError('clip_percentile must be in (0, 100]')
    finite = np.asarray(values).ravel()
    finite = finite[np.isfinite(finite)]
    if not finite.size:
        return -1.0, 1.0
    tail = (100 - percentile) / 2
    low, q25, median, q75, high = np.percentile(finite, [tail, 25, 50, 75, 100-tail])
    low, high = float(low), float(high)
    # Detect zero-centered signals robustly, without using raw extrema.
    # The IQR keeps isolated outliers from making shifted data look centered.
    centered = low < 0 < high and abs(median) <= 0.1 * (q75 - q25)
    if centered:
        amplitude = min(abs(low), abs(high))
        return -amplitude, amplitude
    if low == high:
        # Constant fields need a usable interval centered on their own value.
        padding = max(abs(low) * 1e-6, np.finfo(float).eps)
        return low - padding, high + padding
    return low, high


def matplotlib_cmap(name):
    """Resolve cigvis names without registering global matplotlib colormaps."""
    if name == 'Petrel':
        from cigvis.colormap import get_cmap_from_str
        return get_cmap_from_str(name)
    return name


def petrel_colorscale():
    """Export cigvis's actual LUT for Plotly, matching the 3D palette."""
    import numpy as np
    cmap = matplotlib_cmap('Petrel')
    return [[float(x), 'rgb(%s)' % ','.join(str(float(c)*255) for c in rgba[:3])]
            for x, rgba in zip(np.linspace(0, 1, cmap.N), cmap(np.linspace(0, 1, cmap.N)))]
