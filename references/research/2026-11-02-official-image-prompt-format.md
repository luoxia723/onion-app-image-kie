# GPT 官方生图提示词格式调研

日期：2026-11-02。范围：OpenAI 官方文档与 Cookbook；仅调研，未修改运行代码，未调用付费规划或生图接口。

## 结论与适用边界

官方建议用引号标出必须呈现的原文，并明确位置、字体、出现次数和不增加其他文字。没有找到“必须用花括号包裹画面文字”或“必须写成一段”的要求。官方明确允许自然段、类似 JSON 的结构、指令和标签等不同形式；应选择清楚、易维护的写法，而非依赖特殊语法。[官方 Image prompting：Prompting fundamentals 与 Render exact text](https://developers.openai.com/api/docs/guides/image-prompting#prompting-fundamentals)

“建议”不等于 API 的语法约束，也不保证图像中的文字一定正确。中文引号与英文引号的效果优劣，本次官方资料没有建立结论，不能说换成英文引号就会修好。

当前项目通过 KIE 调用 `gpt-image-2-5-sunburst-image-to-image`。OpenAI 指南可作为提示词设计依据，但不能因此断言第三方请求参数、模型行为或效果与 OpenAI 直连完全一致。本次不建议为配合官方示例，直接向 KIE 请求添加其未声明支持的参数。

## 官方依据

| 问题 | 官方指导及解读 |
|---|---|
| 文案是否应放进引号？ | 应用引号明确原文，说明排版位置与字体；广告示例进一步说明准确呈现、不要额外字符、只出现一次。[官方指南](https://developers.openai.com/api/docs/guides/image-prompting#render-exact-text)、[Cookbook 广告文字示例](https://developers.openai.com/cookbook/examples/multimodal/image-gen-models-prompting-guide#55-marketing-creatives-with-real-text-in-image) |
| 必须花括号、JSON、XML 吗？ | 官方承认多种格式均可表达相同意图，强调清晰可维护；未指定花括号为文字渲染协议。[官方指南](https://developers.openai.com/api/docs/guides/image-prompting#prompting-fundamentals) |
| 必须一段式、不许换行吗？ | 没有。复杂要求建议分成带标签的部分；Cookbook 明确建议复杂请求使用短分段或换行，便于阅读和维护。[Cookbook Prompting Fundamentals](https://developers.openai.com/cookbook/examples/multimodal/image-gen-models-prompting-guide#2-prompting-fundamentals) |
| 参考图怎么描述？ | 按实际输入顺序标明编号和用途，说明提供主体、风格、服饰或背景，以及如何组合。[官方指南](https://developers.openai.com/api/docs/guides/image-prompting#prompting-fundamentals) |
| 分支图／编辑怎么写？ | 分开写本次改变与必须保留的细节，并在迭代中重申关键约束；逐次小改便于判断变化来源。[官方指南](https://developers.openai.com/api/docs/guides/image-prompting#refine-an-image-across-turns) |
| 是不是越长越好／越短越好？ | 长提示词可以有效；从清楚的基础提示开始、一次小改更便于调试。官方没有给所有任务统一的最佳长度。[Cookbook Prompting Fundamentals](https://developers.openai.com/cookbook/examples/multimodal/image-gen-models-prompting-guide#2-prompting-fundamentals) |

## 对当前项目的判断

以下为结合项目的工程建议，不是官方指定模板：

1. 项目已有 `主标题文字逐字呈现为“…”` 这类明确引号写法，方向合理。旧字体样张文字混入广告，不能简单归因于“没加引号”。
2. 可把画面任务、当前准确文字、参考图用途、保留／变化约束分成简短区块，尤其方便人工修改。不应把“一段式”当成 GPT 官方要求。
3. 文字区应明确当前标题、允许的副标题／CTA、各自次数；品牌标准字另属 Logo，避免“没有其他文字”和保留 Logo 相互冲突。
4. 字体样张只提供字形；品牌 Logo、人物身份、画风分别赋予参考职责。具体角色／材质语言仍要写清，引号不能解决空间、动作或素材职责冲突。
5. 后续图写当前替换文案及本次动作变化，说明从首图保留的身份、画风与字体体系；不要夹带其他图的生成流程。
6. 取消人工编辑阶段对系统固定句子的逐字匹配，不妨碍系统在自动组装阶段检查资料完整；API 传输、参考文件、任务依赖、尺寸与文件规格仍应客观检查。

## 可采用的示例骨架

下面是项目建议示例，不是官方原文，也未实际生图验证。编号须与该次真实参考数组一致；无 Logo、字体或人物参考时相应条目应省略。

```text
画面任务：
生成一张完整横版广告。描述当前一个瞬间的场景、人物、道具接触、机位和标题留白。

本张文字：
主标题："拍题精学"。逐字呈现，只出现一次。
位置与字体：在约定标题区域完整排布；具体字形、描边和字色按本套要求。
本张未配置副标题和按钮，不额外添加广告文案；Logo 自带标准字按品牌参考保留。

参考图用途：
参考图1：品牌 Logo，仅提供品牌图形与标准字。
参考图2：角色身份参考；本张画法和材质服从选定画风。
参考图3：仅提供标题字体与排版语言，旧文字和附带贴纸不作为广告内容。

画面约束：
说明所需的统一材质、完整关键动作和文字可读性。
```

对分支图，应将参考区改为实际上传的首图，并分开说明：保持哪些视觉锚点、当前标题整体替换为什么、当前动作和机位如何变化。不要在没有原版素材输入时仍列出它们。
