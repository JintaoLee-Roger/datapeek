from datapeek import viewer


@viewer.register(name="Text signal", extensions=[".txt", ".csv"])
def render(path, options):
    import numpy as np
    from matplotlib.figure import Figure

    data = np.loadtxt(path, delimiter=options.get("delimiter", "," if path.suffix == ".csv" else None))
    fig = Figure(figsize=(10, 5), layout="constrained")
    fig.subplots().plot(data[:20000])
    return fig
