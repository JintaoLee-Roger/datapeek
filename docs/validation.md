# 本地基础版验证记录

日期：2026-09-18。

环境：macOS arm64；VS Code 1.138.0；Node 25.2.1；Python 3.13.13；NumPy 2.4.4；matplotlib 3.10.9；Plotly 6.7.0。

## 自动化

- TypeScript strict 编译通过。
- Python unittest：9 项测试通过。覆盖 PNG line/image/bool、Plotly line/heatmap、离线脚本拆分与特殊字符标题、不支持数组、用户模块发现与失败回滚、日志隔离、缺失依赖、返回值校验、输出体积上限、协议版本和抽样边界。
- 测试请求目录包含空格与中文；通过实际 Python 子进程执行 runner。

## VS Code 实机

通过 `--extensionDevelopmentPath` 启动本仓库，以 `examples` 为 workspace：

- Explorer 中出现 Preview with DataPeek。
- 命令面板启动文件选择器并创建 DataPeek Webview。
- 默认 Python 环境缺少 NumPy 时，UI 显示缺库诊断和实际解释器路径。
- 为示例 workspace 显式选择已有科学计算环境后，`signal.npy` 的 matplotlib PNG 在 Webview 正常显示。
- Python Plotly 离线输出在同一 Webview 正常显示。点击 Zoom in 后横轴范围和纵轴刻度改变，确认交互脚本执行正常。
- 初始 Scattergl 在该 Webview 显示 WebGL 不支持；内置 renderer 已改用 SVG Scatter 并重新验证。

## 未验证

Remote SSH、Windows、Linux、Restricted Mode 的实机流程，以及完整生命周期/进程树的跨平台集成测试尚未完成。二维图与自定义 renderer 已通过 Python 子进程测试，尚未逐项进行 VS Code GUI 验收。自定义 Plotly renderer 使用 WebGL traces 时仍取决于 Webview 的 GPU 支持。
