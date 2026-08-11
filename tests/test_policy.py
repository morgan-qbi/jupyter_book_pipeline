"""Security tests for the shared publication policy.

policy.py decides what reaches a public website, so these are the tests that
matter most. They cover the unified exclusion rules, the two-tier
publish/navigate distinction, and the .qbi-exclude marker.
"""

import os
import sys

import pytest

from qbi_pipeline import myst_config as config_generator
from qbi_pipeline.audit import checks as vault_audit
from qbi_pipeline.policy import (
    EXCLUDED_DIRS,
    NON_NAVIGABLE_DIRS,
    QBI_EXCLUDE_MARKER,
    is_confidential_name,
    is_excluded_name,
    is_excluded_relative_path,
    is_navigable_name,
    iter_vault_dirs,
    iter_vault_files,
)


def write(path, content="content\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def relative_files(root):
    return {str(rel).replace("\\", "/") for _, rel in iter_vault_files(root)}


# =============================================================================
# Name-level rules
# =============================================================================

@pytest.mark.parametrize("name", [
    ".obsidian", ".git", ".env", "_private", "_build", "5_confidential",
    "5_restricted.md", "venv", "node_modules", "Discourse Canvas",
    "Folder Template Structure", "something.dist-info", QBI_EXCLUDE_MARKER,
])
def test_is_excluded_name_rejects(name):
    assert is_excluded_name(name) is True


@pytest.mark.parametrize("name", [
    "1_eln", "notes.md", "attachments", "research-biology-la", "2025", "proj",
])
def test_is_excluded_name_allows(name):
    assert is_excluded_name(name) is False


def test_attachments_are_published_but_not_navigable():
    """The publish/navigate split is the reason the old duplicated lists
    diverged: images must be staged or every embed breaks, but the folder must
    not show up as a chapter."""
    assert is_excluded_name("attachments") is False   # staged
    assert is_navigable_name("attachments") is False  # not in the TOC


def test_excluded_names_are_never_navigable():
    for name in EXCLUDED_DIRS | NON_NAVIGABLE_DIRS:
        assert is_navigable_name(name) is False


@pytest.mark.parametrize("name,expected", [
    ("5_confidential", True),
    ("5_x.md", True),
    ("05_confidential", False),   # documents the convention's narrowness
    ("Confidential", False),
])
def test_is_confidential_name(name, expected):
    assert is_confidential_name(name) is expected


def test_is_excluded_relative_path_checks_every_component():
    assert is_excluded_relative_path("proj/5_confidential/secret.md") is True
    assert is_excluded_relative_path("proj/.obsidian/app.json") is True
    assert is_excluded_relative_path("proj/1_eln/entry.md") is False


# =============================================================================
# Traversal
# =============================================================================

@pytest.fixture
def vault(tmp_path):
    v = tmp_path / "vault"
    write(v / "README.md")
    write(v / "1_eln" / "entry.md")
    write(v / "attachments" / "img.png")
    write(v / "5_confidential" / "secret.md", "PATIENT DATA\n")
    write(v / "_private" / "draft.md")
    write(v / ".obsidian" / "app.json")
    write(v / "venv" / "lib" / "mod.md")
    return v


def test_traversal_applies_the_exclusion_rules(vault):
    assert relative_files(vault) == {
        "README.md",
        "1_eln/entry.md",
        "attachments/img.png",
    }


def test_traversal_yields_directories(vault):
    dirs = {str(rel).replace("\\", "/") for _, rel in iter_vault_dirs(vault)}
    assert dirs == {"1_eln", "attachments"}


# =============================================================================
# .qbi-exclude marker  (D-2)
# =============================================================================

def test_marker_excludes_the_folder_it_sits_in(vault):
    write(vault / "wip" / "notes.md")
    write(vault / "wip" / QBI_EXCLUDE_MARKER, "")

    assert "wip/notes.md" not in relative_files(vault)


def test_marker_excludes_everything_beneath_it(vault):
    write(vault / "wip" / "deep" / "deeper" / "buried.md")
    write(vault / "wip" / QBI_EXCLUDE_MARKER, "")

    published = relative_files(vault)
    assert not any(p.startswith("wip/") for p in published)


def test_marker_file_itself_is_never_published(vault):
    # It is a dotfile, so it is excluded by name regardless of the subtree rule.
    assert is_excluded_name(QBI_EXCLUDE_MARKER) is True

    write(vault / "wip" / QBI_EXCLUDE_MARKER, "")
    assert not any(QBI_EXCLUDE_MARKER in p for p in relative_files(vault))


def test_marker_at_vault_root_excludes_everything(vault):
    write(vault / QBI_EXCLUDE_MARKER, "")
    assert relative_files(vault) == set()


def test_marker_does_not_affect_sibling_folders(vault):
    write(vault / "excluded_wip" / "notes.md")
    write(vault / "excluded_wip" / QBI_EXCLUDE_MARKER, "")
    write(vault / "kept_wip" / "notes.md")

    published = relative_files(vault)
    assert "kept_wip/notes.md" in published
    assert "excluded_wip/notes.md" not in published


def test_marker_excludes_subtree_from_directory_traversal(vault):
    write(vault / "wip" / "deep" / "x.md")
    write(vault / "wip" / QBI_EXCLUDE_MARKER, "")

    dirs = {str(rel).replace("\\", "/") for _, rel in iter_vault_dirs(vault)}
    assert not any(d.startswith("wip") for d in dirs)


@pytest.mark.skipif(
    sys.platform == "win32" and not os.environ.get("CI"),
    reason="symlink creation needs Developer Mode or admin on Windows; prod is Linux",
)
def test_traversal_does_not_follow_directory_symlinks(vault, tmp_path):
    outside = tmp_path / "outside"
    write(outside / "private.md", "SECRET\n")
    try:
        os.symlink(outside, vault / "linked", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable in this environment")

    assert not any("private.md" in p for p in relative_files(vault))


# =============================================================================
# One policy, three consumers  (S-1)
# =============================================================================

def test_all_three_modules_share_one_exclusion_implementation():
    """The whole point of policy.py. vault_audit's own copy used to omit the
    confidential rule, so audit reports named files inside 5_* folders."""
    from qbi_pipeline import index

    assert index.iter_vault_files is iter_vault_files
    assert vault_audit.iter_vault_files is iter_vault_files
    assert config_generator.should_skip_dir("5_confidential") is True


def test_audit_no_longer_scans_confidential_folders(vault):
    """S-1 regression guard: audit reports are written to disk and may be
    shared, so they must never name confidential files."""
    scanned = {f.name for f in vault_audit.get_all_files(vault)}

    assert "secret.md" not in scanned
    assert "entry.md" in scanned


def test_audit_respects_the_qbi_exclude_marker(vault):
    write(vault / "wip" / "messy_notes.md")
    write(vault / "wip" / QBI_EXCLUDE_MARKER, "")

    scanned = {f.name for f in vault_audit.get_all_files(vault)}
    assert "messy_notes.md" not in scanned
