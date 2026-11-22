#!/usr/bin/env python3
"""
image_compress.py - Pillow 压缩图片到目标 KB。

# 使用示例

  python3 image_compress.py \\
    /tmp/in.png /tmp/out.jpg \\
    --target-kb 200

# 策略

  1. 若传 target_width/target_height，先按 cover 居中裁切到目标尺寸
  2. 从同一张 RGB 图比较不同色度采样和质量级，选择达标的较清晰候选
  3. 有精确目标宽高时始终保持该像素尺寸，不能为减小体积继续缩图
  4. 未指定精确宽高时才允许按 0.9 逐级缩小，最多 10 轮
  5. 无法同时满足尺寸和体积时明确失败，不留下假成功文件

# 退出码

  0: 成功
  1: 输入文件不存在 / 不可读
  2: 压缩失败（无法满足目标尺寸/体积）
"""

import argparse
from io import BytesIO
import os
import sys
import tempfile
from typing import Optional

try:
    from PIL import Image
except ImportError:
    print("❌ 需要安装 Pillow：pip install Pillow", file=sys.stderr)
    sys.exit(1)

if __package__:
    from .image_quality import EncodingQuality, logo_bounds
else:
    from image_quality import EncodingQuality, logo_bounds


def resize_cover(img: Image.Image, target_width: int, target_height: int) -> Image.Image:
    """Resize to cover target dimensions, then center-crop exactly."""
    if target_width <= 0 or target_height <= 0:
        raise ValueError("target width/height must be positive")
    if img.size == (target_width, target_height):
        return img
    scale = max(target_width / img.width, target_height / img.height)
    resized = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left = max(0, (resized.width - target_width) // 2)
    top = max(0, (resized.height - target_height) // 2)
    return resized.crop((left, top, left + target_width, top + target_height))


def _jpeg_candidate(image, max_bytes, subsampling):
    """Find the highest fitting quality in this sampling mode."""
    def encode(quality):
        output = BytesIO()
        try:
            image.save(output, 'JPEG', quality=quality, optimize=True, subsampling=subsampling)
        except OSError:
            # libjpeg's optimized pass can fail for a valid, detailed image.
            # Retry the same quality and sampling without the entropy optimizer.
            output = BytesIO()
            image.save(output, 'JPEG', quality=quality, optimize=False, subsampling=subsampling)
        return output.getvalue()

    low, high = 25, 95
    best = None
    while low <= high:
        quality = (low + high) // 2
        data = encode(quality)
        if len(data) <= max_bytes:
            best = quality, data
            low = quality + 1
        else:
            high = quality - 1
    # Encoded size can be slightly non-monotonic near the budget.
    if best:
        for quality in range(best[0] + 1, min(95, best[0] + 2) + 1):
            data = encode(quality)
            if len(data) <= max_bytes:
                best = quality, data
    return best


def _best_jpeg(image, max_bytes, pixel_box):
    quality = EncodingQuality(image, logo_bounds(pixel_box))
    candidates = []
    for subsampling in (2, 1, 0):
        result = _jpeg_candidate(image, max_bytes, subsampling)
        if result is None:
            continue
        level, data = result
        with Image.open(BytesIO(data)) as decoded:
            candidates.append((quality.loss(decoded), len(data), level, subsampling, data))
    return min(candidates, key=lambda item: item[:2]) if candidates else None


def compress(
    input_path: str,
    output_path: str,
    target_kb: int = 200,
    target_width: Optional[int] = None,
    target_height: Optional[int] = None,
    *,
    pixel_box=None,
) -> str:
    """压缩到目标 KB。返回最终输出路径。"""
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input not found: {input_path}")
    if target_kb <= 0:
        raise ValueError("target_kb must be positive")
    if bool(target_width) != bool(target_height):
        raise ValueError("target_width and target_height must be provided together")

    with Image.open(input_path) as opened:
        img = opened.convert("RGB")
    if target_width and target_height:
        img = resize_cover(img, target_width, target_height)

    output = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    scales = [1.0] if target_width and target_height else [0.9**index for index in range(10)]
    for scale in scales:
        scaled = img
        if scale < 1.0:
            new_size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
            scaled = img.resize(new_size, Image.LANCZOS)
        result = _best_jpeg(scaled, target_kb * 1024, pixel_box if scale == 1.0 else None)
        if result is None:
            continue
        _, size, quality, subsampling, data = result
        with tempfile.TemporaryDirectory(prefix='.jpeg-', dir=os.path.dirname(output)) as folder:
            candidate = os.path.join(folder, 'delivery.jpg')
            with open(candidate, 'wb') as stream:
                stream.write(data)
            os.replace(candidate, output)
        sampling = ('4:4:4', '4:2:2', '4:2:0')[subsampling]
        print(f"✅ {input_path} → {output} ({scaled.width}x{scaled.height}, {size/1024:.1f} KB, q={quality}, {sampling})")
        return output

    exact = f"{target_width}x{target_height}" if target_width and target_height else "未指定"
    raise ValueError(f"cannot satisfy target_kb={target_kb} at exact_size={exact}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="输入图片路径")
    parser.add_argument("output", help="输出图片路径（.jpg）")
    parser.add_argument("--target-kb", type=int, default=200, help="目标大小（KB）")
    parser.add_argument("--target-width", type=int, help="导出目标宽度")
    parser.add_argument("--target-height", type=int, help="导出目标高度")
    args = parser.parse_args()

    try:
        compress(args.input, args.output, args.target_kb, args.target_width, args.target_height)
        sys.exit(0)
    except FileNotFoundError as e:
        print(f"🔴 {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"🔴 压缩失败：{e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
