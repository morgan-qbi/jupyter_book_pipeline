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


def to_displayable(img):
    """
    Reduce an image to a mode PNG can store and a browser can display.

    Scientific TIFFs are routinely 16-bit or float (microscopy cameras), which
    PNG cannot represent as-is. Rescaling to 8-bit is lossy in the measurement
    sense: it maps the image's own min..max onto 0..255, so the result is fine
    to look at but must not be read off quantitatively. The original stays in
    the vault, untouched, for anyone who needs the real values.
    """
    if img.mode in ('I;16', 'I;16B', 'I;16L', 'I', 'F'):
        extrema = img.getextrema()
        low, high = extrema if isinstance(extrema, tuple) else (0, 255)
        span = (high - low) or 1
        img = img.point(lambda value: (value - low) * 255.0 / span)
        return img.convert('L')

    if img.mode in ('RGB', 'RGBA', 'L', 'LA', 'P'):
        return img

    return img.convert('RGB')


def convert_image(source, output_path):
    """
    Convert an image to a web-renderable format, writing it to `output_path`.

    Used for formats no browser displays inline -- TIFF above all. The staged
    file is renamed by policy.staged_suffix, and the vault original is never
    modified.

    Multi-page TIFFs keep only their first frame; the rest are not reachable
    from a single `<img>` anyway, and the original remains in the vault.
    """
    source = Path(source)
    output_path = Path(output_path)

    try:
        with Image.open(source) as img:
            if img.width * img.height > MAX_IMAGE_PIXELS:
                print(f"  [skip] refusing oversized image ({img.width}x{img.height}): {source}")
                return False

            frames = getattr(img, 'n_frames', 1)
            if frames > 1:
                print(f"  [note] {source.name}: keeping first of {frames} frames")

            img.load()
            img = ImageOps.exif_transpose(img)
            img = to_displayable(img)

            if img.width > MAX_IMAGE_WIDTH:
                ratio = MAX_IMAGE_WIDTH / img.width
                img = img.resize((MAX_IMAGE_WIDTH, int(img.height * ratio)), Image.LANCZOS)

            img = strip_exif(img)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(output_path, format='PNG', optimize=True)

        return True

    except Exception as e:
        print(f"  [skip] couldn't convert {source}: {e}")
        return False


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
