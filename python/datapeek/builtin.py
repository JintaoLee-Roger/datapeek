"""NumPy preview: all sampling and scientific rendering stays in Python."""
from . import viewer


@viewer.register(name="NumPy array", extensions=[".npy"], id="npy")
def render_npy(path, options):
    import numpy as np

    data = np.load(path, mmap_mode="r", allow_pickle=False)
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

    if backend == "plotly":
        import plotly.graph_objects as go
        values = sampled.astype(float).filled(float("nan"))
        if data.ndim == 1:
            # SVG works in Webviews where GPU/WebGL is disabled.
            fig = go.Figure(go.Scatter(x=indices[0], y=values, mode="lines"))
        else:
            fig = go.Figure(go.Heatmap(z=values, x=indices[1], y=indices[0], colorscale=options.get("colorscale", "Viridis")))
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
        im = ax.imshow(sampled, aspect="auto", origin="lower", cmap=options.get("cmap", "viridis"), extent=(-0.5, data.shape[1]-0.5, -0.5, data.shape[0]-0.5))
        fig.colorbar(im, ax=ax)
        ax.set(xlabel="Column index", ylabel="Row index")
    ax.set_title(title, fontsize=10)
    return fig
