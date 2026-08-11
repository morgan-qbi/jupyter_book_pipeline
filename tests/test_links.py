"""Characterization tests: Obsidian link conversion (Phase 2).

This is the most regex-heavy part of the pipeline and the part most likely to
shift during the refactor, so it gets the densest coverage.
"""

from qbi_pipeline.transforms import convert_obsidian_links, rewrite_absolute_paths

INDEX = {
    "chart.png": "1_eln/chart.png",
    "model.stl": "4_aux/model.stl",
    "dup.png": ["a/dup.png", "b/dup.png"],
}
PATHS = {"1_eln/chart.png", "4_aux/model.stl", "a/dup.png", "b/dup.png"}


def convert(content, current_file="notes.md"):
    return convert_obsidian_links(content, current_file, INDEX, PATHS)


# =============================================================================
# Vault-wide lookup by bare filename
# =============================================================================

def test_bare_image_filename_resolves_to_relative_markdown_image():
    assert convert("![[chart.png]]") == "![](1_eln/chart.png)"


def test_lookup_is_relative_to_the_referencing_file():
    assert convert("![[chart.png]]", current_file="1_eln/notes.md") == "![](chart.png)"


def test_deeply_nested_source_walks_back_up():
    out = convert("![[chart.png]]", current_file="2_data/sub/notes.md")
    assert out == "![](../../1_eln/chart.png)"


def test_non_image_becomes_a_download_link():
    assert convert("![[model.stl]]") == "[Download model.stl](4_aux/model.stl)"


def test_filename_with_spaces_is_sanitized_before_lookup():
    index = {"my_chart.png": "1_eln/my_chart.png"}
    out = convert_obsidian_links("![[my chart.png]]", "notes.md", index, {"1_eln/my_chart.png"})
    assert out == "![](1_eln/my_chart.png)"


def test_unresolvable_reference_is_left_verbatim():
    """Unresolved embeds stay as raw ![[...]] so they are visible in the built
    site rather than silently vanishing."""
    assert convert("![[nope.png]]") == "![[nope.png]]"


def test_duplicate_filenames_resolve_to_the_first_match():
    assert convert("![[dup.png]]") == "![](a/dup.png)"


# =============================================================================
# Explicit paths
# =============================================================================

def test_explicit_vault_root_path_is_rewritten_as_relative():
    out = convert("![[1_eln/chart.png]]", current_file="2_data/notes.md")
    assert out == "![](../1_eln/chart.png)"


def test_explicit_path_already_relative_is_kept():
    out = convert("![[chart.png]]", current_file="1_eln/notes.md")
    assert out == "![](chart.png)"


def test_unknown_explicit_path_is_passed_through_sanitized():
    out = convert("![[some folder/ghost.png]]")
    assert out == "![](some_folder/ghost.png)"


def test_multiple_embeds_in_one_document():
    out = convert("A ![[chart.png]] B ![[model.stl]] C")
    assert out == "A ![](1_eln/chart.png) B [Download model.stl](4_aux/model.stl) C"


# =============================================================================
# Absolute path rewriting for standard markdown images
# =============================================================================

def test_absolute_markdown_image_is_made_relative():
    out = rewrite_absolute_paths("![alt](1_eln/chart.png)", "2_data/notes.md", PATHS)
    assert out == "![alt](../1_eln/chart.png)"


def test_alt_text_is_preserved():
    out = rewrite_absolute_paths("![my alt](1_eln/chart.png)", "notes.md", PATHS)
    assert out == "![my alt](1_eln/chart.png)"


def test_external_image_urls_are_skipped():
    for url in ("https://example.org/a b.png", "http://example.org/x.png", "data:image/png;base64,AAA"):
        src = f"![alt]({url})"
        assert rewrite_absolute_paths(src, "notes.md", PATHS) == src
