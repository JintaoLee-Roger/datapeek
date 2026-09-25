# Development and testing

English | [简体中文](implementation-plan.zh-CN.md)

## Build

From the repository root:

```sh
npm ci
python3 -m pip install -r python/requirements.txt
npm run compile
```

Install optional format/viewer dependencies as needed: `h5py`, `zarr`, `seisvol`, and `cigvis` with its viewer dependencies. Press F5 with **Run DataPeek** to launch an Extension Development Host.

## Test

```sh
npm test
npm run test:extension
```

Python tests cover readers, sampling, color limits, cache behavior, and custom examples. Node tests cover file associations and frontend color logic. See [validation coverage](validation.md) for browser checks and platform limits.

Integration scripts under `tests/manual/` require Playwright, Chromium, system libraries, and the datasets referenced by the fixtures. Review paths before running them:

- `detail_fixture.cjs` + `browser_detail.py`: generate and exercise Detailed View and embedded 3D pages.
- `canvas_fixture.cjs` + `browser_quick.py`: generate and check Quick Preview pages, including pixel values.
- `worker_lifecycle.py`: service start, stop, restart, and process-exit cleanup.

`tests/smoke_real_data.py` and `tests/smoke_detail.py` exercise external sample data. Benchmark scripts also reference external datasets; adapt their paths to your environment. See [performance methodology](quick-preview-performance.md).

## Package

```sh
npm run package
```

The VSIX version comes from `package.json`. Install the generated VSIX using **Extensions: Install from VSIX...**, then run **Developer: Reload Window** and reopen previews.

To share with another user, build the VSIX above, then run:

```sh
python scripts/build_share_bundle.py
```

The resulting `build/datapeek-0.0.1-share.zip` contains the VSIX, bilingual guides, preview screenshot, and example scripts. Recipients start at `README.md`; no source-build environment is needed. The bundle does not include a Python environment or dependency installers.

## Documentation

English is the default for documentation, UI strings, and source comments. Each Markdown guide has a `.zh-CN.md` counterpart; update both when behavior changes. Code examples use English comments in both editions. Benchmark JSON is shared.

Keep the README focused on installation and common tasks. Put reader API details in [custom readers](custom-readers.md), maintenance details in [architecture](architecture.md), and measurements with their methodology in the performance guide. Document reproducible behavior rather than local installation state or session history.
