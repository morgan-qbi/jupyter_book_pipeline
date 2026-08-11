"""Tests for image optimization and EXIF stripping (S-6).

Optimization had been switched off behind an early `return`, with its body
parked in a string literal, so lab-notebook photographs shipped full-size with
GPS coordinates intact.
"""

import pytest
from PIL import Image

from qbi_pipeline.transforms import MAX_IMAGE_WIDTH, optimize_image, strip_exif


def make_image(path, size=(80, 60), mode="RGB", color=(120, 30, 200), **save_kwargs):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, size, color).save(path, **save_kwargs)
    return path


# =============================================================================
# Format handling
# =============================================================================

@pytest.mark.parametrize("name", ["photo.jpg", "photo.jpeg", "diagram.png", "shot.webp"])
def test_optimizes_supported_formats(tmp_path, name):
    path = make_image(tmp_path / name)
    assert optimize_image(path) is True
    # Still a readable image of the same dimensions.
    with Image.open(path) as img:
        assert img.size == (80, 60)


@pytest.mark.parametrize("name", ["vector.svg", "animation.gif", "raw.bmp", "notes.md"])
def test_leaves_unsupported_formats_untouched(tmp_path, name):
    path = tmp_path / name
    path.write_bytes(b"original bytes")
    assert optimize_image(path) is False
    assert path.read_bytes() == b"original bytes"


def test_animated_gif_is_not_flattened(tmp_path):
    """GIF is skipped precisely so animation survives."""
    path = tmp_path / "anim.gif"
    frames = [
        Image.new("RGB", (10, 10), (step * 90, 20, 20)).convert("P")
        for step in range(3)
    ]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=100, loop=0)

    with Image.open(path) as img:
        assert img.n_frames == 3, "fixture failed to build an animated GIF"
    before = path.read_bytes()

    assert optimize_image(path) is False
    assert path.read_bytes() == before

    with Image.open(path) as img:
        assert img.n_frames == 3


def test_palette_png_keeps_its_palette(tmp_path):
    """strip_exif copies rather than rebuilding from raw pixel data, so indexed
    colour survives."""
    path = tmp_path / "indexed.png"
    Image.new("RGB", (20, 20), (10, 200, 90)).convert("P").save(path)

    # convert("P") quantizes to the web palette, so read back what was actually
    # stored rather than assuming the requested colour survived.
    with Image.open(path) as img:
        before = img.convert("RGB").getpixel((5, 5))

    assert optimize_image(path) is True

    with Image.open(path) as img:
        assert img.mode == "P"
        assert img.convert("RGB").getpixel((5, 5)) == before


# =============================================================================
# Resizing
# =============================================================================

def test_wide_images_are_resized_preserving_aspect_ratio(tmp_path):
    path = make_image(tmp_path / "wide.jpg", size=(2400, 1200))
    optimize_image(path)

    with Image.open(path) as img:
        assert img.width == MAX_IMAGE_WIDTH
        assert img.height == MAX_IMAGE_WIDTH // 2


def test_narrow_images_are_not_upscaled(tmp_path):
    path = make_image(tmp_path / "small.png", size=(320, 240))
    optimize_image(path)

    with Image.open(path) as img:
        assert img.size == (320, 240)


def test_oversized_images_are_refused(tmp_path, monkeypatch):
    """Decompression-bomb guard: vault images are untrusted input."""
    from qbi_pipeline.transforms import images

    monkeypatch.setattr(images, "MAX_IMAGE_PIXELS", 100)
    path = make_image(tmp_path / "bomb.png", size=(200, 200))

    assert optimize_image(path) is False


# =============================================================================
# EXIF stripping  (the privacy control)
# =============================================================================

def test_exif_is_removed(tmp_path):
    path = tmp_path / "geotagged.jpg"
    exif = Image.Exif()
    exif[0x010F] = "TestCamera"       # Make
    exif[0x0132] = "2026:01:01 12:00:00"  # DateTime
    Image.new("RGB", (60, 40), (10, 20, 30)).save(path, exif=exif)

    with Image.open(path) as before:
        assert dict(before.getexif())

    optimize_image(path)

    with Image.open(path) as after:
        assert not dict(after.getexif())


def test_strip_exif_preserves_pixels(tmp_path):
    original = Image.new("RGB", (8, 8), (5, 100, 200))
    cleaned = strip_exif(original)

    assert cleaned.size == original.size
    assert cleaned.mode == original.mode
    assert cleaned.tobytes() == original.tobytes()


def test_exif_rotation_is_baked_into_pixels_before_stripping(tmp_path):
    """Orientation lives in EXIF, so dropping metadata without applying it
    first would silently rotate published photographs."""
    path = tmp_path / "rotated.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90 CW
    Image.new("RGB", (100, 50), (200, 50, 50)).save(path, exif=exif)

    optimize_image(path)

    with Image.open(path) as img:
        # exif_transpose swaps the axes for orientation 6.
        assert img.size == (50, 100)
        assert not dict(img.getexif())


# =============================================================================
# Failure handling
# =============================================================================

def test_corrupt_image_is_left_in_place_and_does_not_raise(tmp_path):
    """A single unreadable image must not take down a whole build."""
    path = tmp_path / "corrupt.png"
    path.write_bytes(b"this is not a png")

    assert optimize_image(path) is False
    assert path.read_bytes() == b"this is not a png"


def test_missing_file_does_not_raise(tmp_path):
    assert optimize_image(tmp_path / "nope.png") is False
