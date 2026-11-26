# 洋葱广告图工作台

在本机浏览器中制作多渠道广告图。支持普通单图、双图、三图，学习机整套制作、上传概念图扩版，以及已有图片的多尺寸适配。

**下载源码 → 双击启动 → 填写自己的两项 API Key，即可使用。** 无需 Node.js、Codex、数据库服务器或前端构建。运行依赖只有 Pillow，首次启动会自动安装。

[下载安装](#下载安装) · [使用流程](#怎么使用) · [目录导航](#目录导航) · [本机数据](#配置与本机数据) · [测试与发布](#开发与检查)

## 下载安装

需要 **64 位 Python 3.10–3.14**，建议使用 Python 3.12 或 3.13。支持 macOS 和 Windows 10／11；Python 可从 [python.org](https://www.python.org/downloads/) 安装。Windows 安装时勾选 **Add Python to PATH**。

1. 从 [GitHub 仓库](https://github.com/luoxia723/onion-app-image-kie)克隆项目到本机可写目录。
2. macOS 双击 **`启动.command`**；Windows 双击 **`启动.bat`**。
3. 首次启动自动创建项目自己的 `.venv` 并联网安装依赖，随后打开 [本机工作台](http://127.0.0.1:8765)。以后直接双击启动即可。
4. 进入左侧 **模型与设置**，配置下面两项服务并保存。

| 设置分类 | 填写内容 | 默认服务 |
| --- | --- | --- |
| 画面规划 | 内部规划网关 Key | `https://ops-ai-gateway.yc345.tv/v1`，模型 `gpt-6.1-terra` |
| 图片生成 | 自己的 KIE API Key | KIE 图片生成与参考图上传接口 |

默认地址、模型和上传接口沿用内部现有工作台：规划模型为 `gpt-6.1-terra`，图片模型为 `GPT Image 2.6 Flare`，图片请求为 1K。内部使用只需填写自己的 Key；已有本机配置继续优先。需要改用其他兼容服务时，可以在设置中调整接口和模型。

规划 Key 请向内部网关维护者获取；图片 Key 使用自己的 [KIE](https://kie.ai/) 账户。两项 Key 分别使用，需要对应服务有可用额度与模型权限。公开仓库不提供或共享任何人的 Key。

保存 KIE Key 后，普通任务会启用真实生图。学习机新任务在配置两项 Key 后使用正式制作。保存设置不会提交图片。**规划“测试连接”会调用一次语言模型，图片“测试连接”查询 KIE 余额。**

也可用命令行启动：

```sh
git clone https://github.com/luoxia723/onion-app-image-kie.git
cd onion-app-image-kie
python3 bootstrap.py
```

Windows 对应 `py -3 bootstrap.py` 或 `python bootstrap.py`。Mac 如提示启动文件没有执行权限，可在项目目录运行 `chmod +x 启动.command`。首次安装需要联网；不要复制其他人的 `.venv` 或 `.env`。

## 怎么使用

### 普通广告

新建任务，选择应用商店或信息流、图片形式、文案、画面设定和版位，再开始生成。双图／三图先生成首张，后续张引用本套首图保持一致。生成后按版位挑选、查看实际提示词，保存所选图包。

每张先生成完整自然画布，再由代码按冻结的安全范围裁成精确像素；Logo 独立叠加。当前流程已移除蓝框参考、识别和去框。普通广告交付 JPEG／RGB，保留模型原始 PNG。

在「新建任务 → 信息流 → 投放版位」勾选「喜马拉雅套图」，默认选五个尺寸，可逐个取消。可以同时选择微博粉丝通和 CPA，也可以一键全选信息流版位。喜马拉雅以已选尺寸中的第一张作为首图，Luna 审核后继续生成其余已选尺寸。每张 JPEG 严格小于 150 KB，验收后可单独导出喜马拉雅套图，也可和其他信息流成品一起保存。

### 学习机整套

**一句文案 → 画面设定 → 选择版位 → 生成基准图 → 查看并确认 → 扩展整套 → 保存图包。**

- 基准图是 16:9 视觉参考，确认前不会扩展整套；不满意可先重出基准图。
- 「新建任务 → 学习机 → 上传概念图」支持点击选择或拖入已有横向 16:9 有字图。填写图上正文和按钮，预览原图适配、GPT 扩背景、重排和去字，再确认源图并扩套。上传框提示使用不带 Logo 的图。
- 学习机从已有画面去正文或按钮时会重新构图。构图审核未通过时可在母版详情重新构图本组。
- 真实制作中，Luna 逐张审核有字母版。疑似错字会放大该字和相邻文字独立复核，确认有文字缺陷才由 Nano Banana 修复。修复图通过 Luna 后再扩版。可从「制作进度 → 复核文字」查看原图和局部读数。
- 默认全选 44 个版位，交付 45 张图；同一内容和画幅尽量复用母版，不逐尺寸重复生成。
- 正文、CTA、Logo 有无按版位固定；CTA 可自定义，默认“点击下载”。IP、画风和参考图每套确定一次。
- Logo 模板可调整位置和大小。尺寸、指定底灰遮罩、Logo 自动选色和圆角由代码完成。
- 成品按百度、作业帮等渠道分组；点击图片可以查看、复制该版本实际执行的提示词。
- ZIP 内部按 **渠道 → 版位与尺寸 → 图片** 分目录，根目录保留交付清单。

离线预览会显示本次预计模型调用数。生成基准图和确认扩套是分开的操作，条件背景扩展和主动重出会增加调用。

### 多尺寸适配与重试

已有普通图片／完整套图、学习机已确认基准或成品，可以选择“制作多尺寸母版”。先查看分组与裁切计划，再启动每组图生图，从完整自然画布导出多个固定尺寸。

“重出本图”“再次调整背景”“恢复查询”和本机导出重试直接显示在对应图片或进度中。按钮说明影响单图、后续图还是整组；旧版本和图包保留。供应商状态不明时先查询原任务，避免重复付费提交。

KIE 已受理的任务超时会自动续查。出现「等待回执核对」时，到 KIE 任务记录复制任务号，选择「接回任务」。确认原请求未受理后可手动重出。本机回执缺失或损坏时，按页面提示核对记录或恢复备份。

### Logo 与导出

Logo 模板包含应用商店、信息流和学习机，支持渠道筛选、版位翻页和拖动配置。普通任务只选择是否添加 Logo，学习机按版位确定有无。代码自动初选黑字或反白。验收时，有独立 Logo 图层的成品可一键切换款式，新图包使用验收预览上的款式。

用户提供的黑字和反白原图在 [assets/logos/](assets/logos/)。画面设定的 IP 选择器中，「新增角色」包含 27 张编号参考图。登记记录保存在[素材清单](assets/asset-manifest.json)。

任务列表和交付记录支持搜索、筛选与翻页。同版位候选可并排对照，横竖混合的套图从上往下浏览。点图在工作台内查看大图、原图、版本和处理记录，也可按 100% 检查细节。普通任务按套挑选。喜马拉雅、学习机和多尺寸适配可逐张勾选或全选，确认全部当前成品后导出整套。完整操作见[本机工作台说明](本机工作台说明.md)。

## 配置与本机数据

日常使用通过“模型与设置”配置即可，**不需要手工编辑文件**。高级用户可复制 [.env.example](.env.example) 为 `.env`；该示例所有 Key 均为空。直接用文件配置时，需按示例说明选择真实／模拟模式。

| 路径 | 内容 | 是否随源码上传 |
| --- | --- | --- |
| `.env` | 自己的 Key、接口、模型、保存位置 | 否 |
| `.onion-local/` | 本机任务、草稿、索引、上传与备份 | 否 |
| `<保存位置>/.cache/` | 模型回执、原图、提示词及图片版本 | 否 |
| `<保存位置>/工作区/` | 本机成品和图包 | 否 |
| `assets/`、`config/` | 内置 IP、字体、Logo、样图和渠道规则 | 是，属于运行所需素材 |

源码不包含个人 Key、任务数据库、上传文件、真实测试产物或本机图包。内置素材随项目提供，无需另找原作者的电脑路径或登录原始规格文档。真实制作会将提示词和选定参考素材发送至配置的模型服务；应用只监听本机 `127.0.0.1`。

备份／恢复在“数据维护”中操作。备份不包含 `.env`，请自行妥善保存 Key。升级前先做备份；Git 用户可拉取代码，ZIP 用户应先停止服务、备份本机数据，再替换源码。旧图片与图包不会因规则更新自动重画。

## 已知边界

- 精确宽高和文件大小由代码核验；人物、文字、道具是否完整仍需看图，不把尺寸通过当作视觉审核通过。
- 学习机 PNG 优先无损编码，全彩超限时按限制择优减色。可按需把 [pngquant](https://pngquant.org/)、[OxiPNG](https://github.com/oxipng/oxipng) 和[联合量化工具](tools/learning-png/README.md)加入本机 `PATH`，供应用比较更多达标候选。JPG 会按限额比较几种色度采样，优化编码失败时尝试标准编码。 [查看格式与画质规则](references/export-rules.md)
- 图片模型当前执行 1K 请求，后处理输出对应版位精确像素；导出像素大于原生图片不代表新增了同等细节。
- 普通任务的“模拟预览”只替代图片生成，**画面规划仍调用模型**。学习机通过「仅预览计划」离线查看配置。
- 网页可关闭后再回来，生成期间请保持启动窗口和本机服务运行。

## 目录导航

| 路径 | 内容 |
| --- | --- |
| [启动.command](启动.command)、[启动.bat](启动.bat)、[bootstrap.py](bootstrap.py)、[run.py](run.py) | 双击入口、依赖安装和本机服务启动 |
| [frontend/](frontend/) | 页面和交互从 [index.html](frontend/index.html) 加载 |
| [local_app/](local_app/) | [本机 API](local_app/server.py)、任务队列和[学习机制作流程](local_app/learning_runtime.py) |
| [scripts/](scripts/) | 检查与发布命令，以及正式运行使用的[图片请求](scripts/render.py)、[模型注册](scripts/kie_model.py)和[图像压缩](scripts/image_compress.py) |
| [config/](config/)、[assets/](assets/) | 现行版位、母版分组、图层规则和注册素材。旧版位归档在 `config/history/`，旧学习机工作流快照由兼容代码读取 |
| [tests_local/](tests_local/)、[tests_frontend/](tests_frontend/)、[tests/](tests/) | 后端、前端和共享脚本测试，运行范围见[测试说明](references/testing.md) |
| [references/](references/) | 技术架构、业务规则与研究记录 |
| [prototype/](prototype/) | 历史界面原型 |
| [tools/learning-png/](tools/learning-png/)、[skills/](skills/) | 可选 PNG 量化工具及画面规划指导 |

个人配置、任务索引、图片缓存和成品位置见[配置与本机数据](#配置与本机数据)。

## 开发与检查

技术栈为 Python 标准库 HTTP 服务、SQLite／本地文件和原生 JavaScript。运行依赖只需 Pillow；测试额外需要开发依赖和 Node.js 22+。

```sh
python3 bootstrap.py --install-only
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/check_workbench.py --suite all
.venv/bin/python scripts/build_workbench_bundle.py --check
```

Windows 将 `.venv/bin/python` 替换为 `.venv\Scripts\python.exe`。默认 `scripts/check_workbench.py` 检查当前行为；`--suite history`／`transport` 可定向检查，`--collect` 查看收集范围。自动测试阻断外部模型网络，仅使用临时目录和回环 HTTP 服务，不消耗生图额度。

GitHub Actions 执行 Windows／macOS 多 Python 版本的干净安装及离线验证，并执行完整 Python 和前端回归。打包源码可运行：

```sh
python3 scripts/build_workbench_bundle.py --output-dir /path/to/releases
```

打包前会检查凭据和本地数据排除规则，生成可分发的 ZIP／tar.gz。只发布源码和注册素材，任务、图片结果与备份保持在本机。

## 维护文档

- [AGENTS.md：开发协作约定](AGENTS.md)
- [技术架构](references/architecture.md)
- [测试分组与验证边界](references/testing.md)
- [源码发布与干净安装验收](references/releasing.md)
- [学习机配置](references/learning-machine-setup.md)与[提示词合同](references/learning-machine-prompts.md)
- [无框自然画布](references/natural-canvas.md)与[共用母版](references/shared-master-canvases.md)
- [Logo 图层](references/logo-layers.md)与[KIE 请求恢复](references/provider-contract.md)

项目包含品牌 IP、Logo 与参考素材；源码分享不改变这些资产原有的使用授权。
