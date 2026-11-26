"""Choose a brand mark against its exact background at delivery size."""
from PIL import Image


def _linear(value):
    value /= 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


_LINEAR = tuple(_linear(value) for value in range(256))


def _luminance(color):
    red, green, blue = color[:3]
    return .2126 * _LINEAR[red] + .7152 * _LINEAR[green] + .0722 * _LINEAR[blue]


def _contrast(image, logo, origin):
    x, y = origin
    # Both registered marks have the same mascot on the left. Compare the
    # legibility of the right-hand wordmark, primarily at solid stroke pixels.
    start = int(logo.width * .28)
    wordmark = logo.crop((start, 0, logo.width, logo.height))
    background = image.crop((x + start, y, x + logo.width, y + logo.height))
    if background.getchannel('A').getextrema() != (255, 255):
        background = Image.alpha_composite(Image.new('RGBA', background.size, 'white'), background)
    painted = Image.alpha_composite(background, wordmark).load()
    background = background.load()
    glyph = wordmark.load()
    step = max(1, wordmark.width // 180)
    ratios = []
    for row in range(0, wordmark.height, step):
        for column in range(0, wordmark.width, step):
            if glyph[column, row][3] >= 160:
                before = _luminance(background[column, row])
                after = _luminance(painted[column, row])
                ratios.append((max(before, after) + .05) / (min(before, after) + .05))
    if not ratios:
        return (0, 0)
    # Prefer the variant with fewer weak strokes on mixed backgrounds. Cap
    # the average so a few very high-contrast strokes cannot dominate it.
    return (sum(ratio >= 4.5 for ratio in ratios) / len(ratios),
            sum(min(ratio, 7) for ratio in ratios) / len(ratios))


def choose_variant(image, candidates):
    if len(candidates) == 1:
        return candidates[0]
    return max(candidates, key=lambda candidate: _contrast(image, candidate[1], candidate[2]))
