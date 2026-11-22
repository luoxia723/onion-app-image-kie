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


def test_jpeg_retries_failed_optimized_encoding_within_budget(tmp_path, monkeypatch):
    from io import BytesIO

    source = tmp_path / 'source.png'
    target = tmp_path / 'delivery.jpg'
    Image.new('RGB', (480, 320), '#eb6934').save(source, 'PNG')
    original_save = Image.Image.save
    attempted = []

    def save(image, path, format=None, **options):
        if format == 'JPEG' and isinstance(path, BytesIO):
            attempted.append((options['quality'], options['subsampling'], options['optimize']))
            if options['optimize']:
                path.write(b'partial bytes')
                raise OSError('broken data stream when writing image file')
        return original_save(image, path, format, **options)

    monkeypatch.setattr(Image.Image, 'save', save)
    compress(str(source), str(target), 100-1/1024, 480, 320)

    assert attempted and len(attempted) % 2 == 0
    for first, retry in zip(attempted[::2], attempted[1::2]):
        assert first[:2] == retry[:2] and first[2] and not retry[2]
    assert target.stat().st_size < 100*1024
    with Image.open(target) as result:
        assert result.format == 'JPEG' and result.size == (480, 320)
        assert max(abs(a-b) for a, b in zip(result.getpixel((240, 160)), (235, 105, 52))) <= 2
