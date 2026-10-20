# APP图片渲染清单合同

`batch_render.py`读取：

```json
{
  "request_id": "...",
  "jobs": [
    {
      "job_id": "copy-001-placement-001-set-01-slot-01",
      "set_id": "copy-001-placement-001-set-01",
      "slot": 1,
      "copy_draft_id": "确认文案ID",
      "copy_text": "本张确认原句（单图主副文案以换行连接）",
      "prompt": "完整Prompt",
      "resolution": "1K",
      "size": "1280x720",
      "references": [
        {"label": "参考图1", "role": "品牌Logo", "asset_id": "...", "path": "assets/...png"}
      ],
      "output": "<任务版本目录>/03_候选/候选图片/copy-001-placement-001-set-01-01.png",
      "depends_on": []
    }
  ]
}
```

- 每个`job_id`唯一；同一套双图或三图共用`set_id`，`slot`按1、2、3排序；
- `prompt`必须逐字包含对应单图文案或当前slot的短句，不把多张文案挤进一张图；
- `resolution`固定为`1K`；`size`记录已保存版位的目标尺寸并映射为供应商比例，或直接使用保存的`aspect_ratio`。旧的`render_size`不代表实际1K像素；正式批次按保存的目标宽高统一选比例；
- 单图和首张参考顺序为Logo、IP、蓝框（命中时）、其他风格/构图、字体、真实UI；分支只传同套图1原始PNG作为参考图1。
- 预计常规裁切达到6%的job必须有`frame_layout_path`，指向本轮脚本生成的配置。准备方法、范围Prompt和后处理见[白底蓝框适配](blue-frame-adaptation.md)；`size`仍填写最终目标尺寸，不填写框模板像素；
- 单图和首张至少需要一张本轮原版参考图；分支必须填写`base_job_id`和仅包含该job_id的`depends_on`，参考路径必须等于同套图1的output。首张落盘前只验证依赖与路径，不能伪造占位图。
- 单图和首张选择Logo时必须将其作为`参考图1`并满足保真Prompt；分支从同套首张继承Logo，不重复传原版资产。位置按`logo_position(config)`确定：喜马拉雅720×1280、720×1559两种竖图为上方居中，其余默认左上角，完整规则见`prompt-rules.md`；
- `output`必须位于统一任务版本的`03_候选`；短时下载和可重建缓存才进入`.runtime/<任务ID>`；重跑不覆盖不匹配的KIE任务指纹；
- 清单不能保存API Key、上传临时地址或KIE结果临时URL。

- 所有有确认文案的job保存`copy_text`：双/三图对应当前slot短句，单图为主副文案以换行连接。新配置`prompt_format=positive_paragraph_v1`时，代码比对文案字段和Prompt原句，无需文字白名单。Prompt使用一段正向自然语言，技术限制留在配置和校验层。
- 正式执行使用`direct_batch.py`，该入口负责整套完整性、首张依赖、分支只传首张PNG以及本地回执校验。

## 多样化计划

新配置默认visual_diversity_enabled=true且visual_diversity_mode=content_first。Agent按文案编写每套完整visual_concepts，格式见[完整画面方案](visual-directions.md)；先用--assign-styles随机分配每套主画风，Agent按分配结果完成整体方案；布局、镜头、场景和配色不独立随机拼接。每张完整Prompt均须不同，同套继承规则可以共用。新配置art_direction_required=true，每套还需按艺术定调层级保存world、scene、story、composition、lighting_materials。新配置learner_story_required=true，保存learner_story的protagonist、pain_point、product_action、visible_change，首张含具体人物与痛点，逐张动作均围绕人物推进。清单顶层填写visual_plan_path，每个job绑定visual_direction_id，set_id使用计划中的同套标识。首张Prompt包含base_prompt_rule（已含图1动作），分支包含branch_prompt_rule及当前slot的slot_prompt_rules；首张IP与字体引用须和计划一致。direct_batch.py在付费前核对配置指纹、整套覆盖、逐张动作、规则文本和素材绑定。

历史配置没有prompt_format时，可以原样恢复，不向历史Prompt注入新规则。用户显式要求其他风格/布局时保存新版本并重建计划，不能修改已有付费任务指纹。

计划保留style_source_ids、style_description_origin、style_verification_status和style_image_validated。新任务使用库中visual_prompt正向画法描述，IP时代细节由完整场景决定，来源URL留在资料登记中；不把文献链接或上游负向模板画进广告。

清晰示意UI通过screen_ui_mode=conceptual记录，不需要截图参考；job.ui_text须等于计划screen_text，字段留在清单中校验；需要可见时直接描述具体界面内容。reference模式才要求真实截图。
