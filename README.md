# 洋葱广告图本机工作台

将已确认文案制作成多渠道广告图片，支持单图、双图和三图，提供画面规划、KIE生图、逐张提示词编辑、挑选与本机交付。

## 启动

- Mac：双击 `启动.command`。
- Windows：双击 `启动.bat`。
- 命令行：`python bootstrap.py`，或使用已安装依赖的 `.venv/bin/python run.py`。

首次启动需要Python 3.10–3.14，启动器准备本项目的虚拟环境。设置里填写规划API Key和KIE Key，可选择GPT Image 2或GPT Image 2.5 Sunburst，均为1K。具体见[本机工作台说明](本机工作台说明.md)。运行工作台不需要Node.js、Codex或测试依赖。

## 工作流

配置与草稿 → 规划与生成队列 → 本机图片处理 → 预览挑选 → 保存图包。多个窗口共享同一个后台；同套首图完成后，第二、三张引用本套首图PNG。人工编辑以用户内容为准，原文与参考顺序按图片版本记录。

当前规格由 `config/channel-placement-rules.json` 提供：8个渠道、19个尺寸与形式组合。素材分配、模型、文案和规划按轮次冻结；并发固定 20。蓝框由OpenCV识别并去掉框线、框外白边，成品使用JPEG/RGB并检查精确尺寸、KB和哈希。

历史、任务、回执与图片版本由SQLite和本地文件保存。已有目录和图包继续有效；归档、清理与删除分别管理，历史不自动过期。导出使用当前采纳版本的成品JPEG，旧ZIP保持不变。

## 当前代码入口

- `bootstrap.py`、`run.py`：启动同一个本机工作台。
- `frontend/`：本机网页。
- `local_app/`：任务、队列、规划API、KIE执行、历史与交付。
- `scripts/`：工作台使用的共享规划、HTTP、图片处理与资产函数，以及源码打包、测试辅助工具。
- [SKILL.md](SKILL.md)：供规划模型或Agent读取的画面设计方法，不再启动另一套配置卡或批处理流程。

旧配置卡、旧候选选择页、旧批量执行与旧交付打包入口已经移除。当前任务恢复不依赖这些入口；KIE回执解析与请求指纹保护继续保留。

## 开发检查

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/check_workbench.py
.venv/bin/python scripts/check_workbench.py --suite transport
.venv/bin/python scripts/check_workbench.py --suite history
```

默认检查当前工作台、共享核心与前端。`transport` 在本机HTTP模拟服务中完整走上传、创建、查询、下载与恢复，覆盖两种1K模型。`history` 检查保留的历史格式，不是运行旧入口。`--collect` 可先查看范围，数量以实际收集结果为准。

自动测试只连接本机回环服务，不产生生图用量。真实API验证按明确的最少图片范围另外执行并保留回执；离线测试不能代表外部服务可用性或视觉效果。

## 使用与维护资料

- [工作台行为](references/workbench-behavior.md)
- [整体优化方案](references/workbench-optimization-plan.md)
- [KIE请求与恢复](references/provider-contract.md)
- [原始规格快照](config/current-channel-source.json)

项目由原APP图片Skill适配而来，保留其品牌素材、画面方法和有效渠道规格。品牌资产不因源码分享而获得额外使用授权。
