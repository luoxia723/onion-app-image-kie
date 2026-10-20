# 完整画面方案与多样化

新任务默认 `visual_diversity_mode=content_first`、`visual_style_mode=random`。批量按套随机分配主画风，优先不重复：单图每张是一套，双/三图每套共用一种画风。确认功能事实后，按抽到的画风依次设计世界与场景、故事、构图、光色与材质；随机的是主画风，其余视觉维度由Agent协调设计。

当前新任务的随机项：主画风按套从77条风格库分配；启用字体参考且未为本套指定时随机选一张字体PNG；只有配置选择随机IP且未指定本套角色时才随机选IP。Logo、文案、渠道与尺寸沿用配置。世界与时代、场景、故事、动作、构图、配色、光线和IP配饰由Agent依据画风与文案整体设计，不再分别抽取。用户指定画风、字体或IP时使用指定项。

参考图编号在每次请求内重新排列：单图/首张可能是Logo1、IP2、字体3；同套后续图只传已生成的本套第1张广告成图作为参考图1。因此分支继承的是首张已落实的整套设计，首张的画风来源仍是预先选定的风格库，Logo与字体素材不充当整张广告的画风参考。

## 设计一套画面

内部设计层级以[艺术定调](art-direction.md)为准：画风→世界与场景→故事→构图→光色材质。新配置还需在visual_concepts.art_direction中保存这五层决定；最终沿用之前的自然画面叙述方式，将这些决定提炼合并为一段正向描述，不输出分层分析、文字白名单或负面提示段。新配置使用prompt_format=positive_paragraph_v1。

从[Prompt规则](prompt-rules.md)中的创意链出发，先讲清楚学生处于哪个学习瞬间、卡在哪里、产品做了什么，以及变化如何被看见。每张都让人物通过姿势、视线、表情和学习动作参与这个过程：有IP使用选定IP，无IP使用普通原创学生；为人物表演与具体痛点保留画面空间。新配置learner_story_required=true，每套显式填写learner_story的protagonist、pain_point、product_action、visible_change。

每套由Agent整体编写视觉方案，把人物、道具、光线、配色、镜头和文字的位置放在同一个设计里考虑。小版位仍检查缩小后的可读性，同时保留表达内容所需的动作和空间层次；不要把大字、单一姿势、极简背景当成所有方案的固定构图。

批量主画风由风格库随机分配，池用完前优先不重复；有IP时使用支持IP适配的条目。用户指定画风时优先遵从指定；明确要求整批统一或由Agent整体指定画风时可保存 `visual_style_mode=coordinated`。每张仍单独设计动作、情绪或构图，允许共用品牌与字体规则，但不复制整段提示词充数。用户固定的Logo、IP、字体、渠道与文案仍优先。

例如同一套数学三图依次表现准备开始、安排任务、查看完成状态，三张继承本套首张的画风；另一个套组使用另一种抽到的主画风，重新整体设计其场景。主题与配色随本轮内容决定，不添加未确认的产品事实。

## 保存完整方案

默认随机模式下，保持用户保存的制作配置，先执行主画风分配，不调用付费接口：

```sh
python scripts/visual_directions.py --assign-styles --config <02_过程/image-config-result.json> --output <02_过程/visual-style-assignments.json>
```

读取每套的style_id和style_prompt（新格式取库中visual_prompt正向描述），按该画风编写完整 `visual_concepts`，保存对应style_id。顺序为文案1的全部套数、文案2的全部套数，长度等于文案数乘套数。下面仅示意抽中commercial_anime时的一套内容，实际使用本次分配结果。

```json
{
  "visual_diversity_mode": "content_first",
  "visual_concepts": [
    {
      "name": "清蓝目标路线",
      "art_direction": {"world": "现代家庭", "scene": "窗边学习桌", "story": "从补学目标到安排每日任务", "composition": "文案与角色动作形成清楚阅读路线", "lighting_materials": "窗光统一人物、木桌与纸面"},
      "style_id": "commercial_anime",
      "prompt": "本周开始数学学习的书桌场景。所选IP与练习本、纸卡处在统一的商业动漫视觉体系中，清楚线稿和柔和光影表现角色。浅蓝乳白环境、深色标题与少量暖黄呼应角色服装。主文案在左侧完整留白，角色在右侧略微前倾，视线与手部动作将阅读引向桌面任务；前景纸面与后景形成自然层次，Logo按规定位置保留。",
      "slot_actions": [
        "IP看向数学练习本，握笔、身体前倾，表现想把本周数学补起来、准备开始的状态。",
        "IP把空白纸卡沿目标与基础汇合的路线排好，用整理动作表现每日任务安排。",
        "IP指向今日纸卡，旁边的完成勾选表现学习推进，神态比开始时更轻松。"
      ]
    }
  ]
}
```

- `art_direction`保存从世界到光色的五层定调，按[艺术定调](art-direction.md)执行。screen_ui_mode和screen_text管理清晰示意UI或真实截图。
- `name` 是方案名称，`prompt` 是完整视觉方案，均不作为额外广告文案。
- `slot_actions` 按图片顺序写每张的动作和情绪，长度等于所选形式的图片数。对应短句由 `copy_refs` 与 `copy_text` 比对，Prompt直接写对应原句。
- 可选 `ip_asset_id` 在配置为随机IP时指定本套角色；用户已固定IP或不用IP时不能覆盖。可选 `font_reference_path` 只能选择原版字体库中的文件，并遵守字体开关。未指定时仍按已保存配置为每套选择IP和字体；整体方案需与最终所选素材协调。
- 用户指定的画风或布局继续保存到 `visual_direction`，其要求优先进入方案。明确使用coordinated模式时，可跳过随机分配，由Agent整体设计所需画风。

然后执行，不调用付费接口：

```sh
python scripts/visual_directions.py --config <02_过程/image-config-result.json> --output <02_过程/visual-plan.json>
```

建议用`positive_prompt.compose(config, direction, slot, references, frame_label)`合成一段正向Prompt，frame_label仅在实际使用蓝框时传入。首张Prompt包含 `base_prompt_rule`，其中已经包含图1动作。图2/3的Prompt包含同套 `branch_prompt_rule`，再加入各自的 `slot_prompt_rules["2"]` 或 `["3"]`。清单顶层填写 `visual_plan_path`，每张绑定对应 `visual_direction_id`；首张IP和字体使用计划中的路径。付费前检查整套覆盖、配置指纹、逐张动作与实际素材绑定。同套分支仍只引用本套首张原始PNG。

## 风格库按需参考

[主风格库](style-library.md)用于批量随机分配主画风，也可按需检索具体描述与IP适配。随机结果只决定主画风；完整场景和构图仍由Agent针对文案设计。来源ID随计划保存。

```sh
python scripts/visual_directions.py --list-styles --query 水墨 --detail
python scripts/visual_directions.py --list-styles --query "Art Deco" --detail
```

库外画法仍按现有来源与许可要求登记。方案和自动测试只能证明设计意图被保存与执行，实际美感、IP识别和信息可读性仍需看成图。

## 历史任务恢复

原有显式 `open` / `preset` 配置与已保存计划继续支持恢复，不重写其Prompt、素材、指纹或已生成文件。新任务采用 `content_first`；不要为了恢复旧任务，把新的设计字段注入旧配置。付费授权、模型1K、蓝框、候选选择与交付规则继续按各自合同执行。
