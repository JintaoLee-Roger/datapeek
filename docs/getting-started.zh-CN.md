# 安装与首次预览

[English](getting-started.md) | 简体中文

## 安装插件

需要 VS Code 1.90 或更新版本，以及 Python 3.10 或更新版本。已测试的 Python 版本为 3.12，详见[测试环境](validation.zh-CN.md#已测试的依赖)。

DataPeek 通过 VSIX 分发。使用分享包中的 `datapeek-0.0.1.vsix`，或向分享插件的人获取。分享包还包含这些指南、`examples/` 和 `python/requirements.txt`，无需通过 Marketplace 安装。从源码构建的方法见[开发与打包](implementation-plan.zh-CN.md)。

打开命令面板（`Ctrl+Shift+P`，macOS 使用 `Cmd+Shift+P`），运行 **Extensions: Install from VSIX...** 并选择 VSIX。在 Remote SSH 窗口中，请在扩展面板确认 DataPeek 安装在 SSH 主机上。Python、数据和读取器脚本也必须在该主机上可用。

插件 ID 为 `JintaoLi.datapeek`。如果之前安装过 `datapeek-local.datapeek`，请卸载旧构建并重载 VS Code，避免重复命令。

## 准备 Python

在准备供 DataPeek 使用的环境中安装基本依赖：

```sh
python -m pip install numpy matplotlib
```

按需安装可选依赖：

| 功能 | 命令 |
| --- | --- |
| 详细查看、自定义 Plotly Figure | `python -m pip install plotly` |
| HDF5 | `python -m pip install h5py` |
| Zarr | `python -m pip install zarr` |
| cigvis 3D、Petrel 配色 | `python -m pip install "cigvis[viser]"` |

这里的 `python` 应是稍后在 DataPeek 中选择的解释器；必要时使用可执行文件的完整路径。使用已安装的 VSIX 不需要 Node.js 或 npm。SeisVol 格式需要自定义读取器及兼容的 `seisvol` 环境，不属于内置格式。

运行 **DataPeek: Select Python Interpreter**，选择 Python 可执行文件，而不是所在目录。可通过以下命令查看路径：

```sh
python -c "import sys; print(sys.executable)"
```

打开文件夹时，解释器选择命令会保存工作区设置。如果文件夹只读，请按下文方法在本地的 User 设置或 SSH 的 Remote 设置中填写 `datapeek.pythonPath`，使用可执行文件的绝对路径。更换解释器后重新打开预览。

## 用小文件验证安装

在解压后的分享包或源码仓库根目录运行：

```sh
python examples/create_sample.py sample.npy
```

在 VS Code 中打开该文件夹，右键资源管理器中的 `sample.npy`，选择 **Preview with DataPeek**。应看到一个小型合成三维数据的三个切片，无需准备外部数据。脚本不会覆盖已有文件。

![合成样例的快速预览](images/quick-preview.png)

安装 Plotly 后，点击 **Detailed View**，改变 **Axis** 或 **Slice**，并尝试缩放。缩放只操作已加载图像；点击 **Read Visible Region** 才会读取更多细节。若想指定显示比例，取消 **Original aspect**，设置 **W/H**，例如 `2` 表示 2:1。

## 设置读取器参数

本地默认设置使用 **Preferences: Open User Settings (JSON)**。SSH 窗口中的远端默认设置使用 **Preferences: Open Remote Settings (JSON)**。只有需要将设置保存在可写项目中时，才使用 **Preferences: Open Workspace Settings (JSON)**。同一个设置项的工作区设置优先于 Remote/User 设置。

将以下属性合并到已有 JSON 对象中，不要覆盖其他设置：

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

将 `amplitude` 替换成实际数组字段或 HDF5/Zarr 路径；如果不适用，请删除这条示例配置。参数对所有使用该读取器 ID 的文件生效，并非单文件覆盖。针对不同数据集的默认行为，可使用带有明确路径匹配规则的自定义读取器。**Choose Reader** 会显示 ID，完整参数见[读取器选项](custom-readers.zh-CN.md)。

修改配置后重新打开预览。详细查看会记住该视图的手动显示设置，点击 **Reset Defaults** 可恢复配置值。

## 尝试自定义读取器

在 VS Code 打开的文件夹中创建 `.datapeek/text_array.py`：

```python
from datapeek import viewer

@viewer.reader(name="Text array", extensions=[".txt"])
def read(path, options):
    import numpy as np
    return np.loadtxt(path)
```

在 `.datapeek` 文件夹旁创建 `sample.txt`：

```text
0 1 0
1 2 1
0 1 0
```

右键 `sample.txt` 进行预览；如需选择读取器，点击 **Choose Reader → Text array**。无需直接运行 `text_array.py`，也不要安装名为 `datapeek` 的 Python 包：读取器 SDK 由插件提供。跨项目复用时，可将脚本放在扩展宿主的 `~/.datapeek/readers/` 中；Windows 下的 `~` 表示用户主目录。

分享包还包含[可复制使用的科学数据示例](real-data-debug.zh-CN.md)。如果只收到了 VSIX，又需要这些示例，请获取完整分享包。修改读取器后应重新打开预览。只信任你愿意执行的读取器脚本。

## 常见问题

| 现象 | 检查方法 |
| --- | --- |
| `ModuleNotFoundError` | 使用选中解释器的 `-m pip` 安装依赖；SSH 模式下安装在远端。 |
| 容器要求指定 `dataset` | 在 `builtin:scientific` 下设置字段或路径。普通容器的错误信息会列出可用数组。 |
| 自定义读取器未出现 | 检查脚本位置、后缀/路径规则、解释器依赖，以及 **Output → DataPeek**，然后重新打开预览。 |
| 保存设置报 `EACCES` | 使用 User/Remote 设置，不要往只读目录的 `.vscode/settings.json` 写入。 |
| 自动预览仍出现大文件文本警告 | 关闭已有文本标签后重新打开文件，检查 `datapeek.autoPreviewPatterns`；目录仍需右键预览。 |
| 大型压缩 NPZ 超过读取预算 | 转换成支持局部读取的 NPY/Zarr，或确认内存足够后主动提高 `max_read_mib`。 |
| 3D 标签页失败或空白 | 检查选中环境是否安装 `cigvis[viser]`，查看 **Output → DataPeek**，并尝试 **Open in Browser**；远端需能转发端口。 |
| 更新后仍显示旧界面 | 执行 **Developer: Reload Window**，关闭旧预览后重新打开。 |

反馈问题时，请提供 DataPeek、VS Code、Python 版本，本地或 SSH 使用方式、读取器 ID、数组形状和 dtype，以及 **Output → DataPeek** 中相关错误。优先提供小型合成复现数据，无需分享私有数据。
