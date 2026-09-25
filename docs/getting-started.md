# Installation and first preview

English | [简体中文](getting-started.zh-CN.md)

## Install the extension

You need VS Code 1.90 or newer and Python 3.10 or newer. Python 3.12 is the tested version; see [the tested environment](validation.md#tested-dependencies).

DataPeek is distributed as a VSIX. Use the `datapeek-0.0.1.vsix` supplied with the sharing bundle, or request it from the person sharing the extension. The bundle also contains these guides, `examples/`, and `python/requirements.txt`. A Marketplace installation is not required. To build from source, see [development and packaging](implementation-plan.md).

Open the Command Palette (`Ctrl+Shift+P`, or `Cmd+Shift+P` on macOS), run **Extensions: Install from VSIX...**, and select the VSIX. In a Remote SSH window, ensure DataPeek is installed on the SSH host in the Extensions view. Python, data, and reader scripts must be available on that host.

The extension ID is `JintaoLi.datapeek`. If you installed an earlier build under `datapeek-local.datapeek`, uninstall that build to avoid duplicate commands, then reload VS Code.

## Prepare Python

In the environment you want DataPeek to use, install the basic dependencies:

```sh
python -m pip install numpy matplotlib
```

Install only the optional features you need:

| Feature | Command |
| --- | --- |
| Detailed View and custom Plotly Figures | `python -m pip install plotly` |
| HDF5 | `python -m pip install h5py` |
| Zarr | `python -m pip install zarr` |
| cigvis 3D and Petrel palette | `python -m pip install "cigvis[viser]"` |

`python` means the interpreter you will select in DataPeek; use its full executable path if necessary. Node.js and npm are not required to use an installed VSIX. SeisVol formats require a separate custom reader and a compatible `seisvol` installation; they are not built-in formats.

Run **DataPeek: Select Python Interpreter** and select the Python executable, not its containing directory. You can find the executable with:

```sh
python -c "import sys; print(sys.executable)"
```

The selection command saves a workspace setting when a folder is open. If that folder is read-only, set `datapeek.pythonPath` in User settings for local use, or Remote settings for SSH, as described below. Use an absolute executable path. Restart an existing preview after changing the interpreter.

## Verify with a small file

From the extracted sharing bundle or repository root:

```sh
python examples/create_sample.py sample.npy
```

Open that folder in VS Code. Right-click `sample.npy` in Explorer and select **Preview with DataPeek**. You should see three sections of a small synthetic volume. No external dataset is needed, and the script refuses to overwrite an existing file.

![Quick Preview of the synthetic sample](images/quick-preview.png)

If Plotly is installed, click **Detailed View**, change **Axis** or **Slice**, and try zooming. Zoom operates on the loaded image; **Read Visible Region** explicitly loads more detail. To choose a display ratio, uncheck **Original aspect** and set **W/H**, such as `2` for 2:1.

## Configure a reader

Open **Preferences: Open User Settings (JSON)** for local defaults. In an SSH window, use **Preferences: Open Remote Settings (JSON)** for remote defaults. Use **Preferences: Open Workspace Settings (JSON)** only when settings should belong to a writable project. Workspace settings override Remote/User settings for the same setting.

Merge the following property into the existing JSON object; do not replace unrelated settings:

```json
{
  "datapeek.rendererOptions": {
    "builtin:npy": {
      "cmap": "gray",
      "preserve_aspect": false,
      "aspect_ratio": 2
    },
    "builtin:scientific": {
      "dataset": "amplitude"
    }
  }
}
```

Replace `amplitude` with the actual array key or HDF5/Zarr path. Remove that example entry if it does not apply. Options are shared by all files using that reader ID; they are not per-file overrides. For dataset-specific defaults, create a custom reader with narrow path patterns. **Choose Reader** displays the IDs. See [all reader options](custom-readers.md#reader-options).

Reopen a preview after changing configuration. In Detailed View, manual display controls are remembered for that view; **Reset Defaults** restores the configured values.

## Try a custom reader

Create `.datapeek/text_array.py` in the folder opened in VS Code:

```python
from datapeek import viewer

@viewer.reader(name="Text array", extensions=[".txt"])
def read(path, options):
    import numpy as np
    return np.loadtxt(path)
```

Create `sample.txt` alongside the `.datapeek` folder:

```text
0 1 0
1 2 1
0 1 0
```

Right-click `sample.txt` and preview it. Use **Choose Reader → Text array** if prompted. Do not run `text_array.py` directly or install a package named `datapeek`: the extension supplies its reader SDK. For use across projects, put the script in `~/.datapeek/readers/` on the extension host instead. On Windows, `~` means your user home directory.

The sharing bundle includes [ready-to-copy scientific examples](real-data-debug.md). Download or request the complete bundle if you only received the VSIX and want these examples. Editing a reader requires reopening the preview. Only trust reader scripts you intend to execute.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| `ModuleNotFoundError` | Install the package with the selected interpreter's `-m pip`; for SSH, install it remotely. |
| A container asks for `dataset` | Set the array key/path using `builtin:scientific`. The error lists available arrays for ordinary containers. |
| A custom reader is missing | Check script location, suffix/path patterns, selected Python dependencies, and **Output → DataPeek**. Reopen the preview. |
| Settings fail with `EACCES` | Use User/Remote settings instead of writing `.vscode/settings.json` in a read-only folder. |
| Automatic preview still opens a large-file text warning | Close the existing text tab and reopen the file. Check `datapeek.autoPreviewPatterns`; directories require right-click preview. |
| A large compressed NPZ exceeds the read budget | Convert to NPY/Zarr for partial reads, or deliberately raise `max_read_mib` if sufficient memory is available. |
| The 3D tab fails or is blank | Check the selected environment has `cigvis[viser]`, inspect **Output → DataPeek**, and try **Open in Browser**. Remote port forwarding must be available. |
| An update appears unchanged | Run **Developer: Reload Window**, then close and reopen old previews. |

When reporting a problem, include DataPeek/VS Code/Python versions, local or SSH usage, reader ID, array shape/dtype, and the relevant **Output → DataPeek** error. A small synthetic reproducer is preferable to sharing private data.
