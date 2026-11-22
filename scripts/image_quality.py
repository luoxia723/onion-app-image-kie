"""Compare encodings from the same final-sized image using Pillow."""
from PIL import Image, ImageChops, ImageFilter, ImageStat


_DETAIL_WEIGHTS = [min(255, 8 * abs(level - 128)) for level in range(256)]


def tight_png_budget(width, height, byte_limit):
    """Flag a PNG budget of at most 0.4 bytes per pixel."""
    return byte_limit is not None and byte_limit * 5 <= 2 * width * height


def _detail(rgb):
    luminance = rgb.convert('L')
    return ImageChops.subtract(luminance, luminance.filter(ImageFilter.GaussianBlur(1)), offset=128)


def _error(reference, actual):
    return sum(ImageStat.Stat(ImageChops.difference(reference, actual)).mean) / len(reference.getbands())


class EncodingQuality:
    """Rank visual changes, emphasizing fine edges and any known Logo box."""

    def __init__(self, image, logo_box=None):
        self.reference = image.convert('RGBA')
        self.alpha = self.reference.getchannel('A')
        self.clear = self.alpha.point([255]+[0]*255)
        self.opaque = self.alpha.point([0]*255+[255])
        self.transparent = self.alpha.getextrema() != (255, 255)
        self.backgrounds = [Image.new('RGBA', image.size, color) for color in ('white', 'black')] if self.transparent else [None]
        self.colors = [self._visible(self.reference, background) for background in self.backgrounds]
        self.details = [_detail(rgb) for rgb in self.colors]
        self.detail_weights = [detail.point(_DETAIL_WEIGHTS) for detail in self.details]
        # The floor limits the influence of isolated edges in nearly flat images.
        self.detail_weight_means = [max(8, ImageStat.Stat(weights).mean[0]) for weights in self.detail_weights]
        self.logo_box = logo_box

    @staticmethod
    def _visible(image, background):
        return (image if background is None else Image.alpha_composite(background, image)).convert('RGB')

    def alpha_status(self, decoded):
        """Return whether clear/opaque pixels survive and whether alpha is exact."""
        actual = decoded.convert('RGBA').getchannel('A')
        delta = ImageChops.difference(self.alpha, actual)
        if not delta.getbbox():
            return True, True
        protected = ImageChops.lighter(self.clear, self.opaque)
        return not ImageChops.multiply(delta, protected).getbbox(), False

    def loss(self, candidate):
        if candidate.size != self.reference.size:
            raise ValueError('Candidate size must match reference')
        rgba = candidate.convert('RGBA')
        worst = 0
        for background, reference, detail, weights, weight_mean in zip(
                self.backgrounds, self.colors, self.details, self.detail_weights, self.detail_weight_means):
            visible = self._visible(rgba, background)
            detail_error = ImageChops.difference(detail, _detail(visible))
            weighted_error = ImageStat.Stat(ImageChops.multiply(detail_error, weights)).mean[0]
            error = (_error(reference, visible) + 2 * ImageStat.Stat(detail_error).mean[0]
                     + 0.5 * weighted_error * 255 / weight_mean)
            if self.logo_box:
                error += 0.5 * _error(reference.crop(self.logo_box), visible.crop(self.logo_box))
            worst = max(worst, error)
        return worst


def logo_bounds(pixel_box):
    if pixel_box is None:
        return None
    x, y, width, height = pixel_box
    return x, y, x + width, y + height
