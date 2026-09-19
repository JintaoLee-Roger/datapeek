# Quick Preview performance (2026-09-19, 0.0.1)

English | [简体中文](quick-preview-performance.zh-CN.md)

Array readers default to Canvas. Python reads and samples data, computes 256-level color indices with fixed limits, and the browser draws once. This removes Matplotlib Figure construction, axis layout, full-figure rasterization, and PNG encoding. Selected volume slices are still read in full. Display budgets, slice selection, and initial color-limit rules are unchanged. Custom Matplotlib/Plotly Figures, Detailed View, and cigvis retain their existing paths.

## Legacy versus current path

Times are medians of three independent Python render requests per group, including process startup, reading, and artifact generation. Both source-cache groups disable the preview cache. Backend order alternates between repetitions. The final run was separate from data smoke and browser tests.

| Data | Condition | Matplotlib → PNG | Canvas |
| --- | --- | ---: | ---: |
| ridgecrest | Cold source page cache | 1.054 s | 0.362 s |
| ridgecrest | Warm source | 1.040 s | 0.350 s |
| ridgecrest | Preview cache hit | 0.151 s | 0.148 s |
| baiyun | Cold source page cache | 1.748 s | 0.729 s |
| baiyun | Warm source | 1.273 s | 0.294 s |
| baiyun | Preview cache hit | 0.082 s | 0.083 s |
| channels | Cold source page cache | 1.399 s | 0.448 s |
| channels | Warm source | 1.176 s | 0.209 s |
| channels | Preview cache hit | 0.083 s | 0.083 s |

Ridgecrest uses `part_00.zarr/data/7.0.0`. Baiyun uses `sx_cut.npy` (about 1.14 GiB); channels uses `channels_origin_h651x601x401.dat`. Both volume cases retain three complete slice reads.

- Every trial starts fresh Python, without reusing NumPy/Zarr imports or persistent readers.
- **Cold source page cache:** Linux `posix_fadvise(DONTNEED)` targets only the tested source file, followed by `mincore` residency checks. Every cold trial had **0** resident source pages. Global drop_caches was not used.
- **Warm source:** repeats the same path immediately after its cold read, recording residency before and after.
- **Preview cache hit:** populates an independent cache, measures three hits, and verifies `cache HIT` in logs. Hit performance is largely unchanged; most improvement is in first-time generation.
- Python executables, library files, and auxiliary Zarr metadata may be warm. Storage/server caches are uncontrolled. “Cold” here means only the tested source's **Linux page cache**, not a rebooted server or completely cold physical disk.
- These times exclude VS Code interpreter selection, reader discovery, SSH transport, and client-side initial layout. They are not end-to-end click-to-display times. Shared-machine load also affects measurements.

## Transport and frontend

Candidates included raw color indices, zlib level 1, and PNG level 1/6 of the sampled indices alone (without Matplotlib layout). Direct indices avoid plotting-library startup. Lightweight compression is usually cheaper than PNG encoding and reduces remote transport. Compression is used only when it saves more than 8 KiB and 10%; otherwise, raw indices are sent. The browser uses native DecompressionStream with no additional plotting runtime. This is a default tradeoff between transport and computation, not a guarantee of the fastest result for every network or data distribution.

Complete artifact sizes, including title, axes, and frontend code:

| Data | Legacy PNG | Preview HTML |
| --- | ---: | ---: |
| Ridgecrest 7.0.0 | 531,656 B | 174,400 B |
| Baiyun | 786,160 B | 526,749 B |
| channels | 708,074 B | 472,207 B |

The browser script's renderMs measures frontend processing only, not network time or first screen paint. Functional checks and platform limits are listed in [validation coverage](validation.md).

## Reproduce

```sh
python tests/benchmark_quick.py /tmp/quick-benchmark.json
python tests/smoke_real_data.py /tmp/quick-data
python tests/benchmark_quick_codecs.py /tmp/quick-data /tmp/quick-codecs.json
npm run compile
node tests/manual/canvas_fixture.cjs /tmp/quick-data
python tests/manual/browser_quick.py <generated-directory>
```

Requires the external sample datasets referenced by the scripts, Linux mincore/fadvise, and Python reader dependencies. Adjust dataset paths before running. Browser tests additionally need Playwright/Chromium and system libraries. Do not run performance benchmarks alongside other data-reading tests.

Raw records: [backend timings and page residency](quick-preview-benchmark.json), [codec timings and sizes](quick-preview-codecs.json).
