"""Characterization tests: Obsidian link conversion (Phase 2).

This is the most regex-heavy part of the pipeline and the part most likely to
shift during the refactor, so it gets the densest coverage.
"""

import pytest

from qbi_pipeline.transforms import (
    convert_obsidian_links,
    convert_wikilinks,
    rewrite_absolute_paths,
)
from qbi_pipeline.transforms.links import slugify_heading

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


# =============================================================================
# Obsidian-style loose paths in standard markdown images
# =============================================================================

def test_markdown_image_path_wrong_for_this_page_is_resolved_by_search(tmp_path):
    """Obsidian resolves link paths by searching the vault, not by treating
    them as literal relative paths. A note in 2025/ can write
    `attachments/plot.png` for a file in the *parent* folder's attachments,
    which renders fine in Obsidian and 404s once published.

    Found by running a real vault through the pipeline: 33 of 225 image
    references were broken this way.
    """
    index = {"plot.png": "eln/attachments/plot.png"}
    paths = {"eln/attachments/plot.png"}

    out = rewrite_absolute_paths(
        "![](attachments/plot.png)", "eln/2025/2025_06.md", paths, index
    )
    assert out == "![](../attachments/plot.png)"


def test_correct_relative_path_is_left_alone(tmp_path):
    index = {"plot.png": "eln/2025/attachments/plot.png"}
    paths = {"eln/2025/attachments/plot.png"}

    src = "![](attachments/plot.png)"
    assert rewrite_absolute_paths(src, "eln/2025/note.md", paths, index) == src


def test_vault_root_path_still_wins_over_search(tmp_path):
    index = {"plot.png": "elsewhere/plot.png"}
    paths = {"1_eln/plot.png", "elsewhere/plot.png"}

    out = rewrite_absolute_paths("![](1_eln/plot.png)", "2_data/note.md", paths, index)
    assert out == "![](../1_eln/plot.png)"


def test_unresolvable_image_path_is_left_as_written(tmp_path):
    out = rewrite_absolute_paths("![](attachments/ghost.png)", "note.md", set(), {})
    assert out == "![](attachments/ghost.png)"


def test_search_fallback_is_skipped_without_an_index():
    """Back-compat: the index argument is optional."""
    src = "![](attachments/plot.png)"
    assert rewrite_absolute_paths(src, "eln/note.md", set()) == src


def test_plain_link_with_a_loose_path_is_also_resolved():
    """The same loose-path problem applies to links, not just images: a note
    can link a notebook by a path relative to the project root."""
    index = {"calibration.ipynb": "proj/3_code/calibration.ipynb"}
    paths = {"proj/3_code/calibration.ipynb"}

    out = rewrite_absolute_paths(
        "[cal](3_code/calibration.ipynb)", "proj/1_eln/manual.md", paths, index
    )
    assert out == "[cal](../3_code/calibration.ipynb)"


def test_plain_link_keeps_its_text_and_stays_a_link():
    index = {"data.csv": "proj/2_data/data.csv"}
    paths = {"proj/2_data/data.csv"}

    out = rewrite_absolute_paths("[the data](data.csv)", "proj/1_eln/n.md", paths, index)
    assert out.startswith("[the data](")
    assert not out.startswith("![")


def test_image_syntax_is_preserved_through_the_fallback():
    index = {"plot.png": "eln/attachments/plot.png"}
    paths = {"eln/attachments/plot.png"}

    out = rewrite_absolute_paths("![alt](attachments/plot.png)", "eln/2025/n.md", paths, index)
    assert out == "![alt](../attachments/plot.png)"


def test_anchors_and_mailto_are_untouched():
    for url in ("#results", "mailto:ada@qbi.org", "//cdn.example.org/x.js"):
        src = f"[x]({url})"
        assert rewrite_absolute_paths(src, "n.md", set(), {}) == src


# =============================================================================
# Page-to-page wikilinks
# =============================================================================

