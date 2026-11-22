# 洋葱广告图工作台

在本机浏览器中制作多渠道广告图：填写文案、选择 IP／画风和版位，由模型规划与生图，再按渠道要求处理尺寸、Logo 和图包。支持普通单图／双图／三图、学习机整套，以及已有图片的多尺寸适配。

**下载源码 → 双击启动 → 填写自己的两项 API Key，即可使用。** 无需 Node.js、Codex、数据库服务器或前端构建。运行依赖只有 Pillow，首次启动会自动安装。

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

保存 KIE Key 后，普通任务会启用真实生图；学习机创建时仍需选择“真实制作”。保存设置不会提交图片。**规划“测试连接”会调用一次语言模型；图片“测试连接”查询 KIE 余额。**

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

### 学习机整套

**一句文案 → 画面设定 → 选择版位 → 生成基准图 → 查看并确认 → 扩展整套 → 保存图包。**

- 基准图是 16:9 视觉参考，确认前不会扩展整套；不满意可先重出基准图。
- 默认全选 44 个版位，交付 45 张图；同一内容和画幅尽量复用母版，不逐尺寸重复生成。
- 正文、CTA、Logo 有无按版位固定；CTA 可自定义，默认“点击下载”。IP、画风和参考图每套确定一次。
- Logo 模板可调整黑／白款式、位置和大小；尺寸、指定底灰遮罩、Logo、圆角由代码完成。
- 成品按百度、作业帮等渠道分组；点击图片可以查看、复制该版本实际执行的提示词。
- ZIP 内部按 **渠道 → 版位与尺寸 → 图片** 分目录，根目录保留交付清单。

预览会显示本次预计模型调用数；条件背景扩展和主动重出会增加调用。学习机“本机演练”全程离线，适合先熟悉界面。

### 多尺寸适配与重试

已有普通图片／完整套图、学习机已确认基准或成品，可以选择“制作多尺寸母版”。先查看分组与裁切计划，再启动每组图生图，从完整自然画布导出多个固定尺寸。

“重出本图”“再次调整背景”“恢复查询”和本机导出重试直接显示在对应图片或进度中。按钮说明影响单图、后续图还是整组；旧版本和图包保留。供应商状态不明时先查询原任务，避免重复付费提交。

### Logo 与导出

Logo 模板包含应用商店、信息流和学习机，支持渠道筛选、版位翻页和拖动配置。新图保留无 Logo 底图，导出时可切换黑字标准版或白字 APP 版，换 Logo 不调用图片模型；固定无 Logo 的学习机版位保持无 Logo。

任务列表和交付记录支持搜索、筛选与翻页。图片按真实宽高比显示，可查看原图、成品、版本与处理记录。完整操作见[本机工作台说明](本机工作台说明.md)。

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
- 学习机 PNG 优先无损编码。全彩仍超限时尝试不同调色板，选符合大小限制、最接近原画面的候选。无法同时满足要求时提示处理，交付像素不变。图片详情记录实际体积和是否减色。
- 图片模型当前执行 1K 请求，后处理输出对应版位精确像素；导出像素大于原生图片不代表新增了同等细节。
- 普通任务的“模拟预览”只替代图片生成，**画面规划仍调用模型**；只有学习机“本机演练”全程离线。
- 网页可关闭后再回来，生成期间请保持启动窗口和本机服务运行。

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
