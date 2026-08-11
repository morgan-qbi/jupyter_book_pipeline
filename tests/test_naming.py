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
    ("1_eln", "ELN"),
    ("my_folder", "My Folder"),
    ("2_curated_datasets", "Curated Datasets"),
    ("2025", "2025"),                                # was "" in preprocessing
    ("research-biology-la", "Research Biology La"),  # was "Research-Biology-La"
])
def test_prettify_folder_name(raw, expected):
    assert naming.prettify_folder_name(raw) == expected


# =============================================================================
# Case is meaning: names the scientists already spelled correctly
# =============================================================================

@pytest.mark.parametrize("raw,expected", [
    # `str.title()` lowercased the rest of every word, so every acronym the
    # lab writes in caps came out looking like an ordinary word.
    ("NI_DAQ_testing", "NI DAQ Testing"),
    ("LOV_domain_phylogenetics", "LOV Domain Phylogenetics"),
    ("LED_control", "LED Control"),
    ("HsuLOV", "HsuLOV"),
    ("LIS3MDL_comms", "LIS3MDL Comms"),
    # Lowercase-first is a convention, not a mistake: pRSET is a plasmid,
    # phrB a gene, and 0p5mT a field strength of 0.5 mT. "P5Mt" is nonsense.
    ("pRSETb-phrB_Gibson_test", "pRSETb phrB Gibson Test"),
    ("0p5mT", "0p5mT"),
    ("NDTiffStack_measurements", "NDTiffStack Measurements"),
    # An all-lowercase word has no capitals to preserve, so it goes through
    # the acronym table.
    ("mfe_fit_analysis", "MFE Fit Analysis"),
    ("eln_archive", "ELN Archive"),
    # `title()` also broke apostrophes: "Morgan'S Notes".
    ("Morgan's_notes", "Morgan's Notes"),
])
def test_existing_capitalization_is_preserved(raw, expected):
    assert naming.prettify_folder_name(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("1_eln", "ELN"),                  # an ordering prefix is dropped
    ("01_basic_tutorial", "Basic Tutorial"),
    ("4state_kBET", "4state kBET"),    # no underscore: the 4 is the model
    ("20250918_rampdown", "20250918 Rampdown"),   # a date, not an ordering prefix
    ("2025", "2025"),
])
def test_only_a_short_numeric_prefix_is_stripped(raw, expected):
    """A greedy strip ate dates too, and a folder of entries distinguished only
    by date collapses into one repeated nav title."""
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
# get_display_name — overrides, configured from the build config
# =============================================================================

def test_display_name_prefers_override_table():
    naming.configure_display_names({
        "research-team-one": "Research: Team One",
        "ecoli_expression": "E. coli Expression",
    })
    assert config_generator.get_display_name("research-team-one") == "Research: Team One"
    assert config_generator.get_display_name("ecoli_expression") == "E. coli Expression"


def test_display_name_falls_through_to_prettify():
    assert config_generator.get_display_name("some_new_vault") == "Some New Vault"


def test_overrides_are_empty_until_configured():
    """They live in build_config.yml, not in the source. One institute's folder
    names are configuration, and this repository is public."""
    assert naming.DISPLAY_NAMES == {}


def test_configuring_replaces_rather_than_accumulates():
    naming.configure_display_names({"a": "A"})
    naming.configure_display_names({"b": "B"})
    assert "a" not in naming.DISPLAY_NAMES
    assert naming.DISPLAY_NAMES["b"] == "B"


def test_configure_updates_the_dict_other_modules_imported():
    """myst_config imports DISPLAY_NAMES by reference, so rebinding it here
    would leave that module looking at a stale dict."""
    naming.configure_display_names({"a": "A"})
    assert config_generator.DISPLAY_NAMES is naming.DISPLAY_NAMES
    assert config_generator.DISPLAY_NAMES["a"] == "A"


def test_no_overrides_is_accepted():
    naming.configure_display_names(None)
    assert naming.DISPLAY_NAMES == {}


@pytest.mark.parametrize("bad", [["a", "b"], "a: A", 42])
def test_malformed_override_table_is_rejected(bad):
    with pytest.raises(ValueError):
        naming.configure_display_names(bad)


def test_non_string_display_name_is_rejected():
    with pytest.raises(ValueError):
        naming.configure_display_names({"a": ["A"]})


def test_acronym_table_is_lowercase_keyed():
    """Lookup is on an all-lowercase word, so a capitalized key would be dead
    weight that silently never matches."""
    assert all(key == key.lower() for key in naming.ACRONYMS)
