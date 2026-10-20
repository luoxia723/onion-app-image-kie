# 多样化视觉编排

用户未指定风格时，由Agent按文案编写并选择本轮开放方向，不要求用户提供风格名称。不同套探索不同画法和构图，同套双/三图只从自己的首张继承。这里定义Prompt的编排，不保证模型逐项复现效果。

## 主风格多样性的口径

用户要求的是主风格本身丰富、可持续扩展。每套选择一个清楚的主风格；不同套优先探索不同的主导视觉语言，不以配色、光影、镜头、布局或局部材质组合数量代替主风格数量。

Agent可从经典艺术与设计语言、绘画媒介、叙事画风、整体立体表现等方向继续构思本轮主风格，例如水墨、油画、浮世绘、装饰艺术、波普、超现实叙事、复古科幻或黏土定格。它们是开放的探索方向，不是新增的固定枚举，也不代表已实图验证。每个方向必须写清主导的造型、线面、空间与整体表现特征；不能只改名称或换颜色就当成新主风格。

有IP时仍保留角色识别特征，Logo和确认文案不受风格变化影响。同套图2/3从首张继承这个主风格，只改变对应文案和状态。风格统计只统计有具体定义的主风格方向；如需展示组合数，单独标为方案组合，不能称为独立风格数量。

## 开放方向与预设示例

风格没有8类或其他固定数量上限。新任务默认visual_diversity_mode=open，Agent先写入本轮visual_candidates，再生成计划。`config/visual-directions.json`保存已整理的具体视觉描述，可从[完整主风格库](style-library.md)查看，来源见config/visual-style-sources.json。以下只展示部分方向：

| 维度 | 示例选项 |
|---|---|
| 风格 | 精致商业动漫、平面编辑插画、柔和3D、纸艺拼贴、清透水彩、等距微缩场景、叙事光影插画、丝网印刷海报 |
| 布局 | 左文右主体、上文下景、左主体右文、中心大字角落角色、斜向动作构图、桌面俯视构图 |
| 镜头 | 平视中景、侧前方中景、稍远景、桌面斜俯视；按布局兼容性选择 |
| 场景 | 家庭学习角、安静阅读角、抽象学习舞台、纸面任务空间；仅承载已确认动作，不新增功能证据 |
| 配色 | 浅薄荷/墨绿、奶油/珊瑚橙、浅紫/藏青、浅天蓝/钴蓝、浅沙/橄榄绿、乳白/炭黑；所选Logo颜色保持原版 |

默认优先使用本轮开放方向，再用预设补充；平衡布局，先用不同风格和布局组合，再复用已用组合。配色、换IP或镜像只能辅助变化。用户指定的风格/布局优先，不要求强行去重。

有IP时锁定角色身份、脸型、发型、体型、服装和关键标识；可以改变动作表情、镜头及统一的画法/材质/光影。Logo与字体参考各自遵守固定项，不被风格词覆盖。未选IP时不新增吉祥物。小幅版位自动追加大字、单一主要动作、简化背景和道具的要求。

## 检索已有描述

```sh
python scripts/visual_directions.py --list-styles --query 水墨 --detail
python scripts/visual_directions.py --list-styles --query "Art Deco" --detail
```

返回具体描述、IP适配、中文/英文别名、来源id、文字审查与实图验证状态。description_origin标记项目自写/总结，不把博物馆原文标为CC0。完整来源、开源仓库锁定提交、许可证和采用范围见[来源登记](../config/visual-style-sources.json)；[GitHub调研](research/github-style-sources.md)与[经典艺术调研](research/classic-style-sources.md)保留核验依据。

本轮候选可以直接引用已收集条目，不用手抄并丢掉来源/IP约束：

```json
{"visual_candidates": {"styles": [{"id": "art-deco"}, {"id": "expressive-ink"}]}}
```

脚本解析别名到规范id，把完整描述、来源id和IP适配带入计划，首张接收具体的表现要求；分支仍只继承首张。修改引用条目的描述时标记为本轮改写。未知id必须补齐name和prompt，不能只有一个空标签。

