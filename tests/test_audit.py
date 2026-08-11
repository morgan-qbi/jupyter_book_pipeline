"""Tests for vault hygiene checks.

The two checks here catch link rot that the build itself cannot: a link that
resolves to a real page but lands at the top of it because the heading was
renumbered, and a page link that points at nothing at all.
"""

import pytest

from qbi_pipeline.audit.checks import (
    check_broken_anchors,
    check_broken_references,
    check_invalid_notebooks,
    collect_anchors,
    get_all_files,
    iter_markdown_links,
)


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def vault(tmp_path):
    return tmp_path / "vault"


def anchors(vault):
    return check_broken_anchors(get_all_files(vault), vault)


def refs(vault):
    return check_broken_references(get_all_files(vault), vault)


# =============================================================================
# Link scanning
# =============================================================================

def test_balanced_parens_in_a_filename_survive():
    """`Linear_ramp_B(5100).png` is a real filename in this vault, and a
    `\\(([^)]+)\\)` regex truncates it at the first `)` -- then reports a
    broken reference to a file nobody ever wrote."""
    found = list(iter_markdown_links("![](attachments/Linear_ramp_B(5100).png)"))
    assert found == [("!", "", "attachments/Linear_ramp_B(5100).png")]


def test_plain_links_and_images_are_distinguished():
    found = list(iter_markdown_links("[text](a.md) and ![alt](b.png)"))
    assert found == [("", "text", "a.md"), ("!", "alt", "b.png")]


def test_unterminated_link_yields_no_destination():
    """The naive regex ran past the end of the link and swallowed the next
    lines into the filename it reported."""
    found = list(iter_markdown_links("![alt](app://host/x.png\n\n# Next Heading\n"))
    assert found == [("!", "alt", None)]


def test_unterminated_link_is_reported(vault):
    write(vault / "Log.md", "![report](app://host/main_report.png\n\n# 2025_09_30\n")

    found = refs(vault)
    assert len(found) == 1
    assert found[0]["type"] == "unterminated_link"
    assert "closing parenthesis" in found[0]["suggestion"]


# =============================================================================
# Anchor collection
# =============================================================================

def test_headings_become_anchors():
    assert collect_anchors("# Title\n\n## Setup Steps\n") == {"title", "setup-steps"}


def test_numbered_headings_get_the_myst_id_prefix():
    """Lab protocols number their headings, so this is the common case."""
    assert "id-1-overview" in collect_anchors("## 1. Overview\n")


def test_repeated_headings_are_disambiguated():
    """MyST appends -1 to a duplicate, and a link to the second one is valid."""
    found = collect_anchors("## Results\n\ntext\n\n## Results\n")
    assert found == {"results", "results-1"}


def test_headings_inside_code_fences_are_not_anchors():
    content = "# Real\n\n```markdown\n# Example Heading\n```\n"
    assert collect_anchors(content) == {"real"}


def test_myst_explicit_targets_count_as_anchors():
    assert "my-figure" in collect_anchors("(my-figure)=\n## A Figure\n")


def test_trailing_hashes_are_not_part_of_the_heading():
    assert collect_anchors("## Setup ##\n") == {"setup"}


# =============================================================================
# Broken anchors
# =============================================================================

def test_wikilink_to_a_missing_heading_is_reported(vault):
    write(vault / "Protocol.md", "## 5. Degauss the shield\n")
    write(vault / "Manual.md", "See [[Protocol#6. Degauss the shield]]\n")

    found = anchors(vault)
    assert len(found) == 1
    assert found[0]["source_file"] == "Manual.md"
    assert "Protocol.md" in found[0]["suggestion"]


def test_wikilink_to_a_present_heading_is_clean(vault):
    write(vault / "Protocol.md", "## 5. Degauss the shield\n")
    write(vault / "Manual.md", "See [[Protocol#5. Degauss the shield]]\n")

    assert anchors(vault) == []


def test_same_page_anchor_is_checked_against_its_own_headings(vault):
    write(vault / "Protocol.md", "## Setup\n\nSee [[#Teardown]]\n")

    found = anchors(vault)
    assert len(found) == 1
    assert found[0]["source_file"] == "Protocol.md"


def test_alias_does_not_hide_the_heading(vault):
    write(vault / "Protocol.md", "## Setup\n")
    write(vault / "Manual.md", "See [[Protocol#Teardown|the teardown]]\n")

    assert len(anchors(vault)) == 1


