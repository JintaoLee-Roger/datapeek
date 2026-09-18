# DataPeek

An extensible Python-powered scientific data viewer for VS Code.

本地可用的 v0.1 基础版本。TypeScript 负责 VS Code UI 与执行编排，Python 负责数据读取、抽样和科学绘图。

## 安装与使用

1. 在 VS Code 运行 **Extensions: Install from VSIX...**，选择本项目生成的 `datapeek-0.1.0.vsix`。
2. 在要使用的 Python 环境安装依赖（Python 3.10+）：

   ```sh
   python -m pip install numpy matplotlib plotly
   ```

   只用静态图可不安装 Plotly。

3. 打开数据所在项目。运行 **DataPeek: Select Python Interpreter** 选择这个环境的 Python executable，或在 workspace settings 中设置：

   ```json
   {
     "datapeek.pythonPath": "/absolute/path/to/python"
   }
   ```

4. 在 Explorer 中右键数据文件 → **Preview with DataPeek**。

未显式配置时依次使用 Microsoft Python 扩展选中的环境、项目 `.venv`、PATH 中的 Python。不会自动安装依赖，也不会自动激活 conda shell；依赖额外环境变量的环境需自行准备。

## 当前功能

- `.npy` 一维实数数组 → matplotlib line；二维数组 → image + colorbar。
- 设置 `"datapeek.backend": "plotly"` 后重新预览，使用 Python Plotly 交互图，支持浏览器端缩放和平移。
- 自动发现当前 workspace folder 下 `.datapeek/*.py` 的自定义 renderer。
- 输出支持 matplotlib Figure 和 Python Plotly Figure；无需写 JavaScript renderer。
- 每次预览重新发现 Python 模块，保存自定义 renderer 后再次预览即可。
- 多个匹配 renderer 时弹出选择器；未知后缀可手动选择已注册 renderer。
- 错误、缺库和 Python traceback 显示在 DataPeek Output Channel。
- 超时、取消、关闭预览终止子进程；结果大小默认限制为 32 MiB。

大数组在 Python 中 mmap 并抽样：1D 上限 20,000 点，静态 2D 每轴最多 1,024 点，交互 2D 每轴最多 512 点。预览标题注明抽样；可能漏掉窄脉冲，不应作为精确分析结果。object、complex、字符串、空数组及 3D+ 暂不支持。

## 自定义 renderer

在**当前打开的项目根目录**创建 `.datapeek/text_signal.py`：

```python
from datapeek import viewer

@viewer.register(name="Text signal", extensions=[".txt"])
def render(path, options):
    import numpy as np
    from matplotlib.figure import Figure

    data = np.loadtxt(path)
    fig = Figure(figsize=(10, 5), layout="constrained")
    fig.subplots().plot(data[:20000])
    return fig
```

`path` 是 `pathlib.Path`，`options` 是普通字典。`datapeek` SDK 随扩展加载，无需 pip 安装；renderer 的其他依赖必须在选定 Python 环境中可用。SDK 只在 DataPeek runner 内自动可用。

返回 Python Plotly 图也可以：

```python
from datapeek import viewer

@viewer.register(name="Interactive signal", extensions=[".txt"])
def render(path, options):
    import numpy as np
    import plotly.graph_objects as go
    return go.Figure(go.Scatter(y=np.loadtxt(path)[:20000], mode="lines"))
```

通过设置向 renderer 传参：

```json
{
  "datapeek.rendererOptions": {
    "workspace:text_signal.py:render": { "gain": 2 },
    "builtin:npy": { "cmap": "seismic", "title": "Experiment A" }
  }
}
```

用户函数自行读取 `options`。ID 为 `workspace:<文件名>:<函数名>`，可用装饰器的 `id=` 指定稳定的局部 ID。以下划线开头的辅助模块不作为 renderer 扫描。模块导入会执行 Python 代码，因此 Restricted Mode 下禁用扩展。

## 本地开发

```sh
npm ci
npm run compile
python3 -m pip install -r python/requirements.txt
python3 examples/create_samples.py
```

在 VS Code 打开仓库并按 F5，启动 **Run DataPeek**。在扩展开发宿主打开 `examples` 文件夹，右键 `signal.npy`、`matrix.npy` 或 `custom_signal.csv` 预览。自定义示例只在 `examples` 作为 workspace root 时被发现。

```sh
npm test          # 需要当前 python3 环境具备科学库
npm run package  # 生成 datapeek-0.1.0.vsix
```

## Remote SSH 源码调试

可以把源码推到 GitHub 后，在远端 clone，再通过本地 VS Code 的 Remote - SSH 连接并打开远端仓库。仓库保留 `.vscode/launch.json` 和 `tasks.json`，可直接用 **Run DataPeek** 启动调试。

在远端仓库根目录准备环境（Node.js 建议 22 LTS 或更新受支持的 LTS，Python 3.10+）：

```sh
npm ci
python3 -m venv .venv
.venv/bin/python -m pip install -r python/requirements.txt
.venv/bin/python examples/create_samples.py
npm run compile
```

按 F5，在新开的 Extension Development Host 窗口打开远端 `examples` 子目录或其他数据项目。不要在该窗口再次打开扩展源码根目录。在新窗口执行 **DataPeek: Select Python Interpreter**，选择刚创建的远端 `<仓库路径>/.venv/bin/python`，然后右键数据文件预览。

F5 调试的是 TypeScript 扩展；Python renderer 的异常和 traceback 在 **Output → DataPeek** 中查看，Python 子进程断点调试尚未配置。修改 TypeScript 后重新编译并重启调试；修改 Python renderer 后重新预览即可。

扩展声明 `extensionKind: ["workspace"]`，因此 Python 与扩展在远端执行，Webview 在本机显示。可通过 **Developer: Show Running Extensions** 检查执行位置。这是受支持的调试方式，但本项目还没有完成真实 SSH 环境验收。参考 [VS Code 官方 Remote SSH 扩展调试说明](https://code.visualstudio.com/api/advanced-topics/remote-extensions#debugging-using-ssh)。

## 当前边界

- 本轮以本地使用为目标；macOS 实机验证结果见 `docs/validation.md`。扩展使用 workspace host 架构，但 Remote SSH、Windows、Linux 尚未实机验收。
- Plotly 是离线 HTML 输出，不提供 Python 回调或 Dash server。外部地图瓦片、CDN、任意 HTML 字符串输出暂不支持。
- 不支持 `.npz`、HDF5 浏览器、SEG-Y 内置解析、probe、多维切片。
- 每次操作独立 Python 进程，无常驻服务和 discovery 缓存。当前没有全局并发队列；一次打开很多不同文件会启动多个进程。
- 正常关闭会清理预览产物；VS Code 强制退出可能留下系统临时目录中的 `datapeek-*` 文件夹。

`docs/architecture.md` 和 `docs/implementation-plan.md` 包含后续设计，当前实际功能以本 README 为准。
