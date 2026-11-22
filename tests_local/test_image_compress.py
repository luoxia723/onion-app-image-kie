"""Verify delivery JPEG constraints and useful quality against the old encoder."""
from PIL import Image, ImageChops, ImageDraw, ImageStat

from scripts.image_compress import compress


def test_jpeg_uses_budget_to_retain_color_edges(tmp_path):
    source, baseline, target = (tmp_path / name for name in ('source.png', 'legacy.jpg', 'delivery.jpg'))
    original = Image.new('RGB', (320, 211), '#fcf5e9')
    draw = ImageDraw.Draw(original)
    for x in range(5, 310, 9):
        draw.rectangle((x, 20, x+2, 190), fill='#dc193b')
        draw.rectangle((x+4, 20, x+6, 190), fill='#1267d2')
    original.save(source, 'PNG')
    original.save(baseline, 'JPEG', quality=85, optimize=True, subsampling=2)
    compress(str(source), str(target), 80-1/1024, 320, 211)
    with Image.open(target) as new, Image.open(baseline) as old:
        assert new.format == 'JPEG' and new.size == (320, 211)
        new_error = sum(ImageStat.Stat(ImageChops.difference(original, new)).mean)
        old_error = sum(ImageStat.Stat(ImageChops.difference(original, old)).mean)
        assert new_error < old_error / 2
    assert target.stat().st_size < 80*1024
