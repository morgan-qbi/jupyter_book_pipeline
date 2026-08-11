"""Tests: filename sanitizing and folder-name prettifying.

These began as characterization tests locking in behavior across the refactor.
Naming now has exactly one implementation, in qbi_pipeline.naming.
"""

import pytest

from qbi_pipeline import myst_config as config_generator
from qbi_pipeline import naming

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
    assert naming.sanitize_filename(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("a/b/c.md", "a/b/c.md"),
    ("a b/c d.md", "a_b/c_d.md"),
    ("a\\b\\c.md", "a/b/c.md"),
    ("Lab Notebook/img%20 1.png", "Lab_Notebook/img__1.png"),
])
def test_sanitize_path_normalizes_separators_and_spaces(raw, expected):
    assert naming.sanitize_path(raw) == expected


# =============================================================================
# prettify_folder_name — one implementation, shared by every caller
# =============================================================================

@pytest.mark.parametrize("raw,expected", [
    ("1_eln", "Eln"),
    ("my_folder", "My Folder"),
    ("2_curated_datasets", "Curated Datasets"),
    ("2025", "2025"),                                # was "" in preprocessing
    ("research-biology-la", "Research Biology La"),  # was "Research-Biology-La"
])
def test_prettify_folder_name(raw, expected):
    assert naming.prettify_folder_name(raw) == expected


def test_every_module_shares_one_prettify_implementation():
    """Phase 1: there used to be four copies with three behaviors. The two that
    diverged were preprocessing's -- it left hyphens alone and returned an
    empty string for all-digit names like a `2025` folder.
    """
    from qbi_pipeline import transforms

    assert transforms.prettify_folder_name is naming.prettify_folder_name
    assert config_generator.prettify_folder_name is naming.prettify_folder_name


@pytest.mark.parametrize("raw,expected", [
    ("2025", "2025"),
    ("research-biology-la", "Research Biology La"),
])
def test_previously_divergent_cases_now_agree(raw, expected):
    assert naming.prettify_folder_name(raw) == expected
    assert config_generator.prettify_folder_name(raw) == expected


# =============================================================================
# get_display_name — override table
# =============================================================================

def test_display_name_prefers_override_table():
    assert config_generator.get_display_name("research-biology-la") == "Research: Biology LA"
    assert config_generator.get_display_name("ecoli_flavoprotein_expression") == "E. coli Flavoprotein Expression"


def test_display_name_falls_through_to_prettify():
    assert config_generator.get_display_name("some_new_vault") == "Some New Vault"
