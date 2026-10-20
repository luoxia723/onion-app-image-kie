# GitHub 主风格描述来源调研

> 本文保留来源调研快照。当前已接入的描述与执行状态见[主风格库](../style-library.md)。

核验日期：2026-10-19（America/Los_Angeles）。范围：只读公开仓库与原始文件；未调用付费生图、未安装仓库代码、未改动技能或生成配置。统计使用下列锁定提交，数量代表原始记录，不代表可用的独立主风格数。

## 结论

优先整理 `github-mk-styles`（CC0）、`github-twri-styler`（MIT），以 `github-milehigh-styler`（MIT）的艺术流派和媒介条目补充。已有成千上万条提示词记录，但其中混入艺术家、地点、题材、灯光、使用场景及重复项，不能把总行数包装成主风格数量。对本项目最有用的是提取流派/媒介名称后，重新编写适配 IP、Logo 和中文广告的可执行描述；不建议直接随机拼接原始 prompt。

## 已核验的候选

### github-mk-styles — K3nt3L/MK-Styles

- 仓库：[MK-Styles](https://github.com/K3nt3L/MK-Styles)。锁定提交：`ec4941afc18c93a923069ab7c4af644c41a77596`。
- 实际文件：[主文件 62 条](https://github.com/K3nt3L/MK-Styles/blob/ec4941afc18c93a923069ab7c4af644c41a77596/sdxl_styles_marc_k3nt3l.json)、[artstyle 分类 30 条](https://github.com/K3nt3L/MK-Styles/blob/ec4941afc18c93a923069ab7c4af644c41a77596/Categories/sdxl_styles_artstyle.json)、[日本艺术分类 6 条](https://github.com/K3nt3L/MK-Styles/blob/ec4941afc18c93a923069ab7c4af644c41a77596/Categories/sdxl_styles_japan_art.json)、[纸艺分类 10 条](https://github.com/K3nt3L/MK-Styles/blob/ec4941afc18c93a923069ab7c4af644c41a77596/Categories/sdxl_styles_papercraft.json)。分类包含空白 base，并有跨文件重复，不能直接相加。
- 结构：JSON 数组，每项为 `name`、`prompt`、`negative_prompt`；正向模板通常含 `{prompt}`。覆盖石版印刷、腐蚀版画、蓝晒、蜡画、刺绣、酒精墨水、浮世绘、包豪斯等真实媒介/流派。
- 许可：已直接读取 [LICENSE（CC0-1.0）](https://github.com/K3nt3L/MK-Styles/blob/ec4941afc18c93a923069ab7c4af644c41a77596/LICENSE)。仓库同时带有其他项目的风格副本，不能把本仓库 CC0 声明当作所有上游内容来源都已追溯的保证；优先作者自己的 MK 条目，记录来源。
- 数据问题：`Categories/sdxl_styles_crafting.json` 此提交有数组尾逗号，严格 JSON 解析失败；[文件](https://github.com/K3nt3L/MK-Styles/blob/ec4941afc18c93a923069ab7c4af644c41a77596/Categories/sdxl_styles_crafting.json)。主文件含艺术家姓名方向，应与通用媒介分开。负向词需按项目重写，避免阻碍 IP 或广告排字。
- 建议：**第一优先，选择性整理**；可补充传统印刷、地方工艺与手作媒介，不只增加现代数码风格。

### github-twri-styler — twri/sdxl_prompt_styler

- 仓库：[sdxl_prompt_styler](https://github.com/twri/sdxl_prompt_styler)。锁定提交：`51068179927f79dce14f38c6b1984390ab242be2`。
- 实际文件：[base 1 条](https://github.com/twri/sdxl_prompt_styler/blob/51068179927f79dce14f38c6b1984390ab242be2/sdxl_styles_base.json)、[sai 17 条](https://github.com/twri/sdxl_prompt_styler/blob/51068179927f79dce14f38c6b1984390ab242be2/sdxl_styles_sai.json)、[twri 89 条](https://github.com/twri/sdxl_prompt_styler/blob/51068179927f79dce14f38c6b1984390ab242be2/sdxl_styles_twri.json)，合计 107 条原始记录。
- 结构：`name`、`prompt`、`negative_prompt`，用 `{prompt}` 插入主体。含装饰艺术、新艺术、立体主义、表现主义、印象派、点彩、波普、超现实、水彩、纸艺、复古未来、黏土与像素等方向。
- 许可：已直接读取 [LICENSE（MIT，twri 2023）](https://github.com/twri/sdxl_prompt_styler/blob/51068179927f79dce14f38c6b1984390ab242be2/LICENSE)。复制实质内容时保留许可及版权声明。
- 适配风险：有商业题材、摄影技巧、画质增强与游戏品牌条目，并非全是主风格；有渲染器词及模型常用负面词。品牌名方向不宜直接作为本项目自动候选，替换成通用视觉特征。
- 建议：**第一优先，结构清晰的基础词典**；把流派/媒介抽取到主风格，镜头、主题、排版分列，不能全数纳入主风格。

### github-milehigh-styler — TripleHeadedMonkey/ComfyUI_MileHighStyler

- 仓库：[MileHighStyler](https://github.com/TripleHeadedMonkey/ComfyUI_MileHighStyler)。锁定提交：`44b7605cd25eb2dc830a3342654ac6a8ca11ea9e`。
- 实际文件：[V2 大表 1509 条](https://github.com/TripleHeadedMonkey/ComfyUI_MileHighStyler/blob/44b7605cd25eb2dc830a3342654ac6a8ca11ea9e/data/milehighV2/final_correctly_formatted_mile_high_styles.json)、[Aesthetic 55 条](https://github.com/TripleHeadedMonkey/ComfyUI_MileHighStyler/blob/44b7605cd25eb2dc830a3342654ac6a8ca11ea9e/data/Azazeal_Styles/Aesthetic_Styles.json)、[Line Art 47 条](https://github.com/TripleHeadedMonkey/ComfyUI_MileHighStyler/blob/44b7605cd25eb2dc830a3342654ac6a8ca11ea9e/data/Azazeal_Styles/Line_Art_Styles.json)。均实测为三字段数组；统计不合并重复目录版本。
- 许可：已直接读取 [LICENSE（MIT）](https://github.com/TripleHeadedMonkey/ComfyUI_MileHighStyler/blob/44b7605cd25eb2dc830a3342654ac6a8ca11ea9e/LICENSE)。保留版权及许可；内部聚合文件需进一步追踪作者和上游。
- 有用范围：学术写实、丙烯、分析立体主义、中国水墨、陶艺、织造等。大表有 1509 个不同名称，**不是 1509 种独立主风格**：还包含城市、菜系、营销、艺术教育、摄影对象、艺术家、音乐与戏剧。
- 适配风险：部分模板含异常 `¬` 字符及冗余 `mode`；目录也有成人身体/衣着状态，不能全目录导入；艺术家与动画工作室应单独标注，不能默认为通用主风格。负面词常排斥其他绘画媒介，须转为针对本方向的描述。
- 建议：**扩充检索来源**，白名单选流派/工艺/媒介，不直接作为随机库。

### github-wolfden-stylers — wolfden/ComfyUi_PromptStylers

- 仓库：[ComfyUi_PromptStylers](https://github.com/wolfden/ComfyUi_PromptStylers)，提交 `376b3aa2d6c418ec3176b9e7ee6447281d8a16dc`。
- [总表](https://github.com/wolfden/ComfyUi_PromptStylers/blob/376b3aa2d6c418ec3176b9e7ee6447281d8a16dc/sdxl_styles_all.json) 5014 条，实测名称去重 4844；[超现实分类](https://github.com/wolfden/ComfyUi_PromptStylers/blob/376b3aa2d6c418ec3176b9e7ee6447281d8a16dc/sdxl_styles_surrealism.json) 41 条，[印象派分类](https://github.com/wolfden/ComfyUi_PromptStylers/blob/376b3aa2d6c418ec3176b9e7ee6447281d8a16dc/sdxl_styles_impressionism.json) 31 条。标准三字段。
- [LICENSE 为 MIT，版权 twri 2023](https://github.com/wolfden/ComfyUi_PromptStylers/blob/376b3aa2d6c418ec3176b9e7ee6447281d8a16dc/LICENSE)；README 指向 twri，上游内容大量重叠。
- 总表同时含艺术家、灯光、摄影、主题、时间等；所谓超现实分类也混入具体景物和印象派场景，不能根据文件名自动认定主风格。建议用于补漏和交叉核对，不能宣传“新增五千种风格”。

### github-fooocus-styles — lllyasviel/Fooocus

- 仓库：[Fooocus](https://github.com/lllyasviel/Fooocus)，提交 `ae05379cc97bc4361ec8b4ec90193dab21be763f`。
- [diva 文件](https://github.com/lllyasviel/Fooocus/blob/ae05379cc97bc4361ec8b4ec90193dab21be763f/sdxl_styles/sdxl_styles_diva.json) 79 条，[fooocus 文件](https://github.com/lllyasviel/Fooocus/blob/ae05379cc97bc4361ec8b4ec90193dab21be763f/sdxl_styles/sdxl_styles_fooocus.json) 8 条，部分项只有 `negative_prompt`，并非统一正向三字段。
- 仓库 [LICENSE 为 GPL-3.0](https://github.com/lllyasviel/Fooocus/blob/ae05379cc97bc4361ec8b4ec90193dab21be763f/LICENSE)。不能把它当作无条件可复制的 CC0 词库；聚合内容需找原始作者及许可。建议参考分类事实、自己写描述，不整包复制。
- diva 有巴洛克、洛可可、至上主义、色域绘画、彩铅等方向，同样混有灯光、心情、品牌和用途。
- `Fooocus Enhance` 的负向项含文字、Logo、字母等禁用词，与本项目必须呈现品牌和文案直接冲突；还有 SD 权重语法。**不要整段接入当前 KIE 提示词。**

### github-styler-pipeline — andreszs/ComfyUI-Styler-Pipeline

- 仓库：[Styler-Pipeline](https://github.com/andreszs/ComfyUI-Styler-Pipeline)，提交 `feeb683d74f607b057181b26de1d673af53567d7`。
- [aesthetic](https://github.com/andreszs/ComfyUI-Styler-Pipeline/blob/feeb683d74f607b057181b26de1d673af53567d7/data/aesthetic.json) 49 条，[line_art](https://github.com/andreszs/ComfyUI-Styler-Pipeline/blob/feeb683d74f607b057181b26de1d673af53567d7/data/line_art.json) 21 条，[sci_fi](https://github.com/andreszs/ComfyUI-Styler-Pipeline/blob/feeb683d74f607b057181b26de1d673af53567d7/data/sci_fi.json) 50 条。三字段，部分正向是可直接追加的描述，无 `{prompt}`。
- [MIT，andreszs 2026](https://github.com/andreszs/ComfyUI-Styler-Pipeline/blob/feeb683d74f607b057181b26de1d673af53567d7/LICENSE)。
- line_art 有钢笔、交叉排线、笔刷线稿等细分；sci_fi 文件实际上主要是科幻场景，不应算主风格。目录另有内衣和服装状态，必须选择导入范围。
- [作者文档](https://github.com/andreszs/ComfyUI-Styler-Pipeline/blob/main/docs/README.md) 建议具体视觉描述、避免抽象质量标签，并提示某些名词会导致模型额外生成物件。建议用于改良描述写法，不必安装节点。

### github-styleselector-xl — ahgsql/StyleSelectorXL

- 仓库：[StyleSelectorXL](https://github.com/ahgsql/StyleSelectorXL)，提交 `d538b0c47582e18e3e23decae0026e60632c8b7a`。
- [sdxl_styles.json](https://github.com/ahgsql/StyleSelectorXL/blob/d538b0c47582e18e3e23decae0026e60632c8b7a/sdxl_styles.json) 77 条，三字段；大量方向与 twri 重合，也含品牌游戏、技巧和 base。
- 核验树未找到 LICENSE，GitHub 仓库 API 的 license 字段为 null：[第一方 API](https://api.github.com/repos/ahgsql/StyleSelectorXL)。公开可读不等于已明确允许复制；**不直接收编原文**，优先使用许可明确的原始来源。

## 针对本项目的整理规则（建议，非已实施）

1. 一套只选一个 `main_style_id`。风格记录使用自己的中英文名称、媒介/流派、可见特征、IP 保持要求、可读性限制、来源链接、许可、来源提交。
2. 同义词和同一方向不同命名去重；base、画质、镜头、场景、配色、布局、人物状态不计为主风格。
3. 区分 `movement`、`medium`、`craft`、`visual_language`。它们均可成为主风格起点，但每次应选一个主导方向，不能随机叠满互斥流派。
4. 采用白名单导入；艺术家/品牌/工作室、成人、恐怖、政治宗教题材从默认教育广告库排除，保留人工决策空间。艺术家姓名与不适合教育广告并非同一件事；此处是自动编排范围选择。
5. 不继承外部 negative prompt。改成项目自己的约束，特别不能排除中文、Logo、IP。清理权重标记、LoRA/模型名、渲染参数、画质口号与无效占位符。
6. 首张收到唯一主风格的完整具体说明；后两张仍按现有 base/delta 链继承首张。扩风格库不改变三图依赖逻辑。
7. 记录 `draft / reviewed / image_validated`；文本合理或免费校验通过不等于实际成图验证。候选数量、去重主风格数量、已验证数量分别统计。

## 可重新撰写的主风格方向示例

以下是本次研究者原创的简短中文描述示意，不是外部 prompt 的逐条翻译；仍需按具体 IP 和版位补足。历史流派/媒介名称可作为检索入口。

| 主方向 | 可见表现描述（原创） |
| --- | --- |
| 中国水墨 | 以干湿浓淡的墨迹塑造体积，边缘保留毛笔运行感；文字与 Logo 保持清晰轮廓。 |
| 分析立体主义 | 将道具和空间拆成相互衔接的几何切面，IP 的面部关键特征保持完整。 |
| 装饰艺术 | 轮廓强调秩序、阶梯形和几何装饰，形体利落，避免装饰吞没标题。 |
| 点彩 | 以细小分色点形成远看连贯的形体与光感，人物识别区避免过度碎化。 |
| 浮世绘木版 | 平整色面、清晰墨线和层次分明的套色，背景细节有木刻式节奏。 |
| 蜡画 | 让颜色呈现半透明蜡层与温润堆叠感，局部保留刮擦的纹理。 |
| 彩色石版印刷 | 用有限套色与细密颗粒构建色层，保留轻微印刷错位的手工趣味。 |
| 蓝晒 | 以深蓝基底与高亮剪影建立主要关系，保留感光纸般的明暗过渡。 |
| 腐蚀版画 | 依靠细线、排线与颗粒层次表现体积，道具轮廓有蚀刻式精确感。 |
| 彩色玻璃 | 把形体归纳为相互镶嵌的透光色块，深色分隔线统一人物和背景。 |
| 刺绣 | 以可见针脚、绣线走向和布底组织塑形，文字采用清晰的整体排版。 |
| 纸卷艺术 | 以弯折纸条和卷曲边缘构建立体层次，人物保留 IP 的比例与标识。 |
| 酒精墨水 | 让背景色形成自然扩散、透明叠层与流动边界，人物主体保持稳定可辨。 |
| 色域绘画 | 以大面积色层和边界关系构建情绪，让 IP 与标题成为清晰视觉锚点。 |
| 复古未来 | 用早期太空想象中的圆润工业形体和实体仪表语言描绘学习场景。 |

本报告只完成来源筛选与可复用性判断；未声称上述来源的每个条目已经适配或验证。
