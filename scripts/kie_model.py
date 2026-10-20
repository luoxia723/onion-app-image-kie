"""Pinned KIE Sunburst 1K request policy and aspect-ratio adaptation."""
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


def normalize_resolution(value=None) -> str:
    resolution = str(value or RESOLUTION).strip().upper()
    if resolution != RESOLUTION:
        raise ValueError("resolution must be 1K; 2K/4K are not authorized for this configuration")
    return resolution


def nearest_aspect_ratio(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        raise ValueError("target dimensions must be positive")
    target = width / height
    return min(ASPECT_RATIOS, key=lambda label: abs(math.log(target / ASPECT_RATIOS[label])))


def geometry_report(width: int, height: int, aspect_ratio: str | None = None) -> dict:
    ratio = aspect_ratio or nearest_aspect_ratio(width, height)
    if ratio not in ASPECT_RATIOS:
        raise ValueError(f"unsupported Sunburst 1K aspect_ratio: {ratio}")
    target = width / height
    source = ASPECT_RATIOS[ratio]
    crop = max(0.0, 1 - min(target / source, source / target))
    axis = "左右" if source > target else "上下"
    fraction = round(crop * 100, 2)
    return {
        "aspect_ratio": ratio,
        "resolution": RESOLUTION,
        "crop_percent": fraction,
        "crop_axis": axis if crop > 1e-9 else "无",
        "needs_safe_area": fraction >= CROP_REVIEW_THRESHOLD_PERCENT,
        "adaptation_mode": "blue_frame" if fraction >= CROP_REVIEW_THRESHOLD_PERCENT else "cover",
        "adaptation_note": (
            "比例一致，生成后按交付像素缩放"
            if crop < 1e-9 else
            f"常规适配预计裁切 {fraction:.2f}%；使用白底蓝框生成，OpenCV去框后拉伸至目标尺寸，生成后请确认效果"
            if fraction >= CROP_REVIEW_THRESHOLD_PERCENT else
            f"预计裁切{axis}合计 {fraction:.2f}%；文字和 Logo 需留在保留区域"
        ),
    }
