"""KIE image model registry, fixed 1K policy and aspect-ratio adaptation."""
from __future__ import annotations

import math

MODEL = "gpt-image-2-5-sunburst-image-to-image"
PROVIDER = "kie-gpt-image-2-5-sunburst"
RESOLUTION = "1K"
ESTIMATED_CREDITS_PER_IMAGE = 3  # User's account/region screenshot, not a billing guarantee.
CROP_REVIEW_THRESHOLD_PERCENT = 6.0
ASPECT_RATIOS = {
    "1:1": 1.0, "3:2": 3 / 2, "2:3": 2 / 3,
    "4:3": 4 / 3, "3:4": 3 / 4, "16:9": 16 / 9,
    "9:16": 9 / 16, "21:9": 21 / 9, "27:16": 27 / 16,
    "16:27": 16 / 27, "9:8": 9 / 8, "8:9": 8 / 9,
}


GPT_IMAGE_2 = "gpt-image-2-image-to-image"
GPT_IMAGE_26_FLARE = "gpt-image-2-6/flare-image-to-image"
MODELS = {
    MODEL: "GPT Image 2.5 Sunburst",
    GPT_IMAGE_2: "GPT Image 2",
    GPT_IMAGE_26_FLARE: "GPT Image 2.6 Flare",
}


def normalize_model(value=None):
    model = MODEL if value is None else value
    if not isinstance(model,str) or model not in MODELS:
        raise ValueError("请选择支持的图片模型")
    return model


def aspect_ratios(model=MODEL):
    if normalize_model(model) in (GPT_IMAGE_2, GPT_IMAGE_26_FLARE):
        labels=("1:1","3:2","2:3","4:3","3:4","5:4","4:5","16:9","9:16","2:1","1:2","3:1","1:3","21:9","9:21")
        return {k:int(k.split(":")[0])/int(k.split(":")[1]) for k in labels}
    return ASPECT_RATIOS


def normalize_resolution(value=None) -> str:
    resolution = str(value or RESOLUTION).strip().upper()
    if resolution != RESOLUTION:
        raise ValueError("resolution must be 1K; 2K/4K are not authorized for this configuration")
    return resolution


def nearest_aspect_ratio(width: int, height: int, model=MODEL) -> str:
    if width <= 0 or height <= 0:
        raise ValueError("target dimensions must be positive")
    target = width / height
    ratios=aspect_ratios(model)
    return min(ratios, key=lambda label: abs(math.log(target / ratios[label])))


def cover_crop_report(source_width: int, source_height: int, width: int, height: int) -> dict:
    if min(source_width, source_height, width, height) <= 0:
        raise ValueError("image dimensions must be positive")
    source_extent = source_width * height
    target_extent = width * source_height
    removed = abs(source_extent - target_extent)
    extent = max(source_extent, target_extent)
    # Compare before division/rounding: a displayed 6.00% may still be below 6%.
    needs_review = removed * 100 >= extent * CROP_REVIEW_THRESHOLD_PERCENT
    return {
        "crop_percent": round(removed * 100 / extent, 2),
        "crop_axis": ("左右" if source_extent > target_extent else "上下") if removed else "无",
        "needs_safe_area": needs_review,
    }


def geometry_report(width: int, height: int, aspect_ratio: str | None = None, model=MODEL) -> dict:
    ratio = aspect_ratio or nearest_aspect_ratio(width, height, model)
    if ratio not in aspect_ratios(model):
        raise ValueError(f"unsupported model 1K aspect_ratio: {ratio}")
    report = cover_crop_report(*map(int, ratio.split(":")), width, height)
    fraction = report["crop_percent"]
    axis = report["crop_axis"]
    needs_review = report["needs_safe_area"]
    return {
        "aspect_ratio": ratio,
        "resolution": RESOLUTION,
        **report,
        "adaptation_mode": "natural_canvas" if needs_review else "cover",
        "adaptation_note": (
            "比例一致，生成后按交付像素缩放"
            if axis == "无" else
            f"原生画幅与目标比例差 {fraction:.2f}%；生成完整自然画布，将文字和主视觉留在安全区，再按固定窗口裁成精确尺寸"
            if needs_review else
            f"预计裁切{axis}合计 {fraction:.2f}%；文字和 Logo 需留在保留区域"
        ),
    }
