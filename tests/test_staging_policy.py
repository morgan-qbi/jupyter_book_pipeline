"""Security tests: what does and does not reach the staging directory.

Staging is published publicly, so these are the highest-value tests in the
suite. Phase 2 turned staging from copy-everything-except-a-denylist into an
allow-list, so the assertions that used to document leaks are now guarantees.
"""

import os
import sys

import pytest

from policy import PUBLISHABLE_EXTENSIONS
from preprocessing import build_file_index
from staging import assert_safe_staging_target, claim_staging_directory, sync_vault


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


@pytest.fixture
def staging(tmp_path):
    out = tmp_path / "out"
    claim_staging_directory(out)
    return out


def staged_files(staging):
    """Staged files, ignoring pipeline bookkeeping."""
    return {
        str(p.relative_to(staging)).replace("\\", "/")
        for p in staging.rglob("*")
        if p.is_file() and not p.name.startswith(".qbi-")
    }


def sync(vault, staging, **kwargs):
    return sync_vault(vault, staging, **kwargs)


# =============================================================================
# Exclusions
# =============================================================================

def test_confidential_prefix_folder_is_not_staged(vault, staging):
    sync(vault, staging)
    files = staged_files(staging)
    assert "5_confidential/secret.md" not in files
    assert not any(f.startswith("5_") for f in files)


def test_underscore_and_dot_prefixes_are_not_staged(vault, staging):
    sync(vault, staging)
    files = staged_files(staging)
    assert "_private/draft.md" not in files
    assert ".obsidian/app.json" not in files


def test_vendored_directories_are_not_staged(vault, staging):
    sync(vault, staging)
    assert not any(
        f.startswith(("venv/", "node_modules/", "Discourse Canvas/"))
        for f in staged_files(staging)
    )


def test_prefix_rule_applies_to_files_not_just_directories(vault, staging):
    sync(vault, staging)
    assert "5_restricted.md" not in staged_files(staging)


def test_exact_staged_set_is_locked(vault, staging):
    sync(vault, staging)
    assert staged_files(staging) == {
        "README.md", "notes.md", "1_eln/entry.md", "attachments/img.png",
    }


# =============================================================================
# Allow-list  (D-1 / S-2)
# =============================================================================

def test_non_publishable_types_are_skipped(vault, staging):
    """S-2 regression guard: staging used to copy every file type, so a
    spreadsheet or key file dropped in a vault went straight to the web."""
    write(vault / "grant_budget.csv", "salary,amount\n")
    write(vault / "api_keys.txt", "sk-live-secret\n")
    write(vault / "notes.docx", "x")

    sync(vault, staging)
    files = staged_files(staging)

    assert "grant_budget.csv" not in files
    assert "api_keys.txt" not in files
    assert "notes.docx" not in files


def test_publishable_types_are_staged(vault, staging):
    write(vault / "paper.pdf", "%PDF-1.4\n")
    write(vault / "model.stl", "solid\n")

    sync(vault, staging)
    files = staged_files(staging)

    assert "paper.pdf" in files
    assert "model.stl" in files


def test_extra_extensions_can_be_opted_in(vault, staging):
    """The census reports skipped types; opting one in is a config change."""
    write(vault / "dataset.csv", "a,b\n")

    sync(vault, staging, allowed_extensions=PUBLISHABLE_EXTENSIONS | {".csv"})
    assert "dataset.csv" in staged_files(staging)


def test_census_counts_published_and_skipped(vault, staging):
    write(vault / "dataset.csv", "a,b\n")
    write(vault / "other.csv", "a,b\n")

    census, _ = sync(vault, staging)

    assert census.published[".md"] == 3
    assert census.skipped[".csv"] == 2
    assert census.has_skips is True


def test_census_reports_skipped_types_loudly(vault, staging):
    write(vault / "dataset.csv", "a,b\n")
    census, _ = sync(vault, staging)
    rendered = "\n".join(census.render("test-vault"))

    assert ".csv" in rendered
    assert "SKIPPED" in rendered
    assert "publish_extensions" in rendered


def test_census_reports_excluded_subtrees_by_count_only(vault, staging):
    """Confidential content must be visible as a number, never as a name."""
    census, _ = sync(vault, staging)
    rendered = "\n".join(census.render("test-vault"))

    assert "excluded by policy" in rendered
    assert "secret" not in rendered
    assert "confidential" not in rendered.lower()


# =============================================================================
# Symlinks  (S-3)
# =============================================================================

@pytest.mark.skipif(
    sys.platform == "win32" and not os.environ.get("CI"),
    reason="symlink creation needs Developer Mode or admin on Windows; prod is Linux",
)
def test_symlinked_file_is_refused_not_dereferenced(vault, staging, tmp_path):
    """S-3 regression guard: shutil.copy2 follows symlinks, so a link inside a
    vault used to publish the contents of a file outside it."""
    outside = write(tmp_path / "outside" / "private_key", "BEGIN PRIVATE KEY\n")
    try:
        os.symlink(outside, vault / "innocuous.md")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable in this environment")

    _, changes = sync(vault, staging)

    assert not (staging / "innocuous.md").exists()
    assert changes["skipped_symlink"] == 1


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


# =============================================================================
# Staging target safety  (S-4)
# =============================================================================

def test_refuses_a_non_empty_directory_without_a_marker(tmp_path):
    """S-4 regression guard: staging used to rmtree whatever `output` pointed
    at, so one typo in the config could take out the research share."""
    real_data = tmp_path / "shared"
    write(real_data / "important.md", "REAL RESEARCH DATA\n")

    with pytest.raises(ValueError, match="Refusing to use"):
        assert_safe_staging_target(real_data)

    assert (real_data / "important.md").exists()


def test_accepts_an_empty_directory(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert_safe_staging_target(empty)


def test_accepts_a_nonexistent_directory(tmp_path):
    assert_safe_staging_target(tmp_path / "not-yet")


def test_accepts_a_directory_it_previously_claimed(tmp_path):
    out = tmp_path / "out"
    claim_staging_directory(out)
    write(out / "page.md")
    assert_safe_staging_target(out)


def test_rejects_a_file(tmp_path):
    target = write(tmp_path / "afile.txt")
    with pytest.raises(ValueError, match="not a directory"):
        assert_safe_staging_target(target)
