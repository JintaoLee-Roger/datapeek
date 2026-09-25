# 开发与测试

[English](implementation-plan.md) | 简体中文

## 构建

在仓库根目录执行：

```sh
npm ci
python3 -m pip install -r python/requirements.txt
npm run compile
```

按需安装格式和查看器依赖：`h5py`、`zarr`、`seisvol`、`cigvis` 及其查看器依赖。选择 **Run DataPeek** 后按 F5 启动扩展开发窗口。

## 测试

```sh
npm test
npm run test:extension
```

Python 测试覆盖读取器、采样、色阶、缓存和自定义示例；Node 测试覆盖文件关联与前端色阶逻辑。浏览器检查及平台边界见[验证覆盖](validation.zh-CN.md)。

`tests/manual/` 下的集成脚本需要 Playwright、Chromium、系统运行库及测试夹具引用的数据。运行前请检查路径：

- `detail_fixture.cjs` + `browser_detail.py`：生成并验证详细查看和内嵌 3D 页面。
- `canvas_fixture.cjs` + `browser_quick.py`：生成并验证快速预览页面，包括像素值。
- `worker_lifecycle.py`：验证服务启停、重启及进程退出清理。

`tests/smoke_real_data.py` 和 `tests/smoke_detail.py` 使用外部样本数据。基准脚本同样引用外部数据，需按环境修改路径。测量方法见[性能说明](quick-preview-performance.zh-CN.md)。

## 打包

```sh
npm run package
```

VSIX 版本来自 `package.json`。通过 **Extensions: Install from VSIX...** 安装生成的文件，再执行 **Developer: Reload Window** 并重新打开预览。

要向其他人分享，先完成上述打包，再运行：

```sh
python scripts/build_share_bundle.py
```

生成的 `build/datapeek-0.0.1-share.zip` 包含 VSIX、中英文文档、预览截图和示例脚本。收件人从 `README.zh-CN.md` 开始即可，不需要源码构建环境。分享包不包含 Python 环境或依赖安装包。

## 文档维护

文档、界面文本和代码注释默认使用英文。每份 Markdown 文档都有 `.zh-CN.md` 对应版本，行为变化时同步更新；两种版本的代码示例均使用英文注释，基准 JSON 共用。

README 聚焦安装和常用操作；读取器接口放在[自定义读取器](custom-readers.zh-CN.md)，维护细节放在[架构说明](architecture.zh-CN.md)，测量结果连同方法放在性能文档。记录可复现的行为，不记录个人安装状态或会话过程。
