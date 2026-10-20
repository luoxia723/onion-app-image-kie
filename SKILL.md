---
name: onion-app-image-kie
description: 当用户已经确认 APP 图片文案并要求生成信息流、应用商店或学习机正式图片时使用；打开本地配置卡，通过KIE API直连GPT Image 2.5 Sunburst 1K生成候选，完成品牌与UI门禁、规格处理、人工选择和采纳图片交付。不要用于撰写图片文案、修改已有广告图、线索九宫格或投放发布。
---

# APP 图片生成

> 独立适配版：保留原 APP 图片业务流程，供应商调用由本地 Python 直接访问 KIE API。配置使用 `KIE_API_KEY`，操作说明见供应商合同。

## 产物

把已确认图片文案转成可选择、可追溯的图片候选，并只把用户采纳或明确委托Agent选定的图片作为正式交付。当前只做“确认文案 → 配置卡 → KIE直接生图”，不做已有图片编辑或同款复刻。

## 运行前读取

- [统一任务产物目录与命名合同](references/artifact-layout.md)
- [输入、输出与人工门禁](references/input-output-contract.md)
- [渠道与版位](references/channel-placement.md)
- [视觉与Prompt规则](references/prompt-rules.md)
- 设计每套画面时读[完整画面方案](references/visual-directions.md)；先设计场景、IP动作和情绪，再整体安排画风与构图。扩展风格、字体或布局时同时读[固定项清单](references/visual-invariants.md)。
- 需要主风格描述时先检索[联网整理的主风格库](references/style-library.md)，可用`scripts/visual_directions.py --list-styles --query <关键词> --detail`只取相关条目。库外方向再查第一手资料或许可明确的开源库，自写适配描述并记录来源；不直接套用外部negative_prompt或模型参数。
- [合规视觉雷区](references/visual-compliance.md)
- [KIE生图合同](references/provider-contract.md)
- [比例适配与生成后复核清单](references/model-size-compatibility.md)
- [压缩与导出](references/export-rules.md)
- [任务合同](references/task-contract.md)
- [渲染清单合同](references/render-manifest.md)

当前渠道范围只使用[当前在投表清单](references/channel-placement.md)的8个渠道、19个尺寸与形式组合；旧102版位暂不启用，不作为兜底或自动补充。

## 必需输入

- 已确认的 APP 图片文案；
- 产品事实与品牌资产；
- 渠道、版位、图片形式、套数、Logo/IP/字体/CTA/UI等制作配置；
- 需要可识别 UI 时的真实产品截图；
- 用户对候选数量和付费生成的当前确认。

首次使用按[直连配置与恢复](references/provider-contract.md)配置 KIE Key 和本地工作目录。产品事实使用用户当前明确提供的资料，或其指定的正式产品资料目录；本包仅携带现有品牌图片，不内置价格、权益和渠道时效事实。

## 固定流程

