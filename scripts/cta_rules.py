"""Carry confirmed CTA text into an explicit visual button instruction."""


def normalize_text(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("CTA must be text")
    return value.strip()


def configured_text(data):
    # An explicitly empty value means the user cleared the CTA.
    for key in ("cta", "cta_text", "ctaText", "CTA"):
        if key in data:
            return normalize_text(data[key])
    for key in ("context", "config", "image_config", "fields"):
        nested = data.get(key)
        if isinstance(nested, dict):
            text = configured_text(nested)
            if text:
                return text
    return ""


def prompt_rule(text):
    return (f'在画面底部自然留白处呈现醒目的CTA按钮，按钮文字逐字为“{normalize_text(text)}”，'
            '按钮底色与文字形成清楚对比，样式呼应本套画风，与主文案和人物保持清楚间距。')
