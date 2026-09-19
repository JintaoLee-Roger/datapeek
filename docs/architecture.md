# Architecture

English | [简体中文](architecture.zh-CN.md)

This guide is for extension maintainers. For public reader interfaces, see [custom readers](custom-readers.md).

## Execution model

DataPeek runs in the workspace extension host. Under Remote SSH, Python execution and file reads happen remotely while Webviews display on the client. Quick Preview uses one-shot Python requests; each Detailed View owns a persistent reader process.

| Module | Responsibility |
| --- | --- |
| `src/extension.ts` | Interpreter selection, discovery, quick requests, artifact validation, and display |
| `src/autoPreview.ts` | Temporary file associations and recovery |
| `src/details.ts` | Detail requests, process lifecycle, 3D tabs, and URL forwarding |
| `media/detail.js` | Plotly controls and display state |
| `python/runner.py` | Script discovery, execution, and output adaptation |
| `python/detail_worker.py` | Persistent detail request protocol |
| `python/datapeek/sources.py` | Generic sources and reader resource lifetimes |
| `python/datapeek/scientific.py` | Shared slice preparation and Matplotlib rendering |
| `python/datapeek/quick.py` / `quick.html` | Static Canvas artifacts |
| `python/datapeek/detail.py` | Slice/region reads and cigvis services |
| `python/datapeek/colors.py` | Initial color limits and palettes |
| `python/datapeek/cache.py` | Persistent preview cache |

## Reader boundaries

The core reads generic array formats. Dataset-specific names, dimensions, and preprocessing belong in custom scripts. Array readers share viewer controls; Figure renderers own their output. Context-manager readers retain resources until the viewing session closes.

Python stdout/stderr are diagnostic channels. One-shot requests use a response file; detail workers use a structured message protocol. Validate returned artifact paths and enforce output limits before exposing local files to a Webview. Only trusted workspaces may execute reader scripts.

## Display and state

Quick Preview prepares selected slices, color limits, and a bounded display buffer, then produces static Canvas HTML. Custom Figures use their corresponding image/HTML adapters. Detailed View requests sampled arrays for explicitly selected slices or regions.

Zooming and panning remain frontend operations. Applied color limits stay fixed across reads. The frontend retains the overview for Full View; failed reads preserve the previous image. Requests carry sequence information so stale results cannot overwrite a newer selection.

Saved slice/color settings are keyed by file, reader, dataset, and configuration. Temporary artifacts are removed when their panel closes. Hidden detail tabs retain their reader and display state.

## Caches

Persistent preview caching validates source metadata, options, interpreter/dependency versions, and relevant rendering code. Custom readers must opt in; Python files in the reader's directory are included in validation, but external dependencies are not.

Directory stores require metadata traversal, so cache hits are not constant-cost. Entries have count, byte, and age limits; incomplete or corrupt entries fall back to rendering. Panels use independent artifact copies so eviction does not invalidate displayed content.

Detailed View has a separate bounded LRU for complete slices. Region requests crop cached slices or submit region indices to the source on a miss. Format-level caches and decompression buffers are outside this LRU.

## 3D lifecycle

The detail worker calls cigvis to create/display slices from a lazy source and selected positions/colors. Viser listens on loopback; `vscode.env.asExternalUri` supplies the forwarded URL for an embedded Webview or explicit browser action.

Closing 3D stops its service. Closing the parent detail tab or returning to Quick Preview terminates the reader and any associated service. Stop/restart rebuilds a scene from changed 2D settings; the two views do not continuously synchronize.

## Automatic preview

A read-only custom editor handles associated files. The temporary toggle edits user file associations scoped to the workspace path and scheme, without writing to the data directory. The resolver's match target is `scheme:path`; remote extension-host `file:` URIs require conversion to the UI's `vscode-remote:` scheme.

Disabling or reloading restores saved associations. Activation recovers after abnormal exit while preserving user overrides. Directories keep their normal expansion behavior. File patterns and excluded containers are configuration, not dataset-specific core rules.
