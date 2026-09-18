# DataPeek v0.1 架构设计

状态：架构设计基线。本地基础版已实现；本文还包含缓存、并发队列等后续设计，当前功能与限制以 README.md 为准。

## 1. 职责与部署

```text
本地 VS Code UI / Webview
              ↑ PNG 或包含有限绘图数据的 HTML/JS 资源
Workspace Extension Host（本地或 Remote SSH server）
              ↓ spawn：指定 Python executable，无 shell
Python runner + SDK + renderers
              ↓ 在同一台机器读文件、处理、绘图
本地/远端数据文件
```

- 扩展声明 `extensionKind: ["workspace"]`，提供 Node extension entrypoint，不提供 browser entrypoint。
- Remote SSH 时扩展、Python、SDK 和输出目录都位于远端；不自行建立 SSH 连接、HTTP 服务或端口转发。
- 原始数组不通过 extension IPC 传输，TypeScript 不导入科学绘图库，不实现抽样或图形定义。
- 交互式输出依赖 Plotly 自带的浏览器运行时，但 Figure、布局、数据处理与输出适配全部由 Python 完成。
- v0.1 支持本地文件系统与 Remote SSH 文件；虚拟文件系统不支持。URI 必须属于当前 extension host 可访问的文件系统，拒绝任意 provider URI。

