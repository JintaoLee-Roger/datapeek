# v0.1 实现计划与验收

此文件保留最初的分阶段计划。本地基础版已交付，实际完成情况参见 README.md 与 validation.md；Remote SSH 验收等仍为后续任务。

## 推荐目录

```text
src/
  extension.ts
  commands/preview.ts
  python/environment.ts
  python/process.ts
  python/protocol.ts
  renderers/discovery.ts
  webview/panel.ts
python/
  runner.py
  datapeek/
    __init__.py
    registry.py
    discovery.py
    protocol.py
    execution.py
    adapters/matplotlib.py
    adapters/plotly.py
    builtins/npy.py
examples/
  custom-renderer/.datapeek/das.py
tests/
  python/
  extension/
docs/
```

## 阶段 1：验证高风险路径

- 创建 VS Code extension skeleton 与 bundled Python runner。
- 用独立环境返回一个 matplotlib Figure 和一个 Python Plotly Figure。
- 验证本地及实际 Remote SSH 中 Python 路径、产物 URI、CSP、离线 hover/zoom 和资源清理。
- 生成 HTML 必须经过最终 Webview 路径验证；若 Plotly 需要 CSP 调整，应明确到具体资源/样式要求，不能直接放开所有脚本来源。

验收：两种图均可见、交互图可离线操作，日志证明 Python 在目标 host 执行，网络中不出现原始 `.npy` 传输。

## 阶段 2：稳定 Python 契约

- 实现注册 API、模块事务发现、稳定 ID、延迟依赖加载与两种输出适配器。
- 实现 request/response schema、原子响应提交与错误码。
- Python 测试覆盖重复 ID、模块导入失败隔离、任意 print/native 日志、未知返回类型、缺库、PNG 输出和 Plotly 导出资源。

验收：项目添加 `.datapeek/foo.py` 即可发现并渲染；一个坏模块不影响其他可用 renderer。discovery 超时应可诊断且不影响 built-in-only 重试。

## 阶段 3：VS Code 编排与生命周期

- 环境 provider、multi-root 资源作用域、候选选择、配置与 Output Channel。
- 进程超时、取消、排队、panel dispose、陈旧结果丢弃、artifact 清理。
- TS 测试覆盖 Python provider 缺失、无效显式路径、带空格/Unicode 路径、协议畸形、路径逃逸、超限输出、取消竞争与远端 URI。
- 集成测试验证 Restricted Mode 中不能执行 discovery 或 render。

验收：快速连续预览只显示最新结果；关闭 panel 不留活跃 Python 子进程；旧图在替换失败时仍可见；每个 workspace 使用自己的解释器与 renderer。

## 阶段 4：内置 NumPy 与交付

- `.npy` mmap、类型/维数校验、Python 抽样、matplotlib line/image、Plotly 可选输出。
- 使用小型确定性 fixtures 验证轴索引、形状与缺失值。使用单独大文件 smoke case 确认预览不完整载入/传输数组；不把大型 fixture 放入仓库。
- 编写安装与环境说明、自定义 renderer 教程、Remote SSH 操作说明与限制。
- VSIX 包含 runner/SDK/必要资源，排除缓存和测试产物；不捆绑 Python interpreter 或科学计算依赖。

## 最终手工验收矩阵

| 场景 | 必须观察到的结果 |
| --- | --- |
| 本地 Linux/macOS/Windows，1D/2D `.npy` | line/image 正确，路径与 dtype/shape 可辨认 |
| Linux Remote SSH，无 DISPLAY | 远端 Agg 正常输出，本地 Webview 显示 |
| Python Plotly、离线网络 | hover/zoom 正常，无 CDN 依赖 |
| 未知后缀 + 用户 renderer | 右键可预览，无需修改扩展 |
| `.h5` 上多个注册候选 | 用户可选择，未实现 probe 不伪装为已自动识别 |
| 缺少 numpy/matplotlib/plotly/用户依赖 | 指出当前环境及缺库，日志可定位 |
| untrusted workspace | 无 Python 代码被执行，包括 discovery |
| 大型 2D 数组 | 明确标记抽样，仅传输受限 visualization |
| renderer timeout/崩溃/取消 | UI 恢复，可再次渲染，临时产物清理 |
| multi-root + 两种 Python 环境 | 无跨 folder renderer 或环境污染 |
| 标题/标签含 Unicode、HTML、`</script>` | 正确显示或安全转义，导出不损坏 |

真实 Remote SSH 验收必须记录 remote host、Python 版本、VS Code 版本和结果；若环境不可用，标记未验证，不能用本地测试替代远端支持声明。

## 后续版本

先根据实际使用反馈增加 `.npz` 变量选择、HDF5 dataset browser、probe、3D+ 切片、SEG-Y，再考虑常驻 worker、Python 回调交互、其他 HTML adapters。保持 renderer API 与 artifact protocol 分离，避免为新数据格式修改 TypeScript 绘图逻辑。