1. 确认输入是已批准的固定格式APP图片文案；把每套的渠道、图片形式、主标题/副标题或短句整理为配置卡上下文。
2. 建立“产品事实→目标人群→具体场景→产品动作→可感知变化”的最小视觉链。
3. 默认启动`scripts/interactive_server.py`，显式把统一任务版本的`02_过程`作为`--output-dir`，打开配置卡供用户保存。用户明确委托Agent填写中间配置时，可由Agent调用同一个`normalize_config_result`校验并代存，不要求用户打开页面；记录本轮委托原文，不冒称用户亲手操作。一次任务只能选择一个具体版位，不能省略确定的配置结果。
4. 需要可识别APP/UI时等待用户上传真实截图；缺失时停止或改为不可识别的抽象屏幕。
5. 按确认文案先设计完整画面方案，写入`visual_concepts`：具体学习瞬间、IP/主体如何行动、逐张情绪变化，以及统一协调的构图和视觉体系。新任务默认`content_first`，批量按套随机主画风，优先不重复；先运行`--assign-styles`，再据此整体设计场景、IP动作、构图与配色，保存对应`style_id`。每张提示词与动作单独编写，同套双/三图共用画风；用户指定画风优先。按[完整画面方案](references/visual-directions.md)运行`scripts/visual_directions.py`保存`visual-plan.json`，再编写`image-render-manifest.json`，绑定计划、逐张动作与素材。预计常规裁切达到6%时按[白底蓝框适配](references/blue-frame-adaptation.md)准备布局参考；低于门槛常规适配。双/三图按[同套首张与分支规则](references/prompt-rules.md#同套双图三图生成)执行：图1使用原版素材，图2/3只引用同套图1PNG，按对应短句推进动作与状态。
6. 运行`scripts/validate_task.py`和`scripts/direct_batch.py --validate-only`，验证全部job、Prompt、比例、引用顺序和输出路径，不调用付费接口；同时确认本地可导入`requirements.txt`锁定的Pillow，以及蓝框模式需要的OpenCV、NumPy。
7. 告知预计图组数和图片数；取得当前任务付费确认后，按[直连配置与恢复](references/provider-contract.md)执行清单。先验证所有 job，再顺序生成，参考资产按内容哈希去重。默认单批最多12张，用户明确确认时最多20张；技术失败或提交状态不明时保存状态并停止，内容偏差仅作提示，不中断已授权批次。
8. 每张候选下载并解码为PNG，记录taskId、本地SHA-256、字节数和原图路径；不伪造供应商哈希或MCP产物ID。蓝框模式由`render.py`调用OpenCV识别实际框线、裁到内侧并拉伸至目标尺寸，另存无损预览，保留原图；找框失败的原图同样进入选择页并标注待复核，不中断其余已授权job。完整保留`image-render-result.json`，技术成功的候选全部进入选择页，文字、Logo、UI、事实和构图检查作为提示。
9. 默认由用户结合候选和检查提示直接选择“采纳”或“不采纳”，不要求理由。用户明确要求只看最终结果并委托中间选择时，Agent可检查候选、代选符合要求的方案，保存`decision_source=agent_delegated`及委托原文，不能冒称用户已人工审核；最终仍把成图交给用户查看。选择结果保存后直接运行`scripts/prepare_accepted_deliveries.py`，一次读取全部`accepted_schemes`，使用本地Pillow按已保存版位的精确尺寸和KB上限生成JPEG、校验并写入`04_交付`与`05_质检`；零采纳同样正常完成，本地处理不按图片数再次向用户授权。用户明确要求打包时，才把交付规格质检结果传给`scripts/package_accepted_images.py --delivery-result <路径>`，生成ZIP和交付清单到`06_打包`。
10. 任务根目录、版本、文件名和包名由`scripts/artifact_workspace.py`创建与校验；`.runtime/<任务ID>/`只保存可重建过程文件，不上传广告平台、不发布。

## 核心边界

- 文案必须逐字使用确认稿，生图模型不能改写产品事实或 CTA。
- 没有真实 UI 截图时，不生成可识别的虚构界面。
- 参考图必须标明 Logo、IP、字体、UI、风格或构图角色；不把旧广告图当编辑基准。
- 模型固定使用 KIE `gpt-image-2-5-sunburst-image-to-image`、`1K`，单图和每套首张至少提供一张本轮选择的原版参考资产，分支仅使用同套首张PNG；不切换其他模型或自动升级分辨率。请求参数以 `scripts/kie_model.py` 为准。
- 比例按目标尺寸选择最近的供应商支持值。预计常规裁切达到6%（含6%）时使用[白底蓝框适配](references/blue-frame-adaptation.md)，替换旧百分比留白提示；生成后去框并允许轻微拉伸，用户查看效果后采纳。低于门槛正常适配并列出结果。实际像素以返回文件为准，大幅放大时提示清晰度检查。
- 一个任务版本只允许一个具体版位。配置页使用单选，保存端也必须拒绝多个`placement_ids`；`placements`继续保留数组结构但长度固定为1。
- 同套双/三图先生成图1，图2/3都依赖同套图1且只传其PNG；首张落盘并核对回执后才可生成分支。同套字体、Logo、IP和视觉体系通过首张继承，不逐张重新随机。不同套仍独立生成，可换场景、人物、构图和视觉隐喻。
- 付费生成与外部参考图上传需要当前任务授权。
- 旧任务文件里的`paid_generation_approved=true`不能替代当前任务命令上的`--approved-in-current-task`。
- KIE提交结果不确定时保留任务状态并停止，不能再次创建可能重复扣费的任务。
- 生成后内容检查按[输入、输出与人工门禁](references/input-output-contract.md)只作为候选提示，不中断已授权批次、不自动淘汰或重做。
- 正式直连批次使用 `scripts/direct_batch.py`，统一验证、上传去重、任务恢复和结果记录；单张 `render.py` 提供同样的授权与状态保护。
- 蓝框去框与拉伸先形成候选预览；正式JPEG压缩与交付只处理用户采纳的图片。交付沿用同一框内处理结果，不再次对原图做cover裁切。本地处理不需要逐张授权。
- 交付打包只读取交付规格质检结果中已经校验的JPEG，不重新读取候选或重复压缩。
- 自动规格检查和内容提示都不替代人工选择；技术成功的候选全部给用户看，由用户决定是否采纳。
- 选择页只收集采纳/不采纳决定，不收集固定规则反馈、主观理由或跳过反馈状态；点击任一决定后直接进入下一个候选。