库内是可独立作为主导的流派、媒介、工艺和视觉语言方向；保留技法分支与广告适配说明，不把同义词当新增主风格。纯抽象或单色工艺在保留具象IP、身份色时属于本项目改写，不声称完全复现历史流派。所有新描述目前只做文字审查，不能宣称已经逐一验证成图。

## 生成计划

先保留用户已选定的Logo、IP、字体策略、文案、版位与数量，再由Agent把制作方向写入配置扩展字段visual_candidates。方向写清一个主导画法/媒介，配合兼容材质、光影、空间组织；不要把互相矛盾的风格词机械叠加，也不要靠换名字重复同一描述。每轮候选数量按实际套数和用户探索范围安排，不需要固定穷举全部风格。

本轮候选示例（这些是画面表现要求，不是画面文案）：

```json
{
  "visual_candidates": {
    "styles": [
      {"id": "pastel_story", "name": "粉彩叙事", "prompt": "以清楚轮廓、柔和粉彩色层和克制纸面颗粒表现已确认动作。", "supports_ip": true, "components": {"medium": "粉彩", "lighting": "明亮柔光"}},
      {"id": "matte_clay", "name": "哑光黏土", "prompt": "人物与道具采用统一的哑光黏土体积、柔和投影与清楚轮廓。", "supports_ip": true}
    ],
    "layouts": [
      {"id": "foreground_action", "name": "前景动作留白", "prompt": "主要动作放在前景，文字占清楚的完整留白，保留Logo规定位置。"}
    ]
  }
}
```

候选id可以自行命名，不是枚举；name和prompt必填，同轮id及实质描述不能重复。components可写入本轮自选的媒介、材质、光影等细节，会进入首张Prompt。IP方向须明确supports_ip=true，并遵守角色识别约束。布局可不填framing_ids，由其自身描述决定镜头，避免被预设平视镜头覆盖；需要时可指定有效的镜头id。用户固定单一风格时不强制再编写其他候选。

配置与本轮候选确定后运行，不调用付费API：

```sh
python scripts/visual_directions.py --config <02_过程/image-config-result.json> --output <02_过程/visual-plan.json>
```

默认以request_id为随机种子，也可以传`--seed`。同配置和种子得到同样计划，文件存在时拒绝覆盖；重做使用新版本。

计划逐套保存set_id、direction_id、风格/布局/镜头/场景/配色、所选IP及字体路径，以及base_prompt_rule和branch_prompt_rule。写清单时：

1. 顶层填写visual_plan_path；按计划set_id组织每套，所有slot绑定该套visual_direction_id。
2. 首张使用计划选定的IP及字体，结合确认文案、具体动作和既定Logo规则编写Prompt，完整加入base_prompt_rule。不是只把风格名称放在meta里。
3. 图2/3仅引用同套首张，完整加入该套branch_prompt_rule，只更换对应文案和状态；仍满足首张依赖及文字白名单规则。
4. direct_batch.py检查配置指纹、计划与所有job的对应、规则是否进入实际Prompt，以及首张IP和字体引用。自动检查不能判断成图是否保持IP识别和Logo保真，仍需视觉复核。

用户明确指定风格/布局时，在配置中保存visual_direction，例如：

```json
{"visual_direction": {"style_id": "soft_3d", "layout_id": "title_top_scene_bottom"}}
```

指定池外方向时，用style_prompt或layout_prompt保存本轮描述；未指定的维度仍自动编排。不得把用户特定任务的选择写成全局限制。

新保存的配置默认启用开放计划；未指定固定风格、也没有本轮开放风格候选时，预检要求补齐候选，不能静默退回预设。明确只用预设时可指定visual_diversity_mode=preset。历史配置缺少模式或开关时保持原任务恢复行为，不回写已生成图片、Prompt或指纹。生成数量、模型、费用确认、内容提示和选择交付沿用当前合同，本模块不自行发起生图。