VS Code 的 workspace extension host 选择机制支持这种部署方式：[官方说明](https://code.visualstudio.com/api/advanced-topics/extension-host)。

## 2. Python Renderer API

内置与用户 renderer 使用同一 SDK `datapeek`。SDK 随 VSIX 发布，由 runner 引导加载，不要求用户额外 pip 安装 SDK；科学计算依赖安装在选定环境中。初始 Python 最低版本设为 3.10，实现时通过兼容性测试确认。

```python
from pathlib import Path
from typing import Any, Mapping
from datapeek import viewer

@viewer.register(
    name="My DAS Viewer",
    extensions=[".h5", ".das"],
)
def render(path: Path, options: Mapping[str, Any]):
    # 在函数内部导入可选依赖，避免 discovery 因缺少依赖而失败。
    import h5py
    from matplotlib.figure import Figure

    with h5py.File(path, "r") as f:
        # 用户负责领域相关的读取策略；此处仅为例子。
        data = f["strain"][:512, :1024]

    fig = Figure(figsize=(10, 5))
    fig.subplots().imshow(data, aspect="auto", origin="lower")
    return fig
```

注册接口：

```python
viewer.register(
    *,
    name: str,
    extensions: list[str],
    id: str | None = None,
)
```

- renderer 是同步函数 `render(path, options)`；返回 `matplotlib.figure.Figure` 或 `plotly.basedatatypes.BaseFigure`。
- `path` 是当前 host 的绝对 `pathlib.Path`，`options` 是 JSON object。v0.1 不注入 VS Code 对象，不要求用户接触 TS。
- 不支持 `plt.show()`、隐式当前 Figure、裸 ndarray、任意字符串 HTML 或启动服务作为返回值；不支持类型给出明确错误。
- `id` 是模块内稳定标识；省略时使用函数名。最终 ID 是 `builtin:npy` 或 `workspace:<relative-posix-module-path>:<local-id>`。workspace 身份另外保存在发现作用域中，不把绝对路径暴露到可移植配置。
- 同名显示名称允许存在，UI 展示来源；重复最终 ID 属于注册错误，不能静默覆盖。
- renderer 可读取任意项目数据、使用任意库；框架只约束输出接口与执行生命周期，不试图理解领域格式。
- v0.1 options 由资源作用域的 `datapeek.rendererOptions` 提供，按最终 renderer ID 映射到 JSON object。内置参数有校验，用户参数原样交给 renderer。
- `options` 不包含可修改的输出目录或协议控制字段；runner 的限制独立于 renderer options。

示例配置：

```json
{
  "datapeek.rendererOptions": {
    "builtin:npy": { "backend": "matplotlib", "cmap": "viridis" },
    "workspace:das.py:render": { "dataset": "strain" }
  }
}
```

以上示例函数固定读取 `strain`；项目可自行改为读取 `options.get("dataset", "strain")`。

SDK v0.1 API 版本为 1，与 wire protocol 版本分开。以后增加输出适配器只改 Python backend；TS 消费稳定的 artifact 描述。

## 3. Discovery 与选择

默认扫描所属 workspace folder 的 `.datapeek/*.py`，文件名排序；跳过以下划线开头的文件。不递归、不混入其他 workspace folder。没有所属 workspace 的文件只使用 built-in renderers。

1. Preview 或首次打开 renderer picker 时，检查 trust 并选定解释器。
2. 独立 discovery 子进程注册 built-ins，并通过 `importlib` 加载用户模块。使用唯一模块名，避免不同文件的 `render` 冲突。
3. 每个模块以注册事务加载：失败时撤销该模块的注册，继续其他模块；返回逐模块诊断。
4. 输出 renderer 描述：ID、名称、extensions、来源、模块相对路径、SDK 版本。仅包含 JSON metadata，不传 Python callable。
5. 扩展根据后缀过滤候选：大小写不敏感，按完整文件名匹配注册后缀，支持 `.foo.bin`；后缀必须以点开头。空列表表示仅可手动选择。
6. 唯一候选直接运行；多个候选弹出 Quick Pick，不自动让用户 renderer 覆盖 built-in。无候选时提供“选择其他 Renderer”，以及 `.datapeek` 示例入口。
7. render 子进程只加载选中模块（或选中 built-in），按相同 ID 查找函数；模块在 discovery 后改变则重新发现，不使用旧函数假设。

缓存只保存 metadata；按 workspace、Python executable/版本和文件内容指纹区分。监视 `.datapeek` 变更后失效，下次 Preview 重新发现；配置或解释器改变同样失效。提供 Refresh Renderers，供安装新依赖或修改辅助模块后刷新。

执行目录为所属 workspace root；无 workspace 时为目标文件目录。runner 在导入自带 SDK 后添加 workspace root 和 `.datapeek` 到 Python 搜索路径，支持项目模块与辅助模块导入。v0.1 不提供自动 editable install 或 package 构建。

**导入 Python 模块会执行代码。** discovery 不是静态解析，也不是安全沙箱。Restricted Mode 中整个 Python 执行功能不可用：manifest 声明 `untrustedWorkspaces.supported: false`，命令执行前仍检查 trust。见 [Workspace Trust 指南](https://code.visualstudio.com/api/extension-guides/workspace-trust)。

未来 `probe` 不属于 v0.1 API，但保留独立选择阶段：后缀预筛选 → 在 Python 中执行有超时的 probe → `score/reason` → 用户选择。容器格式允许多个 renderer 返回适配结果；probe 不应全量读取文件，也不因异常阻断其他候选。引入时另行定义上下文、I/O 建议预算和兼容规则，不先发布空壳参数。

## 4. Python 环境选择

以目标 URI 为资源作用域，每个 workspace folder 独立解析：

1. `datapeek.pythonPath` 显式指定可执行文件。允许绝对路径或 `${workspaceFolder}` 前缀，不接受 shell 命令、参数串或任意变量展开。
2. 若安装 Microsoft Python 扩展，使用其公开 environments API 获取当前资源的 active environment，再 resolve 为 executable。
3. 未获得解释器时，检测 workspace `.venv` 的平台默认 executable。
4. 最后检测 extension host 的 PATH 中 `python3` / `python`，验证版本与可执行性。

显式配置存在但无效时直接报错；已选 Python 环境无法解析时提示选择，不能悄悄回退到别的环境。仅“没有选择”时进入后续默认发现。提供 `DataPeek: Select Python Interpreter`，允许浏览 host 文件系统，选择结果保存为 workspace-folder 配置。

在输出面板和预览状态中显示 host、解释器绝对路径、版本、renderer。用 `spawn(executable, args, { shell: false })`，继承 extension host 环境并设置 `MPLBACKEND=Agg` 和 UTF-8 输出；路径始终作为参数，不拼接 shell。

通过明确 bundle 路径启动 runner，引导加载 SDK，不能从 workspace 中误导入同名 `datapeek`。科学库按选定解释器的环境加载；不全局注入 SDK，不修改用户 site-packages。

v0.1 直接调用环境 executable，不执行 `conda activate` 或用户 shell 启动脚本。依赖额外激活变量的环境须通过 host 环境配置，UI 明确诊断；完整环境激活支持留待后续。Microsoft Python 扩展属于可选集成，不是启动必需依赖。

探测 `sys.executable` / 版本不导入 numpy；运行需要哪个库才检查哪个库。缺库错误指出当前解释器及缺少模块，提供可复制安装命令，不自动联网安装。更换解释器取消旧任务并清空对应 discovery 缓存。

API 参考：[Python Environment APIs](https://github.com/microsoft/vscode-python/wiki/Python-Environment-APIs)。实现中将该 API 包装成独立 provider，并测试扩展未安装及 API 不可用的情况。

## 5. 执行与通信

采用**每次操作一个短生命周期 Python 进程 + 文件协议**。v0.1 不做常驻 daemon；冷启动开销换取模块重载、环境切换与失败隔离的简单性。

每个 request 在 host 的私有临时目录创建独立随机子目录，生命周期归扩展管理：

```text
request.json         # TS 写入
response.json        # Python 成功完成后原子提交
artifacts/
    figure.png       # 或 figure.html / plotly.min.js 等
```

调用：`<python> <bundled-runner.py> --request <absolute-request-json>`。

stdout / stderr 都作为日志持续排空，保留有界尾部（各 1 MiB），不作为协议通道。这样用户 `print()`、第三方库日志和 native 输出不会破坏协议。traceback 写入错误响应及 Output Channel，不注入 Webview HTML。

render 请求示例：

```json
{
  "protocolVersion": 1,
  "requestId": "unique-request-id",
  "operation": "render",
  "workspaceRoot": "/remote/project",
  "targetPath": "/remote/project/data/sample.npy",
  "rendererId": "builtin:npy",
  "options": { "backend": "matplotlib" },
  "limits": { "maxArtifactBytes": 33554432 }
}
```

`operation` 为 `discover` 或 `render`；discover 不含目标与 renderer。输出固定在 request 所在目录，不能由用户 options 重定向。

```json
{
  "protocolVersion": 1,
  "requestId": "unique-request-id",
  "status": "ok",
  "artifact": {
    "kind": "image",
    "entry": "artifacts/figure.png",
    "mimeType": "image/png",
    "files": ["artifacts/figure.png"]
  },
  "metadata": { "shape": [2048, 4096], "sampledShape": [1024, 2048] },
  "warnings": ["Preview subsampled for display"]
}
```

interactive artifact 使用 `kind: "html"`、`mimeType: "text/html"`，列出全部资源。discover 成功响应使用 `renderers` 与 `diagnostics`，不含 artifact。失败响应使用 `status: "error"` 和 `error: {code, message, traceback?}`。

错误码包括 `PYTHON_NOT_FOUND`、`DEPENDENCY_MISSING`、`DISCOVERY_FAILED`、`RENDERER_NOT_FOUND`、`UNSUPPORTED_DATA`、`UNSUPPORTED_RESULT`、`OUTPUT_TOO_LARGE`、`TIMEOUT`、`CANCELLED`、`PROTOCOL_ERROR`。进程级错误可由 TS 生成，无需等待 Python 响应。

先写全部 artifacts，再写临时 response，最后同文件系统原子 rename 为 `response.json`。TS 等待进程成功退出并验证版本、requestId、结构、文件类型与真实路径；拒绝 `..`、绝对 artifact 路径、符号链接逃逸、未列出的资源和超额输出。response 最大 1 MiB，artifacts 默认合计 32 MiB。失败不显示半成品。

默认 discovery 超时 15 秒、render 超时 60 秒，可配置；单 workspace 最多两个 Python 子进程，余下排队。每 panel 的新请求取消前一个，用 requestId 防止晚到结果覆盖新结果。关闭 panel 或切换环境同样取消。POSIX 以独立进程组启动并终止进程组；Windows 实现进程树终止，先宽限 2 秒再强制终止。

清理在进程结束且 Webview 不再引用结果后进行。更新图先保留旧结果，成功替换后再清理。panel 关闭、扩展 deactivate 时清理；下次启动清理该扩展创建且超过 24 小时的孤立目录。输出体积限制不等于内存沙箱：自定义 renderer 的内存与 I/O 由其作者控制，v0.1 不保证对任意 Python 程序硬隔离。

## 6. 输出适配与 Webview

### matplotlib

Python 使用 Agg backend，将返回的 Figure 保存为 PNG（默认 150 DPI），在 finally 中释放 Figure。Webview 只显示图片、渲染状态与元信息；无需 Python GUI、X11 或 DISPLAY。

### Python Plotly

Python 调用 `plotly.io.to_html` 生成离线完整 HTML，包含当前 Python Plotly 配套的 Plotly.js，禁用 MathJax CDN。缩放、平移、hover 等由生成结果提供，不回调 Python。

Python 输出适配器使用 HTML parser 提取生成文档中的脚本为本地资源，保留原顺序，将资源引用改为 artifact 标记；不以正则猜测脚本边界。TS 只把这些已声明的资源标记转换为 `webview.asWebviewUri` 并注入容器 CSP，不创建 Plotly traces 或调用 `Plotly.newPlot`。需专门验证 `</script>` 等数据文本不会破坏导出。

v0.1 仅支持受控 Plotly Figure 导出。地图瓦片、外部图像、CDN 和依赖 Dash/Bokeh server 的回调不在离线保证范围内。未来可增加明确的 `HtmlArtifact` 与其他 Python 适配器；不能承诺任意库生成的 HTML 原样可用。

参考：[Plotly HTML 导出](https://plotly.com/python/interactive-html-export/) 与 [to_html API](https://plotly.com/python-api-reference/generated/plotly.io.to_html.html)。

### 资源与边界

- artifacts 的 host 路径转换为 VS Code URI，再调用 `asWebviewUri`；Remote SSH URI 保留正确的 scheme/authority，不把远端路径当作本机路径。
- `localResourceRoots` 只包含当前 panel 的产物目录及必要扩展资源，不开放 workspace。
- 图片模式 `enableScripts: false`；交互模式启用脚本。CSP 从 `default-src 'none'` 开始，仅允许声明的本地 scripts、图片、字体和必要 styles；Plotly 样式可能需要 inline style，禁止 inline script、eval 和外部 connect。
- 交互页面不暴露 host RPC，不注入可用于执行命令的 message handler。标题、路径、错误等 UI 文本转义；拒绝 artifact 的外部资源加载。
- PNG 和 Plotly 页面不要求 Python 进程继续存在。刷新或换参数会重新启动 Python；隐藏/恢复 panel 可从保留的 artifact 重建。

Webview 资源访问与 CSP 遵循 [VS Code Webview 指南](https://code.visualstudio.com/api/extension-guides/webview)。Plotly 与 CSP 的兼容性是实现第一阶段必须验证的技术风险，不能仅凭浏览器直接打开 HTML 视为通过。

## 7. 内置 `.npy` renderer

`builtin:npy` 使用 `numpy.load(path, mmap_mode="r", allow_pickle=False)`，在 Python 侧完成以下逻辑：

| 输入 | 默认 matplotlib | 可选 Python Plotly |
| --- | --- | --- |
| 1D 实数/整数/bool | line，x 为原始索引 | SVG Scatter line（兼容无 WebGL 环境） |
| 2D 实数/整数/bool | imshow + colorbar | Heatmap |
| scalar、空数组、3D+、complex、object、structured、字符串 | 明确不支持的说明 | 同左 |

为保证首次预览开销可控，内置 renderer 在读入绘图数据前按索引均匀抽样：1D 最多 20,000 点，2D 每轴最多 1,024 点，Plotly 2D 每轴最多 512 点。采样保留首尾坐标，图中坐标对应原数组索引，展示原始 shape、dtype、采样 shape 和抽样提示。不做全量 min/max 扫描；默认色阶从预览样本计算。NaN/Inf 在 Python 中转为 masked/缺失值。

抽样可能漏掉窄脉冲；UI 明确称为 sampled preview，不用它替代科学分析。领域专用 renderer 可以自行实现 envelope、切片或滤波。文件读取期间若修改，返回可重试诊断；v0.1 不承诺文件快照一致性。

内置 `backend` 支持 `matplotlib`（默认）和 `plotly`；可调 cmap、标题及采样上限，但不能越过框架硬上限。缺 Plotly 时报缺库提示，不默默换成静态图。

NumPy 的 mmap 和禁用 pickle 行为参考 [numpy.load](https://numpy.org/doc/stable/reference/generated/numpy.load.html)。

## 8. v0.1 命令与配置

命令：`DataPeek: Preview with DataPeek`（Explorer 右键、编辑器标题、命令面板）、`DataPeek: Select Python Interpreter`、`DataPeek: Refresh Renderers`。无传入 URI 时使用活动编辑器，仍无目标时选择文件；目录不触发预览。未知后缀也提供入口，以便选择自定义 renderer。

配置初始集合：

| 配置 | 默认值 | 作用 |
| --- | --- | --- |
| `datapeek.pythonPath` | unset | 当前资源的 host Python executable |
| `datapeek.rendererOptions` | `{}` | 按 renderer ID 传 JSON options |
| `datapeek.renderTimeoutSeconds` | `60` | 渲染超时 |
| `datapeek.discoveryTimeoutSeconds` | `15` | 发现超时 |
| `datapeek.maxArtifactMiB` | `32` | 可视化总输出上限 |

数值配置必须有限、正值且有合理上界；以实现 schema 为准。配置读取使用目标 URI，不用全局单例解释器。初版不增加自动安装、复杂参数表单、renderer marketplace、持久结果缓存或后台文件自动重绘。
