# 快速预览速度优化（2026-09-19，0.0.1）

[English](quick-preview-performance.md) | 简体中文


数组读取器默认走 Canvas。Python 读取和采样后按固定色阶生成 256 级颜色索引，浏览器一次性显示。去掉 Matplotlib Figure 构造、坐标布局、整张大图栅格化和 PNG 编码；仍完整读取选中的三维切片。默认显示采样预算、切片选择和初始色阶规则保持一致。自定义 Figure 的 Matplotlib/Plotly 输出兼容保留，详细查看和 cigvis 不改。

## 新旧路径实测

以下是单次 Python render 请求的中位数（每组 3 次），包含新进程启动、读取、显示产物生成；未命中预览缓存的两组关闭预览缓存。每轮交替新旧路径顺序。最后一轮独立执行，未同时运行数据 smoke 或浏览器测试。

| 数据 | 条件 | 原 Matplotlib → PNG | 新 Canvas |
| --- | --- | ---: | ---: |
| ridgecrest | 源文件页缓存冷 | 1.054 s | 0.362 s |
| ridgecrest | 源文件已预热 | 1.040 s | 0.350 s |
| ridgecrest | 预览缓存命中 | 0.151 s | 0.148 s |
| baiyun | 源文件页缓存冷 | 1.748 s | 0.729 s |
| baiyun | 源文件已预热 | 1.273 s | 0.294 s |
| baiyun | 预览缓存命中 | 0.082 s | 0.083 s |
| channels | 源文件页缓存冷 | 1.399 s | 0.448 s |
| channels | 源文件已预热 | 1.176 s | 0.209 s |
| channels | 预览缓存命中 | 0.083 s | 0.083 s |

Ridgecrest 使用 `part_00.zarr/data/7.0.0`。Baiyun 使用 `sx_cut.npy`（约 1.14 GiB），channels 为 `channels_origin_h651x601x401.dat`；两者均维持三个完整切片读取。

- 每次启动新的 Python，因此没有复用 NumPy/Zarr 导入状态或常驻 reader。
- “页缓存冷”：只对被测源文件执行 Linux `posix_fadvise(DONTNEED)`，随后用 `mincore` 验证驻留页。本次所有冷读试验源文件驻留页均为 **0**。没有执行全系统 drop_caches。
- “已预热”：紧接同一路径的冷读再次读取，并记录读前/读后驻留页。
- “预览缓存命中”：先填充独立预览缓存，再测量三次，检查日志确实出现 `cache HIT`。命中性能基本不变，主要收益来自第一次生成预览。
- Python 可执行文件、科学库文件和 Zarr 辅助元数据可能已预热；底层存储/服务端缓存不可控。因此这里的“冷”只指被测源文件的 **Linux 页缓存**，不能解释为服务器重启后、物理磁盘完全冷读。
- 表中不包含 VS Code 解释器选择、读取器发现、SSH 传输和用户端首次布局；不能把这些值直接当作点击到显示的端到端耗时。共享机器负载也会影响测量。

## 传输和前端

比较了原始颜色索引、zlib level 1、仅对采样索引做 PNG level 1/6（不含 Matplotlib 布局）。直接索引避免图形库启动；轻量压缩通常比 PNG 编码便宜，并能减少远程传输。压缩后节省超过 8 KiB 且超过原体积 10% 才采用压缩数据，否则传原始索引。浏览器使用原生 DecompressionStream，不新增 JS 绘图库。不能保证在每种网络/数据分布下都绝对最快，这是兼顾远程传输和本地计算的默认策略。

最终完整产物大小（含标题、坐标和前端脚本）：

| 数据 | 原 PNG | 新预览 HTML |
| --- | ---: | ---: |
| Ridgecrest 7.0.0 | 531,656 B | 174,400 B |
| Baiyun | 786,160 B | 526,749 B |
| channels | 708,074 B | 472,207 B |

浏览器脚本中的 renderMs 只衡量前端脚本处理，不包含网络或屏幕首次绘制时间。功能检查和平台边界见[验证覆盖](validation.zh-CN.md)。

## 复现

```sh
python tests/benchmark_quick.py /tmp/quick-benchmark.json
python tests/smoke_real_data.py /tmp/quick-data
python tests/benchmark_quick_codecs.py /tmp/quick-data /tmp/quick-codecs.json
npm run compile
node tests/manual/canvas_fixture.cjs /tmp/quick-data
python tests/manual/browser_quick.py <上一步输出的目录>
```

需要脚本引用的外部样本数据、Linux mincore/fadvise 及相应 Python 读取依赖，运行前应修改数据路径。浏览器测试另外需要 Playwright/Chromium 和系统运行库。不要同时跑上述速度基准和其他数据读取测试。

原始记录：[新旧路径及驻留页](quick-preview-benchmark.json)、[编码时间与体积](quick-preview-codecs.json)。
