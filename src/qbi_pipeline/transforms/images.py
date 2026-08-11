"""
Phase 4: image optimization and metadata stripping.

Only ever rewrites the staged copy; vault originals are never modified.
"""

from pathlib import Path

from PIL import Image, ImageOps

# Images wider than this are downscaled for web delivery.
MAX_IMAGE_WIDTH = 1200  # pixels

OPTIMIZABLE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}

# Ceiling on total pixels before an image is treated as hostile rather than
# merely large. Guards against decompression bombs, since vault images are
# untrusted input. 8000x8000 is far beyond any real lab photograph.
MAX_IMAGE_PIXELS = 64_000_000


def strip_exif(img):
    """
    Return a copy of the image carrying no EXIF metadata.

    Phone photographs of lab notebooks embed GPS coordinates, device serial
    numbers and timestamps. Publishing those alongside research notes discloses
    where and when the work happened, so stripping is unconditional and does
    not depend on whether resizing or recompression is enabled (S-6).

    Pillow carries metadata in `img.info` and writes it back out on save (the
    JPEG encoder reads `info['exif']` even when no exif argument is passed), so
    clearing that dict is what actually drops it. Copying rather than rebuilding
    from pixel data keeps palettes and transparency intact.
    """
    clean = img.copy()
    clean.info = {}
    return clean


def optimize_image(image_path):
    """
    Strip metadata from an image, and resize/compress it for web delivery.

    Always rewrites the staged copy, never the vault original. Failures are
    non-fatal: a single unreadable image must not take down a build, so the
    file is left as-is and the build continues.
    """
    image_path = Path(image_path)
    ext = image_path.suffix.lower()
    if ext not in OPTIMIZABLE_EXTENSIONS:
        return False

    try:
        with Image.open(image_path) as img:
            if img.width * img.height > MAX_IMAGE_PIXELS:
                print(f"  [skip] refusing oversized image ({img.width}x{img.height}): {image_path}")
                return False

            # Force a full read before saving; a streamed PNG otherwise fails
            # on write with an _idat error.
            img.load()

            # Bake EXIF rotation into the pixels before the orientation tag is
            # discarded, or stripped images come out sideways.
            img = ImageOps.exif_transpose(img)

            if img.width > MAX_IMAGE_WIDTH:
                ratio = MAX_IMAGE_WIDTH / img.width
                img = img.resize((MAX_IMAGE_WIDTH, int(img.height * ratio)), Image.LANCZOS)

            img = strip_exif(img)

            if ext in {'.jpg', '.jpeg'}:
                img.save(image_path, quality=80, optimize=True)
            elif ext == '.png':
                img.save(image_path, optimize=True)
            elif ext == '.webp':
                img.save(image_path, quality=80)

        return True

    except Exception as e:
        print(f"  [skip] couldn't optimize {image_path}: {e}")
        return False
