"""Security regression tests: what does and does not reach the staging directory.

Staging is published publicly, so these are the highest-value tests in the
suite. They currently encode the CURRENT policy, including the ways it fails
open (S-1, S-2, S-3). When Phase 2 lands, the KNOWN-WRONG assertions here flip
and become the real guarantees.
"""

import os
import sys

import pytest

from preprocessing import build_file_index, create_staging_directory


def write(path, content="content\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def vault(tmp_path):
    """A miniature vault covering every exclusion rule."""
    v = tmp_path / "vault"
    write(v / "README.md", "# Home\n")
    write(v / "notes.md", "Top level note\n")
    write(v / "1_eln" / "entry.md", "Lab entry\n")
    write(v / "attachments" / "img.png", "notpng")

    # Should be excluded:
    write(v / "5_confidential" / "secret.md", "PATIENT DATA\n")
    write(v / "5_restricted.md", "restricted note\n")
    write(v / "_private" / "draft.md", "draft\n")
    write(v / ".obsidian" / "app.json", "{}")
    write(v / "venv" / "lib" / "mod.md", "vendored\n")
    write(v / "node_modules" / "pkg" / "readme.md", "vendored\n")
    write(v / "Discourse Canvas" / "canvas.md", "canvas\n")
    return v


def staged_files(staging):
    return {
        str(p.relative_to(staging)).replace("\\", "/")
        for p in staging.rglob("*") if p.is_file()
    }


# =============================================================================
# Exclusions that work today
# =============================================================================

def test_confidential_prefix_folder_is_not_staged(vault, tmp_path):
    staged = staged_files(create_staging_directory(vault, tmp_path / "out"))
    assert "5_confidential/secret.md" not in staged
    assert not any(s.startswith("5_") for s in staged)


def test_underscore_and_dot_prefixes_are_not_staged(vault, tmp_path):
    staged = staged_files(create_staging_directory(vault, tmp_path / "out"))
    assert "_private/draft.md" not in staged
    assert ".obsidian/app.json" not in staged


def test_vendored_directories_are_not_staged(vault, tmp_path):
    staged = staged_files(create_staging_directory(vault, tmp_path / "out"))
    assert not any(s.startswith(("venv/", "node_modules/", "Discourse Canvas/")) for s in staged)


def test_prefix_rule_applies_to_files_not_just_directories(vault, tmp_path):
    staged = staged_files(create_staging_directory(vault, tmp_path / "out"))
    assert "5_restricted.md" not in staged


def test_publishable_content_is_staged(vault, tmp_path):
    staged = staged_files(create_staging_directory(vault, tmp_path / "out"))
    assert {"README.md", "notes.md", "1_eln/entry.md", "attachments/img.png"} <= staged


def test_exact_staged_set_is_locked(vault, tmp_path):
    """Full snapshot, so any change in exclusion behavior fails loudly."""
    staged = staged_files(create_staging_directory(vault, tmp_path / "out"))
    assert staged == {"README.md", "notes.md", "1_eln/entry.md", "attachments/img.png"}


# =============================================================================
# Ways the policy fails open
# =============================================================================

def test_confidential_folder_without_the_magic_prefix_is_published(vault, tmp_path):
    """KNOWN-WRONG (S-1): exclusion is prefix-matching on a name, so any folder
    a researcher names anything other than `5_*` publishes."""
    write(vault / "Confidential" / "hr_records.md", "SALARY DATA\n")
    write(vault / "05_Private" / "notes.md", "private\n")

    staged = staged_files(create_staging_directory(vault, tmp_path / "out"))
    assert "Confidential/hr_records.md" in staged   # <- leaks
    assert "05_Private/notes.md" in staged          # <- leaks


def test_arbitrary_non_publishable_files_are_published(vault, tmp_path):
    """KNOWN-WRONG (S-2): staging is copy-everything-except-a-denylist, so any
    file type in a vault reaches the public site."""
    write(vault / "grant_budget.csv", "salary,amount\n")
    write(vault / "api_keys.txt", "sk-live-secret\n")

    staged = staged_files(create_staging_directory(vault, tmp_path / "out"))
    assert "grant_budget.csv" in staged   # <- leaks
    assert "api_keys.txt" in staged       # <- leaks


@pytest.mark.skipif(
    sys.platform == "win32" and not os.environ.get("CI"),
    reason="symlink creation needs Developer Mode or admin on Windows; prod is Linux",
)
def test_symlinked_file_is_dereferenced_and_its_target_published(vault, tmp_path):
    """KNOWN-WRONG (S-3): shutil.copy2 follows symlinks, so a link inside a
    vault publishes the contents of a file outside the vault."""
    outside = write(tmp_path / "outside" / "private_key", "BEGIN PRIVATE KEY\n")
    try:
        os.symlink(outside, vault / "innocuous.md")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable in this environment")

    staging = create_staging_directory(vault, tmp_path / "out")
    leaked = staging / "innocuous.md"
    assert leaked.is_file()
    assert "BEGIN PRIVATE KEY" in leaked.read_text(encoding="utf-8")  # <- leaks


# =============================================================================
# File index
# =============================================================================

def test_file_index_honors_the_same_exclusions(vault):
    index, paths = build_file_index(vault)
    assert "secret.md" not in index
    assert "draft.md" not in index
    assert "entry.md" in index
    assert "1_eln/entry.md" in paths


def test_file_index_sanitizes_names(tmp_path):
    v = tmp_path / "v"
    write(v / "my note.md")
    index, paths = build_file_index(v)
    assert "my_note.md" in index
    assert "my_note.md" in paths


def test_duplicate_filenames_are_collected_into_a_list(tmp_path):
    v = tmp_path / "v"
    write(v / "a" / "dup.md")
    write(v / "b" / "dup.md")
    index, _ = build_file_index(v)
    assert isinstance(index["dup.md"], list)
    assert sorted(index["dup.md"]) == ["a/dup.md", "b/dup.md"]
