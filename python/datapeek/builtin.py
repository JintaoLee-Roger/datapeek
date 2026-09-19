"""NumPy preview: all sampling and scientific rendering stays in Python."""
from . import viewer
from .colors import matplotlib_cmap, petrel_colorscale


def render_npy(path, options):
    import numpy as np

    data = np.load(path, mmap_mode="r", allow_pickle=False)
    if data.ndim == 3:
        from .scientific import draw
        return draw(data, options, options.get("title", path.name), volume=True)
    if data.ndim not in (1, 2) or not data.size or data.dtype.kind not in "biuf":
        raise ValueError(f"Supported: nonempty 1D/2D real numeric arrays; got {data.shape}, {data.dtype}")
    backend = options.get("backend", "matplotlib")
    if backend not in ("matplotlib", "plotly"):
        raise ValueError("backend must be matplotlib or plotly")
    limit = 20000 if data.ndim == 1 else (512 if backend == "plotly" else 1024)
    indices = [np.linspace(0, size - 1, min(size, limit), dtype=int) for size in data.shape]
    sampled = data[indices[0]] if data.ndim == 1 else data[np.ix_(*indices)]
    sampled = np.ma.masked_invalid(sampled)
    title = options.get("title", path.name)
    note = f"shape={data.shape}, dtype={data.dtype}"
    if sampled.shape != data.shape:
        note += f" — sampled preview {sampled.shape} (may omit narrow features)"
    title = f"{title}\n{note}"

    if data.ndim == 2:
        from .colors import color_limits
        vmin, vmax = color_limits(sampled.compressed(), options)

    if backend == "plotly":
        import plotly.graph_objects as go
        values = sampled.astype(float).filled(float("nan"))
        if data.ndim == 1:
            # SVG works in Webviews where GPU/WebGL is disabled.
            fig = go.Figure(go.Scatter(x=indices[0], y=values, mode="lines"))
        else:
            fig = go.Figure(go.Heatmap(zmin=vmin, zmax=vmax, z=values, x=indices[1], y=indices[0], colorscale=petrel_colorscale() if options.get("cmap") == "Petrel" or options.get("colorscale") == "Petrel" else options.get("colorscale", "Viridis")))
        fig.update_layout(title=title.replace("\n", "<br>"), xaxis_title="Sample index" if data.ndim == 1 else "Column index", yaxis_title="Value" if data.ndim == 1 else "Row index", autosize=True)
        return fig

    from matplotlib.figure import Figure
    fig = Figure(figsize=(10, 6), layout="constrained")
    ax = fig.subplots()
    if data.ndim == 1:
        ax.plot(indices[0], sampled, linewidth=0.9)
        ax.set(xlabel="Sample index", ylabel="Value")
        ax.grid(alpha=0.2)
    else:
        im = ax.imshow(sampled, vmin=vmin, vmax=vmax, aspect="auto", origin="upper", cmap=matplotlib_cmap(options.get("cmap", "viridis")), extent=(0, data.shape[1]-1, data.shape[0]-1, 0))
        fig.colorbar(im, ax=ax)
        ax.set(xlabel="Column index", ylabel="Row index")
    ax.set_title(title, fontsize=10)
    return fig


@viewer.reader(name='NumPy array', extensions=['.npy'], id='npy')
def read_npy(path, options):
    import numpy as np
    return np.load(path, mmap_mode='r', allow_pickle=False)
