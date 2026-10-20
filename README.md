# APP 图片生成 · KIE API 独立版

将已确认的 APP 图片文案，经配置卡、KIE GPT Image 2.5 Sunburst 1K 生成、候选选择和本地规格处理，转成采纳图片。保留原版Logo、IP和字体参考，当前仅启用用户在投表的8个渠道、19个版位组合；旧102版位停用归档。直接调用KIE API。

当前锁定 `gpt-image-2-5-sunburst-image-to-image` 和 `1K`，至少需要一张原版参考图，不自动升级分辨率或更换入口。预算按用户账号截图的3积分/张估算，实际扣费以账号区域报价为准。比例差距大时生成后重点确认，详细结果见[尺寸比例适配报告](references/model-size-compatibility.md)。

预计常规裁切达到6%的版位使用[白底蓝框生成、OpenCV去框后拉伸](references/blue-frame-adaptation.md)，低于门槛沿用常规适配。去框预览与生成原图分别保存，用户采纳后再按渠道KB上限正式交付。

画面按[艺术定调层级](references/art-direction.md)设计：画风→世界与场景→故事→构图→光色材质，再编译成逐张提示词。批量默认按套随机主画风并优先不重复，单图逐张独立设计，同套双/三图风格一致；场景、构图和配色仍整体协调，不独立随机拼接。用户指定画风时优先遵从指定。

## 使用

将整个仓库作为一个 Skill 文件夹安装，保留文件名 `onion-app-image-kie`。支持 Skill 的 Agent 从根目录 [SKILL.md](SKILL.md) 读取流程。直接向 Agent 提出：

> 使用 onion-app-image-kie，按我已确认的文案打开配置卡，生成 APP 图片候选，并按我的选择交付。

首次配置需要 Python 3.10+ 和 KIE API Key。在本地创建虚拟环境并安装依赖：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Windows 使用 `.venv\Scripts\python.exe`。运行脚本时使用安装了依赖的 Python。

在本机 `~/.config/onion-app-image-kie/.env` 中配置 `KIE_API_KEY`，或通过同名进程环境变量提供。不要将真实 Key 放入仓库或聊天。配置详情和任务恢复方式见 [KIE API 合同](references/provider-contract.md)。

运行工作目录由 `ONION_IMAGE_WORKSPACE` 指定，未设置时使用当前目录。图片和任务写入该目录的 `工作区/产物/`；Skill 安装位置与工作目录可以不同。产品事实由用户提供当前确认的资料；仓库携带品牌图片，不包含完整的价格、权益或渠道时效资料。

## 验证

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests -q
```

自动测试使用本地样例与模拟API，不发起真实付费生图；当前187项测试通过，包含分层艺术定调、正向一段式Prompt、七类视觉约束逐张传入与缺失拦截、文案元数据校验、无IP自由主体、清晰示意UI、批量随机主画风、同套继承、独立提示词、完整画面方案与逐张动作绑定、模型锁定、6%阈值边界、单张入口蓝框校验、多重蓝框拒绝、分支付费前预检、损坏任务状态拦截和明确平台过滤。已完成一次真实KIE候选生成验证：OPPO横版三图2套，共6张，同套分支引用首张PNG；下载中断后复用原任务恢复，未新建生图任务。该批候选尚未完成用户采纳与正式JPEG交付，不视为完整端到端验收。正式使用前仍需配置有效Key，并确认本次参考图上传和生图数量。

## 来源与维护

由 `content-automation` 中的 APP 图片 Skill 独立适配而来。本仓库维护 KIE API 变体，原 MCP 版本保持原有维护位置。

关联任务：[content-automation#119](https://github.com/luoxia723/content-automation/issues/119)。仓库包含洋葱品牌参考资产；这些品牌资产不因源码公开而获得额外使用授权。

每张均有学生或选定IP参与具体学习场景，无IP方案使用普通原创学生；带IP允许少量画风或时代元素融入服装与配饰，保留主要识别特征。场景可探索古代、中世纪、现代与幻想设定。屏幕可显示清晰示意UI，无需强制模糊；只有要还原实际界面时才需要真实截图。

新任务提示词使用一段正向自然语言：直接描述画面、动作、确认文案和必要素材用途。画面文字白名单、负面提示段与内部制作编号不进入Prompt；模型、尺寸、压缩、素材绑定和任务依赖由配置与代码处理。参见[Prompt规则](references/prompt-rules.md)和[示例](references/prompt-examples.md)。
