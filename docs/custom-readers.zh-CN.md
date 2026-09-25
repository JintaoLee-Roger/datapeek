# 自定义读取器与配置

[English](custom-readers.md) | 简体中文

## 脚本位置与选择

项目脚本放在工作区根目录的 `.datapeek/*.py`，个人脚本放在 `~/.datapeek/readers/*.py`。可通过 `datapeek.readerPaths` 指定其他个人目录。依赖安装在 DataPeek 选中的 Python 环境中，插件会提供 `datapeek` SDK。

唯一匹配的自定义读取器优先于内置读取器；多个匹配时提示选择，成功打开后记住。点击 **Choose Reader** 可更换。修改脚本后重新预览，已有 Detailed View 需先关闭。

用 `extensions` 匹配后缀，必要时通过 `patterns`/`exclude` 路径模式缩小范围。应匹配自己的数据布局，避免接管同后缀的无关文件。

## 返回数组

`@viewer.reader` 可复用快速预览、详细查看及三维数组的 3D 控件。返回具有 `shape`、`dtype` 和切片能力的对象即可；大数据应使用 mmap 或惰性读取。

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

`Array(data, options, title)` 提供显示默认值和可选标题。上下文管理器可在读取器使用期间保持文件打开。普通二维数组无需设置 `kind`，可用 `xlabel`、`ylabel` 自定义轴名称；三维数据应采用 `(iline, xline, time)` 顺序。

预处理由脚本负责。应使用固定参考，使同一点在概览和局部读取中的值保持一致，避免按每次请求区域重新归一化。

## 返回 Figure

需要自行绘图或叠加图层时，使用 `@viewer.register`：

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

返回 Matplotlib Figure 或 Python Plotly Figure。Figure 绘图器保留自己的显示方式，不附加通用数组的切片/3D 控件。完整用法见[地震叠加示例](real-data-debug.zh-CN.md#合成地震与断层叠加)。

## 读取器参数

[如何打开 Settings JSON、选择本地/远端设置](getting-started.zh-CN.md#设置读取器参数)。以下参数按读取器 ID 生效，不是单文件配置。

读取器 ID 可在 **Choose Reader** 中查看：

- `builtin:npy`：NPY 数组。
- `builtin:scientific`：NPZ、HDF5、Zarr 容器。
- `personal:<filename>:<function-or-explicit-id>`：个人脚本。
- `workspace:<filename>:<function-or-explicit-id>`：项目脚本。

按 ID 设置参数：

```json
{
  "datapeek.rendererOptions": {
    "builtin:scientific": {"dataset": "amplitude"},
    "builtin:npy": {"slices": ["iline", "xline"], "iline": 200},
    "workspace:text_array.py:read": {"cmap": "gray"}
  }
}
```

配置优先于 `Array` 返回的默认值。参数属于各个读取器，切换数据时应删除不适用的格式字段。自定义 Figure 的参数由脚本自行定义。

| 通用数组参数 | 含义 |
| --- | --- |
| `dataset` | 容器包含多个数组时指定字段或路径 |
| `slices` | 三维预览方向：从 `iline`、`xline`、`time` 中选择，不可重复 |
| `iline`、`xline`、`time` | 从零开始的切片索引，默认中间位置 |
| `large_volume_gb` | 默认选择一个/三个切片的体积阈值，默认 1.5 十进制 GB |
| `max_pixels` | 快速预览每轴显示点上限，默认 512，允许 16–2048 |
| `max_read_mib` | 二维读取/解码估算和通用 NPZ 解压预算，默认 256 MiB |
| `preserve_aspect` | 保留原始切片行列比例；默认 `true` |
| `aspect_ratio` | `preserve_aspect=false` 时的显示宽高比；正数，默认 `2` |
| `cmap` | 配色名称，通用数组默认 `gray` |
| `clip_percentile` | 初始自动色阶使用的中央百分位区间，默认 99 |
| `vmin`、`vmax` | 显式有限色阶，需同时提供且 `vmin < vmax` |
| `kind`、`time_axis`、`dt` | DAS 使用 `kind="das"`，时间轴为 0/1，可指定秒为单位的采样间隔 |

显式切片选择优先于体积阈值。选中切片完整读取后才降低显示分辨率。读取预算是解码估算，不是实际磁盘流量或进程内存的硬上限；压缩块可能导致实际读取范围大于请求区域。

初始色阶使用中央百分位区间的端点。若端点跨零且 `abs(median) <= 0.1 × IQR`，取 `va=min(abs(vmin),abs(vmax))`，使用 `[-va,va]`。这里使用显示百分位端点，而非原始极值；其他数据保留原端点，常量数据增加小间隔。手动色阶直接使用。详细查看中色阶保持固定，直到 Apply 或 Reset Defaults。

## 显式启用缓存

内置数组读取器使用预览缓存。自定义数组读取器可通过 `@viewer.reader(..., cache=True)` 启用。缓存会校验源数据元信息、参数及脚本同目录的 Python 文件，但不追踪外部辅助文件和远程依赖；依赖这些内容时应保持缓存关闭。Figure 绘图器不缓存。

通过 `datapeek.cache.enabled`、`maxEntries`、`maxMiB`、`maxAgeDays` 配置，使用 **DataPeek: Clear Preview Cache** 手动清除。
