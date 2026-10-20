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


def geometry_report(width: int, height: int, aspect_ratio: str | None = None) -> dict:
    ratio = aspect_ratio or nearest_aspect_ratio(width, height)
    if ratio not in ASPECT_RATIOS:
        raise ValueError(f"unsupported Sunburst 1K aspect_ratio: {ratio}")
    report = cover_crop_report(*map(int, ratio.split(":")), width, height)
    fraction = report["crop_percent"]
    axis = report["crop_axis"]
    needs_review = report["needs_safe_area"]
    return {
        "aspect_ratio": ratio,
        "resolution": RESOLUTION,
        **report,
        "adaptation_mode": "blue_frame" if needs_review else "cover",
        "adaptation_note": (
            "比例一致，生成后按交付像素缩放"
            if axis == "无" else
            f"常规适配预计裁切 {fraction:.2f}%；使用白底蓝框生成，OpenCV去框后拉伸至目标尺寸，生成后请确认效果"
            if needs_review else
            f"预计裁切{axis}合计 {fraction:.2f}%；文字和 Logo 需留在保留区域"
        ),
    }
