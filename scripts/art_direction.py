"""Art-direction layers and subject/screen policies for new visual plans."""

ART_DIRECTION_FIELDS = (
    ("world", "世界与时代"),
    ("scene", "具体场景"),
    ("story", "叙事瞬间"),
    ("composition", "构图与阅读路线"),
    ("lighting_materials", "光色与材质"),
)

IP_RULE = (
    "IP保留脸型、发型、体型、年龄和关键标识；原服装核心配色与轮廓可辨，"
    "可少量加入符合画风或时代的纹样、材质、披肩、扣件或配饰。"
)
NO_IP_RULE = (
    "无品牌IP；主体可为文字、建筑、物件、抽象图形或普通原创人物，不必加人物，按本套画风与故事自由设计。"
)


def art_direction_layers(concept, required=False):
    layers = concept.get("art_direction")
    if layers is None:
        if required:
            raise ValueError("new visual concepts require layered art_direction before prompt writing")
        return None
    if not isinstance(layers, dict) or any(not isinstance(layers.get(key), str) or not layers[key].strip()
                                           for key, _ in ART_DIRECTION_FIELDS):
        raise ValueError("art_direction must specify world, scene, story, composition and lighting_materials")
    return {key: layers[key] for key, _ in ART_DIRECTION_FIELDS}


def concise_ip_note(note):
    common = (
        "保持所选IP的脸型、发型、体型、参考服装和关键标识；整体采用该主风格的材料与造型语言，不改变角色身份。"
        "原版Logo原样保留，标题继续服从独立字体参考。同套首张定调，后两张引用首张改变动作状态。"
    )
    note = note.replace(common, "")
    generic = "保留原版角色脸型、发型、体型、服装与关键标识，允许少量对应画风或时代的纹样、材质和配饰融入，保留身份与年龄。"
    return note.replace(generic, "").strip()


def screen_rule(config, concept):
    legacy_reference = bool(config.get("ui_reference_required") or config.get("screen_ui_reference_required"))
    mode = concept.get("screen_ui_mode") or config.get("screen_ui_mode") or ("reference" if legacy_reference else "conceptual")
    if mode not in {"conceptual", "reference", "none"}:
        raise ValueError("screen_ui_mode must be conceptual, reference or none")
    saved_mode = config.get("screen_ui_mode") or ("reference" if legacy_reference else "conceptual")
    if (saved_mode == "none" and mode != "none") or (saved_mode == "reference" and mode == "conceptual"):
        raise ValueError("concept screen mode conflicts with the saved screen choice")
    texts = concept.get("screen_text", [])
    if not isinstance(texts, list) or any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError("screen_text must contain explicit non-empty UI labels")
    texts = list(dict.fromkeys(texts))
    if mode == "none" and texts:
        raise ValueError("screen_text is incompatible with screen_ui_mode=none")
    from positive_prompt import enabled
    if enabled(config):
        rule = "屏幕以清晰示意界面呈现" + "、".join(f'“{text}”' for text in texts) + "。" if mode == "conceptual" and texts else ""
        return mode, texts, rule
    rules = {
        "conceptual": "屏幕可显示清晰示意UI，无需模糊；仅表达已确认功能，内部文字遵循本轮白名单，不生成未经确认的成绩、价格或效果数字。",
        "reference": "屏幕使用本轮提供的真实UI截图，保持已确认界面与功能，不凭空替换为另一种真实产品页面。",
        "none": "本套不展示电子屏幕或UI，使用选定主体与道具表达故事。",
    }
    return mode, texts, rules[mode]
