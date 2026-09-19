# Validation coverage

English | [简体中文](validation.zh-CN.md)

Recorded for version 0.0.1 on 2026-09-19. Test results describe the checked environments, not a guarantee for every platform or dependency combination.

| Scope | Evidence |
| --- | --- |
| Python | 57 tests passed: readers, slicing, colors, caching, Canvas output, and seismic/fault example |
| TypeScript / Node | Compilation and 11 tests passed: associations and frontend color logic |
| Quick Preview | Nine sample datasets rendered; browser pixel hashes matched Python output; 1D, single-point, NaN/Inf, and Petrel cases checked |
| Detailed View | Fixed limits, slice selection, manual colors, zoom without reads, region reads, and overview restoration checked in Chromium |
| Region reads | An 11×11 region loaded with one request, preserving axes and color limits |
| 3D | Real Viser canvas/WebSocket loaded in generated embedded pages; mocked VS Code host verified browser actions and tab-close cleanup |
| Worker lifecycle | Start, stop, restart, and port release after process exit checked |
| Custom Figure example | NPZ/Zarr inputs generated seismic/fault overlays; numerical tests checked reflection, convolution alignment, and transparent masks |

## Compatibility limits

Python 3.12 has been tested; the declared Python minimum is 3.10. Tests use installed scientific dependencies and a cigvis version supporting lazy slice providers.

Complete Remote SSH desktop file-opening flows and final Webview port forwarding still need acceptance in a real VS Code window. Browser and mock-host tests do not establish those behaviors. Windows process cleanup and the minimum-version dependency matrix remain unverified.

See [development commands](implementation-plan.md) to run checks and [performance methodology](quick-preview-performance.md) for timing conditions. Re-run tests for code changes; documentation-only edits require link and content checks rather than repeating data benchmarks.
