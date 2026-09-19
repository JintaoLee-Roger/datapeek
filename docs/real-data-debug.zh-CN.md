# DAS 与地震示例

[English](real-data-debug.md) | 简体中文

这些可选脚本演示数据集专用读取器和自定义绘图。复制到读取器目录后才会启用，安装插件不会自动启用示例。通用配置见[自定义读取器](custom-readers.zh-CN.md)。

## 合成地震与断层叠加

[seismic_fault_demo.py](../examples/seismic_fault_demo.py) 读取包含 `imp` 和 `fault` 的 NPZ 或 Zarr，数组顺序为 `(iline, xline, time)`。

在仓库根目录执行：

```sh
mkdir -p ~/.datapeek/readers
cp examples/seismic_fault_demo.py ~/.datapeek/readers/
```

也可复制到工作区的 `.datapeek/`。预览 NPZ 文件或 Zarr 目录后，选择 **Choose Reader → Demo: synthetic seismic + fault**。

默认路径模式匹配 `rgt_fault_imp_512v3/dataset/*.npz` 和 `rgt_fault_imp_512v3/zarr/*.zarr`。其他布局可修改 `patterns`，或手动选择绘图器。

示例流程：

1. 完整读取一个 iline 或 xline 截面。
2. 计算 `r[t] = (imp[t+1] - imp[t]) / (imp[t+1] + imp[t])`，最后一点为零。`reflectivity='difference'` 可改为普通一阶差分。
3. 沿时间轴与零相位 Ricker 子波褶积，保持道长，边界补零。
4. 将大于 `fault_threshold` 的断层位置叠加为红色，背景透明。

修改副本中的 `DEFAULTS` 可设置方向、索引、采样间隔、频率和透明度。`index=None` 为中间切片，`show_steps=True` 同时展示阻抗和反射系数。默认 2 ms 和 25 Hz 是演示假设，不是文件元数据。

依赖为 `numpy`、`matplotlib`，Zarr 输入另需 `zarr`。Zarr 支持局部解码；压缩 NPZ 即使只保留选中截面，也必须解码前面的数据。反复查看大体积时优先使用 Zarr。此示例返回 Figure，不附带通用数组的 Detailed View/3D 控件。

## 数据集专用数组读取器

[geoscience.py](../examples/readers/geoscience.py) 演示如何指定字段、坐标约定和格式读取方式，同时复用数组查看控件。

```sh
mkdir -p ~/.datapeek/readers
cp examples/readers/geoscience.py ~/.datapeek/readers/
```

应用到其他数据集前，应检查脚本中的路径模式和约定：

| 示例布局 | 约定 |
| --- | --- |
| Zhoushan NPZ | `data`，时间轴在前，显示 DAS 时转置 |
| Ridgecrest `part_*.zarr/data/N.0.0` | 文件名决定事件编号，使用父级 Zarr 元数据，通过 `valid_nt` 移除补零 |
| Acquisition HDF5 | `Acquisition/Raw[0]/RawData` 及采样元数据 |
| Marmousi 仿真 NPZ | `clean_strain_rate` 及采样间隔 |
| FORGE 事件 NPZ | `data` 及采样间隔 |
| `rgt_fault_imp_512v3` Zarr | 默认 `imp`，通过 `dataset` 选择其他字段 |
| `*_h<nt>x<nx>x<ni>.dat` | C-order、小端 float32，重排为 `(ni,nx,nt)` |
| `.slmdb`、`.szarr`、`.snpy` | `seisvol.open_volume(mode="r")` |

除 NumPy 外，依输入格式可能需要 `h5py`、`zarr` 或 `seisvol`。读取器不去均值、不归一化；需要预处理时，在副本中明确添加。

Ridgecrest 裸块入口要求 `(1, channel, time)` 分块布局，应预览单独的 `N.0.0` 成员，而不是事件集合。如需隐藏集合的预览菜单，可配置 `datapeek.previewExcludedPaths`。

个人目录安装后，参数使用 `personal:geoscience.py:geoscience`：

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

NPY 可直接使用 `builtin:npy`。通用参数和读取限制见[读取器参数](custom-readers.zh-CN.md#读取器参数)。
