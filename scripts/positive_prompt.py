"""Compose new model prompts; technical contracts remain in config/manifest."""

FORMAT = "positive_paragraph_v1"


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
    parts = [direction["base_prompt_rule" if slot == 1 else "branch_prompt_rule"]]
    if slot > 1:
        parts.append(direction["slot_prompt_rules"][str(slot)])
    if texts[0]:
        parts.append(f'主标题文字逐字呈现为“{texts[0]}”，作为画面的第一文字层级，按本张构图完整排布。' if slot == 1 else f'本张主标题文字逐字更新为“{texts[0]}”，保持本套标题的视觉层级。')
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
            elif "字体" in role or ref.get("path") == direction.get("font_reference_path"):
                parts.append(f'{label}用于标题字形参考，标题沿用其中的字形骨架、笔画粗细、转折、外轮廓与描边层次，配色呼应当前画面，文字完整清晰。')
            elif direction.get("screen_ui_mode") == "reference" and ("UI" in role or "截图" in role):
                parts.append(f'屏幕完整呈现{label}提供的真实界面。')
    if frame_label:
        parts.append(prompt_rule(frame_label))
    prompt = paragraph(*parts)
    validate_paragraph(prompt)
    return prompt
