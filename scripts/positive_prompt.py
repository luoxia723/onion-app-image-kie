"""Compose new model prompts; technical contracts remain in config/manifest."""

FORMAT = "positive_paragraph_v1"
VISUAL_CONTRACT_VERSION = "visual_rules_v1"
FONT_FEATURES = "字体类型、字形骨架、笔画粗细、转折、外轮廓、描边层次、字面宽窄与排版密度"
CONTENT_RULE = "广告正文仅使用本张确认文案，界面功能、说明文字和具体数字均以本轮已确认资料为依据。"


def task_rule(config):
    placement = config["placements"][0]
    width = placement.get("target_width") or config.get("target_width")
    height = placement.get("target_height") or config.get("target_height")
    orientation = ""
    if width and height:
        orientation = "横版" if int(width) > int(height) else "竖版" if int(width) < int(height) else "方版"
    category = placement.get("category") or config.get("category") or placement.get("channel") or "应用投放"
    return f"生成一张{orientation}{category}独立广告图，整张采用一个连续完整的场景。"


def font_rule(label):
    return (f"{label}仅用于标题字形和排版参考，其中示例字句在本图由确认文案完整替换；"
            f"标题保持参考中的{FONT_FEATURES}，插画画风用于人物与场景，标题采用确定的参考字体体系，文字配色可随画面调整。")


def inherited_font_rule():
    return "标题字形、描边、字体类型、字面宽窄和排版密度沿用首张已确定的字体体系，本张文字由当前确认稿完整替换。"


def readability_rule():
    return "文字和关键图形与局部背景保持清楚对比；近色或纹理干扰由背景明度、自然留白和布局调整解决，装饰服从阅读焦点。"


def branch_title_rule(text):
    return (f"首张文案所在区域在本图完整替换为“{text}”，该短句作为本张主文案，"
            "文案区仅保留本张确认内容，字体和层级沿用首张，断行与间距适应当前短句长度。")


def is_font_reference(ref):
    return "字体" in str(ref.get("role") or "") or "font-references" in str(ref.get("path") or "")


def validate_visual_contract(config, prompt, references, slot=1, copy_text=""):
    version = config.get("visual_contract_version")
    if version is None:
        return
    if version != VISUAL_CONTRACT_VERSION:
        raise ValueError("unsupported visual_contract_version")
    required = [task_rule(config), CONTENT_RULE, readability_rule()]
    if slot > 1 and copy_text:
        required.append(branch_title_rule(copy_text))
    fonts = [ref for ref in references if is_font_reference(ref)]
    if slot == 1:
        if fonts and not config.get("font_reference_enabled", True):
            raise ValueError("font references conflict with the saved font switch")
        if config.get("font_reference_enabled", True) and not fonts:
            raise ValueError("visual contract requires the selected font reference")
        required.extend(font_rule(ref["label"]) for ref in fonts)
    elif config.get("font_reference_enabled", True):
        required.append(inherited_font_rule())
    if any(rule not in prompt for rule in required):
        raise ValueError("prompt is missing a required visual contract instruction")


def enabled(config):
    # Missing format denotes a frozen historical task, never rewrite its prompt.
    value = config.get("prompt_format")
    if value not in (None, FORMAT):
        raise ValueError("unsupported prompt_format")
    return value == FORMAT


def paragraph(*parts):
    sentences = []
    for part in parts:
        text = " ".join(part.split()) if part else ""
        if text:
            sentences.append(text if text[-1] in "。！？；.!?;" else text + "。")
    return "".join(sentences)


def validate_paragraph(prompt):
    if not prompt.strip() or any(char in prompt for char in ("\n", "\r")):
        raise ValueError("new prompt must be one non-empty paragraph")
    if "画面文字白名单" in prompt or "negative_prompt" in prompt:
        raise ValueError("new prompt must describe the desired picture directly")


def approved_copy(source, slot, count):
    if count > 1:
        return [source.get(f"short{slot}") or ""]
    return [source.get("mainTitle") or source.get("short1") or "", source.get("subtitle") or ""]


def compose(config, direction, slot=1, references=(), frame_label=None):
    """Return one positive paragraph using a frozen plan and actual ref labels.

    No model call, auto-truncation or negative-word filtering occurs here.
    Agent-authored scene/action prose must already describe desired content.
    """
    if not enabled(config):
        raise ValueError("compose requires the new prompt_format")
    from logo_reference import logo_position, logo_prompt_rule
    from blue_frame import prompt_rule
    from cta_rules import prompt_rule as cta_rule

    count = int(config["placements"][0].get("image_count") or {"双图": 2, "三图": 3}.get(config.get("image_form"), 1))
    copies = config.get("copy_refs") or []
    source = next((c for c in copies if c.get("copyDraftId") == direction.get("copy_draft_id")), None)
    if source is None and len(copies) == 1:
        source = copies[0]
    if source is None:
        raise ValueError("direction must identify its approved copy")
    texts = approved_copy(source, slot, count)
    parts = [task_rule(config), direction["base_prompt_rule" if slot == 1 else "branch_prompt_rule"]]
    if slot > 1:
        parts.append(direction["slot_prompt_rules"][str(slot)])
    product_action = (direction.get("learner_story") or {}).get("product_action", "").rstrip("。")
    if product_action and product_action not in "".join(parts):
        parts.append(product_action)
    if texts[0]:
        parts.append(f'主标题文字逐字呈现为“{texts[0]}”，作为画面的第一文字层级，按本张构图完整排布。' if slot == 1 else branch_title_rule(texts[0]))
    if len(texts) > 1 and texts[1]:
        parts.append(f'副标题文字逐字呈现为“{texts[1]}”，字号小于主标题，与主标题形成清楚的阅读关系。')
    if config.get("cta"):
        parts.append(cta_rule(config["cta"]))
    if slot == 1:
        for ref in references:
            label, role = ref["label"], ref.get("role", "")
            asset_id = ref.get("asset_id") or ""
            if asset_id.startswith("logo."):
                parts.append(logo_prompt_rule(label, logo_position(config)))
            elif asset_id.startswith("ip."):
                parts.append(f'{label}为本画面角色原型。')
            elif is_font_reference(ref) or ref.get("path") == direction.get("font_reference_path"):
                parts.append(font_rule(label))
            elif direction.get("screen_ui_mode") == "reference" and ("UI" in role or "截图" in role):
                parts.append(f'屏幕完整呈现{label}提供的真实界面。')
    elif config.get("font_reference_enabled", True):
        parts.append(inherited_font_rule())
    parts.extend([readability_rule(), CONTENT_RULE])
    if frame_label:
        parts.append(prompt_rule(frame_label))
    prompt = paragraph(*parts)
    validate_paragraph(prompt)
    validate_visual_contract(config, prompt, references, slot, texts[0])
    return prompt
