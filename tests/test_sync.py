"""Tests for incremental staging sync.

Staging used to be deleted and rebuilt on every run. It is now reconciled, so
that the directory can be kept under version control and a build touches only
what actually changed.
"""

import pytest

from qbi_pipeline.cli import validate_output_path
from qbi_pipeline.staging import claim_staging_directory, sync_vault


def write(path, content="content\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def vault(tmp_path):
    v = tmp_path / "vault"
    write(v / "README.md", "# Home\n")
    write(v / "1_eln" / "entry.md", "Lab entry\n")
    write(v / "attachments" / "img.png", "notarealpng")
    return v


@pytest.fixture
def staging(tmp_path):
    out = tmp_path / "out"
    claim_staging_directory(out)
    return out


# =============================================================================
# Only changed files are written
# =============================================================================

def test_first_sync_writes_everything(vault, staging):
    _, changes = sync_vault(vault, staging)
    assert changes["updated"] == 3
    assert changes["unchanged"] == 0


def test_second_sync_writes_nothing(vault, staging):
    sync_vault(vault, staging)
    _, changes = sync_vault(vault, staging)

    assert changes["updated"] == 0
    assert changes["unchanged"] == 3


def test_unchanged_files_keep_their_mtime(vault, staging):
    """The point of not rewriting: `git status` in staging should show only
    what a build actually changed."""
    sync_vault(vault, staging)
    before = (staging / "1_eln" / "entry.md").stat().st_mtime_ns

    sync_vault(vault, staging)
    assert (staging / "1_eln" / "entry.md").stat().st_mtime_ns == before


def test_edited_source_is_rewritten(vault, staging):
    sync_vault(vault, staging)
    write(vault / "1_eln" / "entry.md", "Lab entry, revised\n")

    _, changes = sync_vault(vault, staging)

    assert changes["updated"] == 1
    assert changes["unchanged"] == 2
    assert "revised" in (staging / "1_eln" / "entry.md").read_text(encoding="utf-8")


def test_new_file_is_added_without_touching_the_rest(vault, staging):
    sync_vault(vault, staging)
    write(vault / "1_eln" / "second.md", "Another entry\n")

    _, changes = sync_vault(vault, staging)

    assert changes["updated"] == 1
    assert changes["unchanged"] == 3
    assert (staging / "1_eln" / "second.md").exists()


def test_changed_binary_asset_is_recopied(vault, staging):
    sync_vault(vault, staging)
    write(vault / "attachments" / "img.png", "different bytes entirely")

    _, changes = sync_vault(vault, staging)
    assert changes["updated"] == 1


# =============================================================================
# Deletions propagate  (S-5)
# =============================================================================

def test_deleted_source_file_is_pruned_from_staging(vault, staging):
    """S-5 regression guard: staging never pruned, so a file deleted from a
    vault -- including one deleted because it should not have been public --
    stayed live on the site indefinitely."""
    sync_vault(vault, staging)
    assert (staging / "1_eln" / "entry.md").exists()

    (vault / "1_eln" / "entry.md").unlink()
    _, changes = sync_vault(vault, staging)

    assert not (staging / "1_eln" / "entry.md").exists()
    assert changes["removed"] == 1


def test_file_that_becomes_confidential_is_unpublished(vault, staging):
    """Marking a folder after it has been published must take it down."""
    write(vault / "wip" / "draft.md", "messy\n")
    sync_vault(vault, staging)
    assert (staging / "wip" / "draft.md").exists()

    write(vault / "wip" / ".qbi-exclude", "")
    sync_vault(vault, staging)

    assert not (staging / "wip" / "draft.md").exists()


def test_pruning_leaves_preserved_paths_alone(vault, staging):
    """A git repo, hand-placed static assets and the generated config must
    survive a sync that prunes everything else."""
    write(staging / ".git" / "HEAD", "ref: refs/heads/main\n")
    write(staging / "_static" / "style.css", "body {}\n")
    write(staging / "myst.yml", "version: 1\n")

    sync_vault(vault, staging)

    assert (staging / ".git" / "HEAD").exists()
    assert (staging / "_static" / "style.css").exists()
    assert (staging / "myst.yml").exists()


def test_stray_file_in_staging_is_pruned(vault, staging):
    write(staging / "leftover.md", "from an older build\n")
    sync_vault(vault, staging)
    assert not (staging / "leftover.md").exists()


# =============================================================================
# Dry run
# =============================================================================

def test_dry_run_writes_nothing(vault, staging):
    _, changes = sync_vault(vault, staging, dry_run=True)

    assert changes["would_write"] == 3
    assert not (staging / "README.md").exists()


def test_dry_run_does_not_delete(vault, staging):
    sync_vault(vault, staging)
    (vault / "1_eln" / "entry.md").unlink()

    sync_vault(vault, staging, dry_run=True)
    assert (staging / "1_eln" / "entry.md").exists()


# =============================================================================
# Output path validation  (S-4)
# =============================================================================

def test_output_may_not_be_a_vault(tmp_path):
    vault = tmp_path / "research-biology-la"
    vault.mkdir()
    with pytest.raises(ValueError, match="must not be a source path"):
        validate_output_path(vault, [vault])


def test_output_may_not_contain_a_vault(tmp_path):
    """The config typo that motivated this: `output` set to the shared root,
    one line above the vault paths."""
    root = tmp_path / "shared"
    vault = root / "research-biology-la"
    vault.mkdir(parents=True)

    with pytest.raises(ValueError, match="contains source path"):
        validate_output_path(root, [vault], root=root)


def test_sibling_output_is_accepted(tmp_path):
    root = tmp_path / "shared"
    vault = root / "research-biology-la"
    vault.mkdir(parents=True)
    out = root / "_build_staging"

    validate_output_path(out, [vault], root=root)


# =============================================================================
# Broken-link warnings for allow-list gaps
# =============================================================================

def test_reference_to_a_skipped_file_is_reported(vault, staging, capsys):
    """The allow-list's failure mode is a missing file, which is invisible
    unless a page that links to it says so."""
    write(vault / "data" / "results.xlsx", "a,b\n")
    write(vault / "1_eln" / "entry.md", "See ![[results.xlsx]] for details\n")

    sync_vault(vault, staging)
    output = capsys.readouterr().out

    assert "results.xlsx" in output
    assert "not a published file type" in output


def test_no_warning_when_the_reference_is_published(vault, staging, capsys):
    write(vault / "1_eln" / "entry.md", "See ![[img.png]]\n")

    sync_vault(vault, staging)
    assert "not a published file type" not in capsys.readouterr().out


# =============================================================================
# Optimized assets are not rebuilt every run
# =============================================================================

def test_optimized_image_is_not_recopied_on_every_build(tmp_path, staging):
    """Optimization rewrites the staged copy, so it can never match its source.
    Comparing against the source directly meant every build re-copied and
    re-encoded every image -- wasted work, and cumulative JPEG quality loss."""
    from PIL import Image

    v = tmp_path / "vault"
    (v / "attachments").mkdir(parents=True)
    Image.new("RGB", (2000, 1000), (10, 20, 30)).save(v / "attachments" / "photo.jpg")
    write(v / "note.md", "text\n")

    _, first = sync_vault(v, staging)
    assert first["updated"] == 2

    _, second = sync_vault(v, staging)
    assert second["updated"] == 0
    assert second["unchanged"] == 2


def test_two_names_that_sanitize_alike_do_not_fight_over_one_staged_file(tmp_path, staging, capsys):
    """`to order.dna` and `to_order.dna` both sanitize to `to_order.dna`.

    Both were being written to that one path, each overwriting the other, so
    the published file was whichever came last and every single build reported
    them as changed -- which would have put a spurious commit in the staging
    repo every night forever.
    """
    v = tmp_path / "vault"
    write(v / "reference to order.dna", "spaced\n")
    write(v / "reference_to_order.dna", "underscored\n")

    _, first = sync_vault(v, staging)
    assert first["skipped_collision"] == 1
    assert "both stage as" in capsys.readouterr().out

    _, second = sync_vault(v, staging)
    assert second["updated"] == 0
    assert second["unchanged"] == 1


def test_collision_keeps_the_same_file_every_run(tmp_path, staging):
    """Which one wins must not depend on the order the filesystem returns."""
    v = tmp_path / "vault"
    write(v / "reference to order.dna", "spaced\n")
    write(v / "reference_to_order.dna", "underscored\n")

    sync_vault(v, staging)
    staged = (staging / "reference_to_order.dna").read_text(encoding="utf-8")

    for _ in range(3):
        sync_vault(v, staging)
        assert (staging / "reference_to_order.dna").read_text(encoding="utf-8") == staged


def test_edited_image_is_reprocessed(tmp_path, staging):
    from PIL import Image

    v = tmp_path / "vault"
    (v / "attachments").mkdir(parents=True)
    target = v / "attachments" / "photo.jpg"
    Image.new("RGB", (2000, 1000), (10, 20, 30)).save(target)

    sync_vault(v, staging)
    Image.new("RGB", (2000, 1000), (200, 10, 10)).save(target)

    _, changes = sync_vault(v, staging)
    assert changes["updated"] == 1


def test_manifest_is_not_pruned_as_stale(tmp_path, staging):
    from qbi_pipeline.staging import MANIFEST_NAME

    v = tmp_path / "vault"
    write(v / "note.md", "text\n")
    sync_vault(v, staging)
    assert (staging / MANIFEST_NAME).exists()

    sync_vault(v, staging)
    assert (staging / MANIFEST_NAME).exists()


# =============================================================================
# MyST's own artifacts must survive a sync
# =============================================================================

def test_myst_build_directory_is_never_pruned(vault, staging):
    """On the server, `myst start` runs as a service with _build open. Pruning
    it would delete the build cache and the theme's node_modules underneath a
    running process on every cron build."""
    write(staging / "_build" / "site" / "content" / "x.json", "{}")
    write(staging / "_build" / "templates" / "site" / "myst" / "book-theme"
          / "node_modules" / "react" / "index.js", "x")

    sync_vault(vault, staging)

    assert (staging / "_build" / "site" / "content" / "x.json").exists()
    assert (staging / "_build" / "templates" / "site" / "myst" / "book-theme"
            / "node_modules" / "react" / "index.js").exists()


@pytest.mark.parametrize("name", ["_build", "_static", "_next", ".git", ".cache"])
def test_underscore_and_dot_prefixed_entries_are_preserved(vault, staging, name):
    """Vault content can never start with _ or . (policy excludes those), so
    anything in staging that does belongs to something else."""
    write(staging / name / "file.txt", "x")
    sync_vault(vault, staging)
    assert (staging / name / "file.txt").exists()


def test_ordinary_stale_content_is_still_pruned(vault, staging):
    """The preserve rule must not become a licence to leave anything behind."""
    write(staging / "old_page.md", "stale\n")
    write(staging / "chapter" / "old.md", "stale\n")

    sync_vault(vault, staging)

    assert not (staging / "old_page.md").exists()
    assert not (staging / "chapter" / "old.md").exists()


# =============================================================================
# Notebook validity
# =============================================================================

@pytest.mark.parametrize("content,valid", [
    ('{"cells": [], "nbformat": 4, "nbformat_minor": 5}', True),
    ('{}', False),                       # valid JSON, not a notebook
    ('{"cells": []}', False),            # no nbformat
    ('{"nbformat": 4}', False),          # no cells
    ('{"cells": "not a list", "nbformat": 4}', False),
    ('[]', False),                       # JSON, but not an object
    ('not json at all', False),
])
def test_notebook_validity(tmp_path, staging, content, valid):
    """A file that is valid JSON but not a valid notebook used to reach MyST
    and fail the whole site build with `Cannot read properties of undefined`.
    MyST exits non-zero, so one bad notebook took everything down."""
    v = tmp_path / "vault"
    write(v / "nb.ipynb", content)

    census, changes = sync_vault(v, staging)

    assert (staging / "nb.ipynb").exists() is valid
    assert changes["skipped_invalid"] == (0 if valid else 1)
