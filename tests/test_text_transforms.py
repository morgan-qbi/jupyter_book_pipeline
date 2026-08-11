"""Characterization tests: image linebreaks (0b), path normalization (1),
text cleanup (3)."""

import pytest

from qbi_pipeline.transforms import (
    ensure_image_linebreaks,
    fix_text_issues,
    normalize_markdown_link_urls,
    normalize_notion_folders,
)

# =============================================================================
# Phase 0b: image linebreaks
# =============================================================================

def test_splits_text_running_directly_into_an_embed():
    assert ensure_image_linebreaks("data![[chart.png]]") == "data\n\n![[chart.png]]"


def test_inserts_blank_line_before_embed_on_its_own_line():
    assert ensure_image_linebreaks("Intro\n![[chart.png]]") == "Intro\n\n![[chart.png]]"


def test_preserves_indentation_of_embeds_inside_lists():
    out = ensure_image_linebreaks("* bullet\n  ![[chart.png]]")
    assert out == "* bullet\n\n  ![[chart.png]]"


def test_is_idempotent_when_blank_line_already_present():
    already = "Intro\n\n![[chart.png]]"
    assert ensure_image_linebreaks(already) == already


def test_applies_to_standard_markdown_images_too():
    assert ensure_image_linebreaks("Intro\n![alt](a.png)") == "Intro\n\n![alt](a.png)"


# =============================================================================
# Phase 1: path normalization
# =============================================================================

def test_rewrites_notion_export_folders_to_attachments():
    src = "![](Lab%20Notebook%20216be76e722280c380fad6c0fc508250/test.png)"
    assert normalize_notion_folders(src) == "![](attachments/test.png)"


def test_rewrites_double_underscore_attachments():
    assert normalize_notion_folders("![](__attachments/i.png)") == "![](attachments/i.png)"


def test_sanitizes_spaces_in_markdown_link_urls():
    src = "![img](folder name/my image.png)"
    assert normalize_markdown_link_urls(src) == "![img](folder_name/my_image.png)"


def test_link_text_is_left_untouched():
    src = "[My Link Text](a b.md)"
    assert normalize_markdown_link_urls(src) == "[My Link Text](a_b.md)"


@pytest.mark.parametrize("url", [
    "https://example.org/my%20paper.pdf",
    "http://example.org/a b.html",
    "mailto:ada@qbi.org",
    "//cdn.example.org/lib.js",
    "#section-heading",
])
def test_external_urls_are_left_untouched(url):
    """S-15 regression guard: sanitizing rewrites %20 and spaces to
    underscores, which is right for a vault path and breaks a remote one."""
    src = f"[link]({url})"
    assert normalize_markdown_link_urls(src) == src


def test_vault_paths_are_still_sanitized_alongside_external_ones():
    src = "[a](https://example.org/x%20y.pdf) and [b](my file.png)"
    out = normalize_markdown_link_urls(src)
    assert "https://example.org/x%20y.pdf" in out
    assert "my_file.png" in out


# =============================================================================
# Phase 3: text cleanup
# =============================================================================

def test_normalizes_unicode_dashes_to_ascii_hyphen():
    assert fix_text_issues("10–20 and — and −5") == "10-20 and - and -5"


def test_escapes_at_signs():
    assert fix_text_issues("measured @50 mT") == "measured \\@50 mT"


def test_leaves_fenced_code_blocks_untouched():
    """S-9 regression guard: the @ escape used to be applied to the whole
    document, turning a Python decorator into `\\@dataclass`."""
    src = "```python\n@dataclass\nclass X: pass\n```\n"
    assert fix_text_issues(src) == src


def test_leaves_tilde_fences_untouched():
    src = "~~~python\n@property\ndef x(self): ...\n~~~\n"
    assert fix_text_issues(src) == src


def test_leaves_inline_code_untouched():
    assert fix_text_issues("use `@dataclass` here") == "use `@dataclass` here"


def test_leaves_dashes_inside_code_untouched():
    """Dash normalization would otherwise silently edit string literals."""
    src = "```\nprint('range 10–20')\n```\n"
    assert fix_text_issues(src) == src


def test_still_escapes_prose_around_a_code_block():
    src = "email ada@qbi.org\n\n```\n@decorator\n```\n\nmore @ text\n"
    out = fix_text_issues(src)

    assert "ada\\@qbi.org" in out
    assert "```\n@decorator\n```" in out
    assert "more \\@ text" in out


def test_escapes_at_signs_in_email_addresses():
    """Intended behavior: MyST reads a bare @ as the start of a citation
    reference, so prose must escape it to render literally."""
    assert fix_text_issues("contact ada@qbi.org") == "contact ada\\@qbi.org"