def test_missing_page_is_left_to_the_reference_check(vault):
    """One issue per problem: a link to a nonexistent page is a broken
    reference, and reporting it twice makes a report people stop reading."""
    write(vault / "Manual.md", "See [[No Such Page#Anything]]\n")

    assert anchors(vault) == []


def test_markdown_anchor_link_is_checked(vault):
    write(vault / "Protocol.md", "## Setup\n")
    write(vault / "Manual.md", "See [setup](Protocol.md#teardown)\n")

    assert len(anchors(vault)) == 1


def test_markdown_anchor_link_that_resolves_is_clean(vault):
    write(vault / "Protocol.md", "## Setup\n")
    write(vault / "Manual.md", "See [setup](Protocol.md#setup)\n")

    assert anchors(vault) == []


def test_external_urls_with_fragments_are_ignored(vault):
    write(vault / "Manual.md", "See [spec](https://example.org/doc#section)\n")

    assert anchors(vault) == []


def test_block_references_are_not_treated_as_headings(vault):
    """`[[Page#^block-id]]` addresses a paragraph, not a heading."""
    write(vault / "Protocol.md", "Some paragraph ^abc123\n")
    write(vault / "Manual.md", "See [[Protocol#^abc123]]\n")

    assert anchors(vault) == []


def test_anchors_in_code_fences_are_not_reported(vault):
    write(vault / "Protocol.md", "## Setup\n")
    write(vault / "Manual.md", "```\nSee [[Protocol#Nope]]\n```\n")

    assert anchors(vault) == []


def test_confidential_folders_never_reach_the_report(vault):
    """Audit reports are written to disk and shared (S-1)."""
    write(vault / "5_confidential" / "Salaries.md", "See [[Salaries#Nope]]\n")
    write(vault / "Public.md", "## Setup\n")

    assert anchors(vault) == []


# =============================================================================
# Notebooks that cannot be published
# =============================================================================

def notebooks(vault):
    return check_invalid_notebooks(get_all_files(vault), vault)


def test_empty_json_notebook_is_reported(vault):
    """`{}` is valid JSON and passes any JSON check, but has no cells. The
    build skips it silently into a log nobody reads."""
    write(vault / "analysis.ipynb", "{}")

    found = notebooks(vault)
    assert len(found) == 1
    assert found[0]["file"] == "analysis.ipynb"


def test_unparseable_notebook_is_reported(vault):
    write(vault / "broken.ipynb", "not json at all")

    assert len(notebooks(vault)) == 1


def test_valid_notebook_is_clean(vault):
    write(
        vault / "good.ipynb",
        '{"cells": [], "nbformat": 4, "nbformat_minor": 5, "metadata": {}}',
    )

    assert notebooks(vault) == []


def test_markdown_is_not_checked_as_a_notebook(vault):
    write(vault / "notes.md", "# Notes\n")

    assert notebooks(vault) == []


# =============================================================================
# Broken page links
# =============================================================================

def test_wikilink_to_a_missing_page_is_reported(vault):
    write(vault / "Manual.md", "See [[Build Guide]]\n")

    found = [i for i in refs(vault) if i["type"] == "wikilink"]
    assert len(found) == 1
    assert "Build Guide" in found[0]["reference"]


def test_wikilink_to_an_existing_page_is_clean(vault):
    write(vault / "1_eln" / "Build Guide.md", "# Build Guide\n")
    write(vault / "Manual.md", "See [[Build Guide]]\n")

    assert refs(vault) == []


def test_underscored_link_matches_a_spaced_filename(vault):
    """A name copied out of the published site comes back underscored."""
    write(vault / "1_eln" / "Build Guide.md", "# Build Guide\n")
    write(vault / "Manual.md", "See [[Build_Guide]]\n")

    assert refs(vault) == []


def test_image_embeds_are_not_reported_as_page_links(vault):
    write(vault / "plot.png", "")
    write(vault / "Manual.md", "![[plot.png]]\n")

    assert refs(vault) == []


def test_a_link_with_a_heading_is_checked_by_page_not_heading(vault):
    """The page half is the reference check's business; the heading half is
    the anchor check's. This one has a good page and a bad heading."""
    write(vault / "Protocol.md", "## Setup\n")
    write(vault / "Manual.md", "See [[Protocol#Teardown]]\n")

    assert refs(vault) == []
    assert len(anchors(vault)) == 1
