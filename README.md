# DataPeek

English | [简体中文](README.zh-CN.md)

A lightweight scientific data preview extension for VS Code. Open a quick overview, inspect a slice when needed, and add Python readers for your own formats.

## Get started

1. Install the DataPeek `.vsix` using **Extensions: Install from VSIX...**.
2. Install `numpy` and `matplotlib` in a Python 3.10+ environment. Add `h5py` for HDF5 or `zarr` for Zarr files. Detailed View requires `plotly`; 3D and the Petrel palette require `cigvis` and its viewer dependencies.
3. Run **DataPeek: Select Python Interpreter**.
4. Right-click a file or supported data directory and select **Preview with DataPeek**.

With Remote SSH, install Python dependencies and reader scripts on the remote host. Previews open in the active editor group. After updating the extension, run **Developer: Reload Window** and reopen existing previews.

## Supported data

| Reader | Use |
| --- | --- |
| Built-in | Generic 1D, 2D, and 3D arrays in NPY, NPZ, HDF5, and Zarr |
| Custom array reader | Your dataset names, axis conventions, or file formats; uses the shared preview and inspection controls |
| Custom Figure renderer | Your own Matplotlib or Python Plotly visualization, including overlays |

If a container holds multiple arrays, select one through its `dataset` option. Volumes use `(iline, xline, time)` order. Built-in readers display values as stored; preprocessing belongs in custom scripts.

Use **Choose Reader** to switch handlers. DataPeek remembers a successful choice for each file. See [custom readers and options](docs/custom-readers.md) and [DAS/seismic examples](docs/real-data-debug.md).

## Inspect data

Quick Preview shows a static overview. For array readers, **Detailed View** opens Plotly in the same tab.

| Control | Action |
| --- | --- |
| Axis and Slice | Select a volume section; the slider reads on release |
| Zoom and pan | Explore the loaded image without reading more data |
| Read Visible Region | Load more detail within the visible area |
| Full View | Return to the loaded overview |
| vmin/vmax, Colormap, Apply | Adjust display colors without rereading data |
| Reset Defaults | Restore the reader's configured display defaults |

Color limits remain fixed after initialization until you change or reset them. Zoom alone does not increase data resolution. Available palettes include `gray`, `seismic`, `RdBu_r`, `viridis`, and `Petrel`.

For volume readers, **3D View** opens cigvis in a separate tab; **Open in Browser** opens it externally. Use **Stop 3D** before rebuilding with new slice settings. Closing the 3D tab stops its service; closing only an external browser tab does not.

## Single-click previews

Run **DataPeek: Toggle Automatic Preview** to temporarily open matching files directly in DataPeek. Run it again to disable; reloading also restores the previous file associations. Close and reopen any already-open text tabs after enabling it.

Default patterns cover NPY, NPZ, H5, and HDF5. Add other file patterns with `datapeek.autoPreviewPatterns`. Directories still expand normally; use their context menu to preview them. `datapeek.previewExcludedPaths` can hide container paths from that menu.

## Large files and caching

Previews limit display resolution. For volumes up to 1.5 GB of uncompressed data, the default is three middle slices; larger volumes default to iline only. Each selected slice is read in full. Use the `slices` option to override the selection.

Compressed formats may need to decode more data than the displayed region. Generic NPZ readers decompress an entire selected array; NPY/Zarr are preferable for large data requiring partial reads.

The preview cache defaults to 100 entries, 512 MiB, and 7 days without access. Configure `datapeek.cache.*`, or run **DataPeek: Clear Preview Cache**. Custom array readers can opt in to caching; Figure renderers are not cached.

## Add a custom viewer

Place a Python script in `.datapeek/` at the workspace root, or `~/.datapeek/readers/` for reuse across projects. The extension supplies the `datapeek` SDK.

```python
from datapeek import viewer

@viewer.reader(name="Text array", extensions=[".txt"])
def read(path, options):
    import numpy as np
    return np.loadtxt(path)
```

For an overlay example, [seismic_fault_demo.py](examples/seismic_fault_demo.py) generates seismic traces from impedance and overlays faults. Installation, assumptions, and parameters are documented in the script and the [examples guide](docs/real-data-debug.md#synthetic-seismic-with-fault-overlay).

## Help and development

Errors and diagnostics appear in **Output → DataPeek**. Check the selected Python environment if a dependency is missing. Reader scripts execute Python code and require a trusted workspace.

- [Custom readers and configuration](docs/custom-readers.md)
- [DAS and seismic examples](docs/real-data-debug.md)
- [Development and testing](docs/implementation-plan.md)
