"""Tests for image format conversion (TIFF -> PNG).

TIFFs are common in microscopy and no browser renders them inline. They are
re-encoded into PNG on the way into staging, which renames the file -- so the
rename has to reach every place a link can be resolved. Obsidian embeds carry
a bare filename with no path, so the vault index is the load-bearing part.
"""

import pytest
from PIL import Image

from qbi_pipeline.index import build_file_index
from qbi_pipeline.naming import staged_relative_path
from qbi_pipeline.policy import staged_suffix
from qbi_pipeline.staging import claim_staging_directory, sync_vault
from qbi_pipeline.transforms import convert_image, process_markdown_content
from qbi_pipeline.transforms.images import to_displayable


def write(path, content="content\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_tiff(path, size=(60, 40), mode="RGB", color=(10, 120, 200)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, size, color).save(path, format="TIFF")
    return path


@pytest.fixture
def staging(tmp_path):
    out = tmp_path / "out"
    claim_staging_directory(out)
    return out


# =============================================================================
# Name mapping
# =============================================================================

@pytest.mark.parametrize("suffix,expected", [
    (".tif", ".png"),
    (".tiff", ".png"),
    (".TIF", ".png"),
    (".png", ".png"),
    (".md", ".md"),
])
def test_staged_suffix(suffix, expected):
    assert staged_suffix(suffix) == expected


@pytest.mark.parametrize("raw,expected", [
    ("attachments/scan.tif", "attachments/scan.png"),
    ("a folder/my scan.tiff", "a_folder/my_scan.png"),
    ("notes.md", "notes.md"),
    ("attachments/photo.png", "attachments/photo.png"),
])
def test_staged_relative_path(raw, expected):
    assert staged_relative_path(raw) == expected


# =============================================================================
# Conversion
# =============================================================================

def test_tiff_is_converted_to_png(tmp_path):
    source = make_tiff(tmp_path / "scan.tif")
    out = tmp_path / "scan.png"

    assert convert_image(source, out) is True
    with Image.open(out) as img:
        assert img.format == "PNG"
        assert img.size == (60, 40)


def test_original_tiff_is_never_modified(tmp_path):
    source = make_tiff(tmp_path / "scan.tif")
    before = source.read_bytes()

    convert_image(source, tmp_path / "scan.png")
    assert source.read_bytes() == before


def test_wide_tiff_is_resized(tmp_path):
    source = make_tiff(tmp_path / "big.tif", size=(2400, 1200))
    out = tmp_path / "big.png"

    convert_image(source, out)
    with Image.open(out) as img:
        assert img.width == 1200


def test_sixteen_bit_tiff_is_reduced_for_display(tmp_path):
    """Microscopy cameras produce 16-bit data PNG cannot store."""
    source = tmp_path / "micro.tif"
    Image.new("I;16", (20, 20), 30000).save(source, format="TIFF")

    assert convert_image(source, tmp_path / "micro.png") is True
    with Image.open(tmp_path / "micro.png") as img:
        assert img.mode in ("L", "P")


def test_to_displayable_rescales_to_full_range(tmp_path):
    img = Image.new("I;16", (4, 4), 1000)
    img.putpixel((0, 0), 0)
    img.putpixel((3, 3), 4000)

    out = to_displayable(img)
    assert out.mode == "L"
    assert out.getextrema() == (0, 255)


def test_corrupt_tiff_does_not_raise(tmp_path):
    source = tmp_path / "broken.tif"
    source.write_bytes(b"not a tiff")
    assert convert_image(source, tmp_path / "broken.png") is False


# =============================================================================
# The rename reaches link resolution
# =============================================================================

def test_index_maps_tif_name_to_staged_png(tmp_path):
    v = tmp_path / "vault"
    make_tiff(v / "attachments" / "scan.tif")

    index, paths = build_file_index(v)

    # Keyed by the name as written in the vault...
    assert "scan.tif" in index
    # ...but pointing at what staging actually contains.
    assert index["scan.tif"] == "attachments/scan.png"
    assert "attachments/scan.png" in paths
    assert "attachments/scan.tif" not in paths


def test_bare_filename_embed_resolves_to_png(tmp_path):
    """Obsidian's smart links carry no path, so this is the common case."""
    v = tmp_path / "vault"
    make_tiff(v / "attachments" / "scan.tif")
    index, paths = build_file_index(v)

    out = process_markdown_content("![[scan.tif]]\n", "1_eln/entry.md", index, paths)
    assert "![](../attachments/scan.png)" in out


def test_explicit_path_embed_resolves_to_png(tmp_path):
    v = tmp_path / "vault"
    make_tiff(v / "attachments" / "scan.tif")
    index, paths = build_file_index(v)

    out = process_markdown_content(
        "![[attachments/scan.tif]]\n", "1_eln/entry.md", index, paths
    )
    assert "![](../attachments/scan.png)" in out


def test_converted_image_renders_inline_not_as_download(tmp_path):
    """A .tif would otherwise fall through to the download-link branch."""
    v = tmp_path / "vault"
    make_tiff(v / "scan.tif")
    index, paths = build_file_index(v)

    out = process_markdown_content("![[scan.tif]]\n", "entry.md", index, paths)
    assert "Download" not in out
    assert "![](scan.png)" in out


# =============================================================================
# End to end through staging
# =============================================================================

def test_sync_publishes_png_and_not_tif(tmp_path, staging):
    v = tmp_path / "vault"
    make_tiff(v / "attachments" / "scan.tif")
    write(v / "entry.md", "See ![[scan.tif]]\n")

    sync_vault(v, staging)

    assert (staging / "attachments" / "scan.png").exists()
    assert not (staging / "attachments" / "scan.tif").exists()
    assert "![](attachments/scan.png)" in (staging / "entry.md").read_text(encoding="utf-8")


def test_converted_asset_is_not_reconverted_every_build(tmp_path, staging):
    v = tmp_path / "vault"
    make_tiff(v / "scan.tif")

    _, first = sync_vault(v, staging)
    assert first["updated"] == 1

    _, second = sync_vault(v, staging)
    assert second["updated"] == 0
    assert second["unchanged"] == 1


def test_edited_tiff_is_reconverted(tmp_path, staging):
    v = tmp_path / "vault"
    target = make_tiff(v / "scan.tif")
    sync_vault(v, staging)

    make_tiff(target, size=(80, 80), color=(200, 10, 10))
    _, changes = sync_vault(v, staging)
    assert changes["updated"] == 1


def test_census_counts_tif_as_published(tmp_path, staging):
    v = tmp_path / "vault"
    make_tiff(v / "scan.tif")

    census, _ = sync_vault(v, staging)
    assert census.published[".tif"] == 1
    assert ".tif" not in census.skipped
