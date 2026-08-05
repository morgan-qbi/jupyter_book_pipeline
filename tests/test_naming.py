"""Characterization tests: filename sanitizing and folder-name prettifying.

These lock in behavior AS IT IS TODAY so Phases 1-3 can move this code without
silently changing output. Tests marked KNOWN-WRONG document a real defect; they
get inverted when that finding is fixed.
"""

import pytest

import config_generator
import preprocessing


# =============================================================================
# sanitize_filename / sanitize_path
# =============================================================================

@pytest.mark.parametrize("raw,expected", [
    ("simple.md", "simple.md"),
    ("with space.png", "with_space.png"),
    ("url%20encoded.png", "url_encoded.png"),
    ("both %20 kinds.png", "both___kinds.png"),
    ("", ""),
])
def test_sanitize_filename(raw, expected):
    assert preprocessing.sanitize_filename(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("a/b/c.md", "a/b/c.md"),
    ("a b/c d.md", "a_b/c_d.md"),
    ("a\\b\\c.md", "a/b/c.md"),
    ("Lab Notebook/img%20 1.png", "Lab_Notebook/img__1.png"),
])
def test_sanitize_path_normalizes_separators_and_spaces(raw, expected):
    assert preprocessing.sanitize_path(raw) == expected


# =============================================================================
# prettify_folder_name — TWO divergent implementations (see S-1 / naming.py)
# =============================================================================

@pytest.mark.parametrize("raw,expected", [
    ("1_eln", "Eln"),
    ("my_folder", "My Folder"),
    ("2_curated_datasets", "Curated Datasets"),
])
def test_prettify_agrees_across_both_implementations(raw, expected):
    """Cases where the two copies happen to agree."""
    assert preprocessing.prettify_folder_name(raw) == expected
    assert config_generator.prettify_folder_name(raw) == expected


def test_prettify_diverges_on_pure_digit_names():
    """KNOWN-WRONG (preprocessing): a year folder is stripped to an empty string.

    config_generator.py grew a guard for this; preprocessing.py never did.
    Phase 1 unifies on the config_generator behavior.
    """
    assert preprocessing.prettify_folder_name("2025") == ""       # <- defect
    assert config_generator.prettify_folder_name("2025") == "2025"  # <- correct


def test_prettify_diverges_on_hyphenated_names():
    """KNOWN-WRONG (preprocessing): hyphens are not converted to spaces.

    Every real vault name is hyphenated (research-biology-la), so this is the
    difference that actually shows up in output.
    """
    assert preprocessing.prettify_folder_name("research-biology-la") == "Research-Biology-La"
    assert config_generator.prettify_folder_name("research-biology-la") == "Research Biology La"


# =============================================================================
# get_display_name — override table
# =============================================================================

def test_display_name_prefers_override_table():
    assert config_generator.get_display_name("research-biology-la") == "Research: Biology LA"
    assert config_generator.get_display_name("ecoli_flavoprotein_expression") == "E. coli Flavoprotein Expression"


def test_display_name_falls_through_to_prettify():
    assert config_generator.get_display_name("some_new_vault") == "Some New Vault"
