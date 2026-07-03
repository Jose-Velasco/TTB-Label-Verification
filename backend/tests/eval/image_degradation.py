"""Image degradation utilities for simulating real-world bad photos in eval tests.

Each function takes PNG (or other Pillow-readable) image bytes and returns bytes
in a degraded form, approximating a specific failure mode of phone-camera captures.
"""

import io
import random

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter


def _load(image_bytes: bytes) -> Image.Image:
    return Image.open(io.BytesIO(image_bytes)).convert("RGB")


def _to_png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def apply_gaussian_blur(image_bytes: bytes, radius: float = 8.0) -> bytes:
    """Simulate an out-of-focus camera capture."""
    image = _load(image_bytes)
    blurred = image.filter(ImageFilter.GaussianBlur(radius=radius))
    return _to_png_bytes(blurred)


def apply_low_contrast(image_bytes: bytes, factor: float = 0.3) -> bytes:
    """Simulate poor lighting by flattening contrast."""
    image = _load(image_bytes)
    flattened = ImageEnhance.Contrast(image).enhance(factor)
    return _to_png_bytes(flattened)


def apply_rotation(image_bytes: bytes, degrees: float = 15.0) -> bytes:
    """Simulate a crooked photo angle."""
    image = _load(image_bytes)
    rotated = image.rotate(degrees, expand=True, fillcolor=(255, 255, 255))
    return _to_png_bytes(rotated)


def apply_jpeg_compression_artifacts(image_bytes: bytes, quality: int = 15) -> bytes:
    """Simulate heavy JPEG compression. Returns JPEG bytes, not PNG."""
    image = _load(image_bytes)
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def apply_glare_overlay(image_bytes: bytes, opacity: float = 0.4) -> bytes:
    """Simulate a bright reflection/glare spot over a random region of the image."""
    image = _load(image_bytes)
    width, height = image.size

    # Fixed seed keeps the eval deterministic without touching global random state.
    rng = random.Random(42)
    glare_w = int(width * rng.uniform(0.25, 0.4))
    glare_h = int(height * rng.uniform(0.15, 0.3))
    x = rng.randint(0, max(width - glare_w, 1))
    y = rng.randint(0, max(height - glare_h, 1))

    mask = Image.new("L", (glare_w, glare_h), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, glare_w, glare_h], fill=int(255 * opacity))
    mask = mask.filter(ImageFilter.GaussianBlur(radius=min(glare_w, glare_h) / 4))

    white_patch = Image.new("RGB", (glare_w, glare_h), (255, 255, 255))
    image.paste(white_patch, (x, y), mask)

    return _to_png_bytes(image)