PAGES = {
    "Build_Guide.md": "1_eln/Build_Guide.md",
    "README_GUI.md": "3_code/README_GUI.md",
    "dup.md": ["a/dup.md", "b/dup.md"],
}
PAGE_PATHS = {"1_eln/Build_Guide.md", "3_code/README_GUI.md", "a/dup.md", "b/dup.md"}


def wiki(content, current="1_eln/User_Manual.md"):
    return convert_wikilinks(content, current, PAGES, PAGE_PATHS)


def test_bare_wikilink_becomes_a_page_link():
    """These rendered as literal [[double brackets]] on the published site."""
    assert wiki("see [[Build Guide]]") == "see [Build Guide](Build_Guide.md)"


def test_wikilink_resolves_across_folders():
    """Link text is the target as written, which is what Obsidian displays."""
    assert wiki("see [[README_GUI]]") == "see [README_GUI](../3_code/README_GUI.md)"


def test_wikilink_alias_is_used_as_link_text():
    assert wiki("see [[Build Guide|the build guide]]") == "see [the build guide](Build_Guide.md)"


def test_wikilink_to_a_heading_gets_an_anchor():
    out = wiki("see [[Build Guide#Optical Path]]")
    assert out == "see [Build Guide > Optical Path](Build_Guide.md#optical-path)"


def test_wikilink_alias_wins_over_the_heading_label():
    out = wiki("see [[Build Guide#Optical Path|optics]]")
    assert out == "see [optics](Build_Guide.md#optical-path)"


def test_same_page_heading_link():
    assert wiki("see [[#Setup Steps]]") == "see [Setup Steps](#setup-steps)"


@pytest.mark.parametrize("heading,anchor", [
    ("Setup Steps", "setup-steps"),
    ("Start-up", "start-up"),
    ("1. What the instrument does", "id-1-what-the-instrument-does"),
    ("4. Step 1 — Check the magnetometer", "id-4-step-1-check-the-magnetometer"),
    ("5. Step 2 - Degauss the shield (monthly)", "id-5-step-2-degauss-the-shield-monthly"),
])
def test_heading_slugs_match_myst(heading, anchor):
    """Verified against mystmd 1.6.4. Numbered headings are the norm in lab
    protocols, and MyST prefixes those ids with `id-` because a bare numeric
    HTML identifier is invalid -- getting it wrong breaks most anchors."""
    assert slugify_heading(heading) == anchor


def test_explicit_path_wikilink():
    assert wiki("see [[3_code/README_GUI.md]]") == "see [3_code/README_GUI.md](../3_code/README_GUI.md)"


def test_unresolvable_wikilink_is_left_as_written():
    """Visible on the page beats silently vanishing."""
    assert wiki("see [[No Such Page]]") == "see [[No Such Page]]"


def test_image_embeds_are_not_treated_as_page_links():
    """convert_obsidian_links owns `![[...]]`; this must not eat it."""
    src = "![[plot.png]]"
    assert wiki(src) == src


def test_pandas_indexing_in_a_code_block_is_not_a_wikilink():
    """`df[['a', 'b']]` is column selection. This lab writes a lot of pandas,
    and a vault with a matching page name would have had its published code
    silently rewritten into a link."""
    index = {"dup.md": "a/dup.md"}
    src = "```python\ndf[['dup']]\n```\n"
    assert convert_wikilinks(src, "n.md", index, {"a/dup.md"}) == src


def test_pandas_indexing_in_an_inline_code_span_is_left_alone():
    index = {"dup.md": "a/dup.md"}
    src = "use `df[['dup']]` for that\n"
    assert convert_wikilinks(src, "n.md", index, {"a/dup.md"}) == src


def test_a_wikilink_after_a_code_block_still_converts():
    """Skipping code must not skip the rest of the document."""
    out = wiki("```python\nx = 1\n```\n\nsee [[Build Guide]]\n")
    assert "[Build Guide](Build_Guide.md)" in out


def test_ambiguous_wikilink_uses_the_first_and_warns(capsys):
    out = wiki("see [[dup]]")
    assert out == "see [dup](../a/dup.md)"
    assert "several" in capsys.readouterr().out
