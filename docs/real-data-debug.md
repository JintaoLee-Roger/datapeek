# DAS and seismic examples

English | [简体中文](real-data-debug.zh-CN.md)

These optional scripts demonstrate dataset-specific readers and custom plots. Copy a script into a reader directory to enable it; installing the extension alone does not activate the examples. See [reader configuration](custom-readers.md).

## Synthetic seismic with fault overlay

[seismic_fault_demo.py](../examples/seismic_fault_demo.py) reads NPZ or Zarr with `imp` and `fault` arrays in `(iline, xline, time)` order.

From the repository root:

```sh
mkdir -p ~/.datapeek/readers
cp examples/seismic_fault_demo.py ~/.datapeek/readers/
```

Alternatively, copy it to the workspace's `.datapeek/` directory. Preview the NPZ file or Zarr directory, then select **Choose Reader → Demo: synthetic seismic + fault**.

The supplied matching patterns target `rgt_fault_imp_512v3/dataset/*.npz` and `rgt_fault_imp_512v3/zarr/*.zarr`. Edit `patterns` to match another layout, or select the renderer manually.

The example:

1. Reads one complete iline or xline section.
2. Computes `r[t] = (imp[t+1] - imp[t]) / (imp[t+1] + imp[t])`, with a zero final sample. `reflectivity='difference'` selects ordinary first differences instead.
3. Convolves along time with a zero-phase Ricker wavelet, keeping trace length and using zero padding at boundaries.
4. Overlays values above `fault_threshold` in red; background values remain transparent.

Edit `DEFAULTS` in the copied script for the axis, index, sample interval, frequency, and opacity. `index=None` selects the middle slice; `show_steps=True` also shows impedance and reflectivity. The 2 ms interval and 25 Hz frequency are demonstration assumptions, not file metadata.

Dependencies: `numpy`, `matplotlib`, and `zarr` for Zarr input. Zarr supports partial decoding; compressed NPZ must decode preceding data even though the script retains only the selected section. Prefer Zarr for repeated inspection of large volumes. This example returns a Figure and has no shared Detailed View/3D controls.

## Dataset-specific array reader

[geoscience.py](../examples/readers/geoscience.py) demonstrates how to supply field names, axis conventions, and format-specific readers while retaining shared array viewing controls.

```sh
mkdir -p ~/.datapeek/readers
cp examples/readers/geoscience.py ~/.datapeek/readers/
```

Review its path patterns and conventions before applying it to other datasets:

| Example layout | Convention |
| --- | --- |
| Zhoushan NPZ | `data`, time-first input transposed for DAS display |
| Ridgecrest `part_*.zarr/data/N.0.0` | Event number from filename, parent Zarr metadata, padding removed using `valid_nt` |
| Acquisition HDF5 | `Acquisition/Raw[0]/RawData` with sampling metadata |
| Marmousi simulation NPZ | `clean_strain_rate` with sampling interval |
| FORGE event NPZ | `data` with sampling interval |
| `rgt_fault_imp_512v3` Zarr | Defaults to `imp`; other fields selected through `dataset` |
| `*_h<nt>x<nx>x<ni>.dat` | C-order little-endian float32, reshaped to `(ni,nx,nt)` |
| `.slmdb`, `.szarr`, `.snpy` | `seisvol.open_volume(mode="r")` |

Dependencies vary by input: `h5py`, `zarr`, or `seisvol`, in addition to NumPy. The reader does not remove means or normalize values. Add any required preprocessing explicitly in your copy.

The Ridgecrest raw-chunk entry requires the `(1, channel, time)` chunk layout. Preview individual `N.0.0` members, not the event collection. Set `datapeek.previewExcludedPaths` if you want to hide the collection's preview menu.

For a personal installation, options use `personal:geoscience.py:geoscience`:

```json
{
  "datapeek.rendererOptions": {
    "personal:geoscience.py:geoscience": {
      "slices": ["iline", "xline"],
      "iline": 200,
      "max_pixels": 512
    }
  }
}
```

NPY can use `builtin:npy` directly. Supported shared options and read limits are described in [custom readers](custom-readers.md#reader-options).
