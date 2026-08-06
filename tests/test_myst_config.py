"""Characterization tests: myst.yml TOC generation.

config_generator.py has no tests at all today and gets moved wholesale in
Phase 3, so this pins its output shape first.
"""

import pytest
import yaml

from config_generator import (
    build_site_config,
    find_homepage,
    scan_chapter_contents,
    scan_vault_structure,
    should_skip_dir,
)


def write(path, content="body\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def staging(tmp_path):
    """Mirrors the real vault -> project -> chapter convention."""
    s = tmp_path / "staging"
    vault = s / "research-biology-la"
    write(vault / "README.md", "# Vault\n")

    proj = vault / "proj"
    write(proj / "README.md", "# Project\n")
    write(proj / "1_eln" / "README.md", "# Chapter\n")
    write(proj / "1_eln" / "b_entry.md")
    write(proj / "1_eln" / "a_entry.md")
    write(proj / "1_eln" / "notes_sub" / "deep.md")
    write(proj / "2_data" / "set.ipynb", "{}")
    write(proj / "5_confidential" / "secret.md", "PATIENT DATA\n")
    return s


# =============================================================================
# Homepage discovery / skip rules
# =============================================================================

def test_find_homepage_prefers_readme(tmp_path):
    write(tmp_path / "index.md")
    write(tmp_path / "README.md")
    assert find_homepage(tmp_path).name == "README.md"


def test_find_homepage_returns_none_when_absent(tmp_path):
    assert find_homepage(tmp_path) is None


@pytest.mark.parametrize("name", ["venv", ".obsidian", "attachments", "_build", "5_secret"])
def test_should_skip_dir_rejects(name):
    assert should_skip_dir(name) is True


@pytest.mark.parametrize("name", ["1_eln", "proj", "research-biology-la"])
def test_should_skip_dir_allows(name):
    assert should_skip_dir(name) is False


# =============================================================================
# Chapter scanning
# =============================================================================

def test_chapter_readme_becomes_overview_and_files_are_sorted(staging):
    chapter = staging / "research-biology-la" / "proj" / "1_eln"
    children = scan_chapter_contents(chapter, staging)

    assert children[0] == {
        "file": "research-biology-la/proj/1_eln/README.md",
        "title": "Overview",
    }
    assert children[1]["file"].endswith("a_entry.md")
    assert children[2]["file"].endswith("b_entry.md")


def test_chapter_subdirectory_becomes_a_nested_group(staging):
    chapter = staging / "research-biology-la" / "proj" / "1_eln"
    children = scan_chapter_contents(chapter, staging)
    sub = children[-1]

    assert sub["title"] == "Notes Sub"
    assert sub["children"] == [
        {"file": "research-biology-la/proj/1_eln/notes_sub/deep.md"}
    ]


def test_toc_paths_always_use_forward_slashes(staging):
    chapter = staging / "research-biology-la" / "proj" / "1_eln"
    for child in scan_chapter_contents(chapter, staging):
        assert "\\" not in child.get("file", "")


# =============================================================================
# Vault scanning
# =============================================================================

def test_vault_structure_uses_display_name_overrides(staging):
    entry = scan_vault_structure(staging / "research-biology-la", staging)
    assert entry["title"] == "Research: Biology LA"


def test_chapters_are_titled_from_the_chapter_name_table(staging):
    entry = scan_vault_structure(staging / "research-biology-la", staging)
    project = entry["children"][1]
    titles = [c["title"] for c in project["children"] if "title" in c]

    assert "Chapter 1: ELN" in titles
    assert "Chapter 2: Curated Datasets" in titles


def test_confidential_chapter_is_excluded_from_the_toc(staging):
    """S-16 regression guard: the TOC layer must enforce the confidential rule
    itself, not rely on preprocessing having already stripped `5_*` folders
    from staging. Running config generation against a raw vault used to list
    confidential files directly.
    """
    entry = scan_vault_structure(staging / "research-biology-la", staging)
    project = entry["children"][1]
    titles = [c["title"] for c in project["children"] if "title" in c]

    assert "Chapter 5: Confidential" not in titles
    assert not any("secret" in str(c) for c in project["children"])


# =============================================================================
# Site config
# =============================================================================

def test_site_config_shape():
    config = build_site_config([{"file": "index.md"}], site_title="Test Site")
    assert config["version"] == 1
    assert config["project"]["title"] == "Test Site"
    assert config["project"]["license"] == "CC-BY-4.0"
    assert config["project"]["open_access"] is True
    assert config["site"]["template"] == "book-theme"


def test_project_id_is_stable_across_builds():
    """S-11 regression guard: a fresh uuid4 per build meant the site's identity
    changed every run, which would break DOI and metadata work."""
    assert build_site_config([])["project"]["id"] == build_site_config([])["project"]["id"]


def test_project_id_differs_between_sites():
    a = build_site_config([], site_title="Site A")["project"]["id"]
    b = build_site_config([], site_title="Site B")["project"]["id"]
    assert a != b


def test_existing_project_id_is_preserved(tmp_path):
    """An id already published wins over the derived one, so identity survives
    even a site rename."""
    existing = tmp_path / "myst.yml"
    existing.write_text(
        "version: 1\nproject:\n  id: 11111111-2222-3333-4444-555555555555\n",
        encoding="utf-8",
    )

    config = build_site_config([], site_title="Renamed", existing_config_path=existing)
    assert config["project"]["id"] == "11111111-2222-3333-4444-555555555555"


def test_malformed_existing_config_falls_back_to_derived_id(tmp_path):
    existing = tmp_path / "myst.yml"
    existing.write_text("{{ not: valid: yaml", encoding="utf-8")

    config = build_site_config([], site_title="X", existing_config_path=existing)
    assert config["project"]["id"] == build_site_config([], site_title="X")["project"]["id"]


def test_dark_logo_intentionally_reuses_the_single_available_asset():
    """D-3: the Light Mode logo is the only asset that exists, so it serves both
    themes. Locked in so nobody 'fixes' it toward a file that is not there."""
    options = build_site_config([])["site"]["options"]
    assert options["logo_dark"] == options["logo"]
    assert "Light Mode" in options["logo_dark"]


def test_hide_footer_links_is_enabled():
    """D-3: rescued from the dead module (S-13) and now actually applied.

    Emitted as a real YAML boolean, not the string 'true' the old module used.
    """
    options = build_site_config([])["site"]["options"]
    assert options["hide_footer_links"] is True
    assert "hide_footer_links: true" in yaml.dump(build_site_config([]))
