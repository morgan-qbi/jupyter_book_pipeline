"""Tests: MyST frontmatter injection (Phase 0a).

S-14 is FIXED. The assertions that previously documented the corruption are
inverted here and now guard against regressing it.
"""

import pytest
import yaml

from qbi_pipeline.transforms import find_frontmatter, has_title, inject_frontmatter


def parse_frontmatter(rendered):
    """Extract and parse the frontmatter block from rendered output."""
    body, _ = find_frontmatter(rendered)
    assert body is not None, f"no frontmatter block found in:\n{rendered!r}"
    return yaml.safe_load(body)


# =============================================================================
# Adding frontmatter where there is none
# =============================================================================

def test_adds_frontmatter_when_absent():
    out = inject_frontmatter("Body text\n", "My Title")
    assert out == "---\ntitle: My Title\n---\n\nBody text\n"


def test_body_is_preserved_verbatim():
    body = "# Heading\n\nSome *markdown* with ![[an embed.png]]\n"
    out = inject_frontmatter(body, "T")
    assert out.endswith(body)


# =============================================================================
# Merging into existing frontmatter  (S-14 regression guards)
# =============================================================================

def test_merges_into_existing_frontmatter_without_corrupting_it():
    """S-14: the title used to be spliced at offset 3, colliding with the
    opening '---' delimiter and producing '---title: X'."""
    original = "---\nauthor: Ada\n---\n\nBody\n"
    out = inject_frontmatter(original, "Injected")

    assert out == "---\ntitle: Injected\nauthor: Ada\n---\n\nBody\n"
    assert not out.startswith("---title:")


def test_merged_frontmatter_still_parses_as_yaml():
    out = inject_frontmatter("---\nauthor: Ada\ntags: [a, b]\n---\n\nBody\n", "Injected")
    parsed = parse_frontmatter(out)

    assert parsed["title"] == "Injected"
    assert parsed["author"] == "Ada"
    assert parsed["tags"] == ["a", "b"]


def test_existing_title_is_left_alone():
    original = "---\ntitle: Kept\nauthor: Ada\n---\n\nBody\n"
    assert inject_frontmatter(original, "Ignored") == original


def test_subtitle_is_not_mistaken_for_a_title():
    """S-14: the old substring check for 'title:' matched 'subtitle:', so these
    files silently got no title."""
    out = inject_frontmatter("---\nsubtitle: A Subtitle\n---\n\nBody\n", "Real Title")
    parsed = parse_frontmatter(out)

    assert parsed["title"] == "Real Title"
    assert parsed["subtitle"] == "A Subtitle"


def test_closing_ellipsis_delimiter_is_recognized():
    out = inject_frontmatter("---\nauthor: Ada\n...\n\nBody\n", "Injected")
    assert out == "---\ntitle: Injected\nauthor: Ada\n...\n\nBody\n"


def test_crlf_line_endings_are_preserved():
    out = inject_frontmatter("---\r\nauthor: Ada\r\n---\r\n\r\nBody\r\n", "Injected")
    assert out == "---\r\ntitle: Injected\r\nauthor: Ada\r\n---\r\n\r\nBody\r\n"


# =============================================================================
# Things that only look like frontmatter
# =============================================================================

def test_horizontal_rule_is_not_treated_as_a_delimiter():
    """S-14: content opening with '--- text' used to be misread as frontmatter
    and silently receive no title at all."""
    out = inject_frontmatter("--- a horizontal rule, not frontmatter\n\nBody\n", "Applied")

    assert parse_frontmatter(out)["title"] == "Applied"
    assert out.endswith("--- a horizontal rule, not frontmatter\n\nBody\n")


def test_unterminated_delimiter_still_yields_a_title():
    """An opening '---' with no closing delimiter is not usable frontmatter, so
    a fresh block is prepended rather than the document being left titleless."""
    out = inject_frontmatter("---\nauthor: Ada\n\nBody\n", "Applied")
    assert parse_frontmatter(out) == {"title": "Applied"}


# =============================================================================
# Title quoting  (S-14 regression guards)
# =============================================================================

@pytest.mark.parametrize("title", [
    "Plain Title",
    "Sample: E. coli",          # colon
    "Ada's Notes",              # apostrophe
    "Ada's: Notes",             # both -- used to emit 'Ada's: Notes'
    "100% Yield",
    "Flux @ 50 mT",
    "Notes [draft] {v2}",
    "Title with åäö and µm",
    "A" * 300,                  # long enough to trigger emitter line-wrapping
])
def test_titles_round_trip_through_yaml(title):
    out = inject_frontmatter("Body\n", title)
    assert parse_frontmatter(out)["title"] == title


def test_colon_title_is_quoted():
    out = inject_frontmatter("Body\n", "Sample: E. coli")
    assert "title: 'Sample: E. coli'" in out


# =============================================================================
# Helpers
# =============================================================================

@pytest.mark.parametrize("content,expected_body", [
    ("---\na: 1\n---\nBody\n", "a: 1\n"),
    ("---\n---\nBody\n", ""),
    ("no frontmatter\n", None),
    ("--- rule\nBody\n", None),
    ("---\nunterminated\n", None),
    ("", None),
])
def test_find_frontmatter(content, expected_body):
    assert find_frontmatter(content)[0] == expected_body


@pytest.mark.parametrize("body,expected", [
    ("title: X\n", True),
    ("subtitle: X\n", False),
    ("author: Ada\n", False),
    ("", False),
    ("::: not valid yaml :::\n", False),
    ("just a string\n", False),
])
def test_has_title(body, expected):
    assert has_title(body) is expected
