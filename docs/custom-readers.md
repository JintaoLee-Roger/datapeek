# Custom readers and configuration

English | [简体中文](custom-readers.zh-CN.md)

## Script locations and selection

Place scripts in `.datapeek/*.py` at the workspace root or `~/.datapeek/readers/*.py` for personal use. Set `datapeek.readerPaths` to use other personal directories. Install dependencies in DataPeek's selected Python environment; the extension provides the `datapeek` SDK.

A unique matching custom reader takes priority over built-in readers. Multiple matches prompt a choice, remembered after a successful preview. Use **Choose Reader** to change it. After editing a script, reopen the preview; close any existing Detailed View first.

Use `extensions` to match suffixes and optional `patterns`/`exclude` globs to narrow paths. Match your dataset layout rather than claiming unrelated files with the same suffix.

## Return an array

`@viewer.reader` shares Quick Preview, Detailed View, and volume 3D controls. Return an object with `shape`, `dtype`, and slicing. Use mmap or lazy sources for large data.

```python
from contextlib import contextmanager
from datapeek import viewer, Array

@viewer.reader(name="Project HDF5", extensions=[".h5"],
               patterns=["*/my_project/*"], id="h5")
@contextmanager
def read(path, options):
    import h5py
    with h5py.File(path, "r") as source:
        yield Array(source[options.get("dataset", "signal")],
                    {"kind": "das", "time_axis": 1, "dt": 0.005},
                    title=path.name)
```

`Array(data, options, title)` supplies display defaults and an optional title. A context manager keeps files open for the reader's lifetime. Ordinary 2D arrays need no `kind`; `xlabel` and `ylabel` customize their axes. Volumes must use `(iline, xline, time)`.

Preprocessing is owned by the script. Use a stable reference so a point has the same value in an overview and a region read. Avoid normalization based on each requested region.

## Return a Figure

Use `@viewer.register` when your script should draw the result, including overlays:

```python
from datapeek import viewer

@viewer.register(name="Text plot", extensions=[".txt"])
def render(path, options):
    import numpy as np
    from matplotlib.figure import Figure
    figure = Figure(figsize=(10, 5), layout="constrained")
    figure.subplots().plot(np.loadtxt(path))
    return figure
```

Return a Matplotlib Figure or a Python Plotly Figure. Figure renderers keep their own display behavior and do not receive shared array slice/3D controls. See the [seismic overlay example](real-data-debug.md#synthetic-seismic-with-fault-overlay).

## Reader options

[How to open Settings JSON and choose local/remote settings](getting-started.md#configure-a-reader). These options apply by reader ID, not by individual file.

Reader IDs appear in **Choose Reader**:

- `builtin:npy`: NPY arrays.
- `builtin:scientific`: NPZ, HDF5, and Zarr containers.
- `personal:<filename>:<function-or-explicit-id>`: personal script.
- `workspace:<filename>:<function-or-explicit-id>`: project script.

Set options by ID:

```json
{
  "datapeek.rendererOptions": {
    "builtin:scientific": {"dataset": "amplitude"},
    "builtin:npy": {"slices": ["iline", "xline"], "iline": 200},
    "workspace:text_array.py:read": {"cmap": "gray"}
  }
}
```

Configuration overrides defaults returned by `Array`. Options belong to each reader; remove format-specific fields when switching datasets. Custom Figure options are defined by the script itself.

| Shared array option | Meaning |
| --- | --- |
| `dataset` | Field/path when a container has multiple arrays |
| `slices` | Volume axes to preview: any distinct selection of `iline`, `xline`, `time` |
| `iline`, `xline`, `time` | Zero-based slice positions; default midpoint |
| `large_volume_gb` | Threshold for the default one/three-slice selection; default 1.5 decimal GB |
| `max_pixels` | Quick Preview samples per axis; default 512, allowed 16–2048 |
| `max_read_mib` | Estimated 2D read/decode and generic NPZ decompression budget; default 256 MiB |
| `preserve_aspect` | Preserve original slice row/column ratio; default `true` |
| `aspect_ratio` | Display width / height when `preserve_aspect=false`; positive number, default `2` |
| `cmap` | Colormap name; default `gray` for generic arrays |
| `clip_percentile` | Central percentile interval for initial automatic limits; default 99 |
| `vmin`, `vmax` | Explicit finite color limits, with `vmin < vmax`; provide both |
| `kind`, `time_axis`, `dt` | For DAS: `kind="das"`, time axis 0/1, optional sampling interval in seconds |

Explicit slice choices override the volume threshold. Selected volume slices are read completely, then reduced for display. Read budgets estimate decoding, not physical disk traffic or a process-memory hard limit. Compressed chunks may require larger reads than the requested area.

Initial automatic limits use the central percentile endpoints. If they straddle zero and `abs(median) <= 0.1 × IQR`, use `va=min(abs(vmin),abs(vmax))` and `[-va,va]`. These are display-percentile endpoints, not raw extrema. Other data keep their endpoints; constants receive a small interval. Manual limits are used directly. Detailed View keeps limits fixed until Apply or Reset Defaults.

## Opt-in caching

Built-in array readers use the preview cache. Custom array readers opt in with `@viewer.reader(..., cache=True)`. Cached output is validated against source metadata, options, and Python files in the script's directory. External side files and remote dependencies are not tracked; leave caching disabled for readers that depend on them. Figure renderers are not cached.

Use `datapeek.cache.enabled`, `maxEntries`, `maxMiB`, and `maxAgeDays` to configure the cache. **DataPeek: Clear Preview Cache** clears it manually.
