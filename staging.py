"""
Staging: reconcile a vault into the published directory.

Staging used to be rebuilt from scratch on every run -- `shutil.rmtree` on the
output path, then a full copy. That had three problems:

1. It deleted whatever the output path pointed at, with no validation. A typo
   in `output:` would have taken the research share with it (S-4).
2. It made the staging directory impossible to keep under version control,
   because `.git` was inside the tree being deleted.
3. In multi-vault mode it only wiped each vault's *subdirectory*, never the
   root, so files deleted from a vault stayed published forever (S-5).

This module syncs instead of rebuilding. It computes the set of files that
*should* exist, writes only those that are new or changed, and prunes the ones
that should no longer be there. Unchanged files are not rewritten, so their
mtimes are stable and `git status` in the staging directory shows exactly what
a build changed.
"""


import json
import shutil
from collections import Counter
from pathlib import Path

from naming import sanitize_relative_path
from policy import (
    PRESERVED_STAGING_NAMES,
    PUBLISHABLE_EXTENSIONS,
    STAGING_MARKER,
    WEB_IMAGE_EXTENSIONS,
    is_preserved_staging_name,
    is_publishable_extension,
    iter_vault_files,
)
from preprocessing import build_file_index, optimize_image, process_markdown_content


class ExtensionCensus:
    """
    Per-vault tally of every file extension encountered, and whether it was
    published.

    An allow-list fails quietly: a researcher adds a new file type, it never
    appears on the site, and nobody notices for months. The census turns that
    into a line of build output.
    """

    def __init__(self):
        self.published = Counter()
        self.skipped = Counter()
        self.excluded_dirs = 0
        self.marked_dirs = 0
        self.excluded_files = 0

    def record(self, suffix, was_published):
        key = suffix.lower() or '(no extension)'
        if was_published:
            self.published[key] += 1
        else:
            self.skipped[key] += 1

    def absorb_traversal_stats(self, stats):
        self.excluded_dirs = stats.get('excluded_dirs', 0)
        self.marked_dirs = stats.get('marked_dirs', 0)
        self.excluded_files = stats.get('excluded_files', 0)

    @property
    def has_skips(self):
        return bool(self.skipped)

    def render(self, vault_name):
        """Return the census as a list of printable lines"""
        lines = [f"\nExtensions in {vault_name}:"]

        combined = [(ext, n, True) for ext, n in self.published.items()]
        combined += [(ext, n, False) for ext, n in self.skipped.items()]
        # Loudest first: skipped types outrank published ones at equal counts,
        # and within each group the biggest gaps come first.
        combined.sort(key=lambda row: (row[2], -row[1], row[0]))

        for ext, count, was_published in combined:
            if was_published:
                lines.append(f"  {ext:<12} {count:>5}  published")
            else:
                lines.append(f"  {ext:<12} {count:>5}  SKIPPED  <- not in allow-list")

        if self.excluded_dirs or self.marked_dirs or self.excluded_files:
            # Counts only, never names: these are the confidential and
            # opted-out subtrees, and naming them would defeat the point.
            parts = []
            if self.excluded_dirs:
                parts.append(f"{self.excluded_dirs} directories excluded by policy")
            if self.marked_dirs:
                parts.append(f"{self.marked_dirs} marked with .qbi-exclude")
            if self.excluded_files:
                parts.append(f"{self.excluded_files} files excluded by name")
            lines.append(f"  ({'; '.join(parts)})")

        if self.has_skips:
            lines.append(
                "  Add any of the SKIPPED types to `publish_extensions` in the "
                "build config if they belong on the site."
            )

        return lines


def assert_safe_staging_target(staging_path):
    """
    Refuse to manage a directory that this pipeline does not own.

    Sync prunes files it considers stale, so it must never be pointed at a
    directory full of real data. A staging directory is identified by its
    marker file; anything else that already has content is rejected rather
    than adopted.
    """
    staging_path = Path(staging_path)
    if not staging_path.exists():
        return

    if not staging_path.is_dir():
        raise ValueError(f"Staging path exists but is not a directory: {staging_path}")

    if (staging_path / STAGING_MARKER).exists():
        return

    contents = [p for p in staging_path.iterdir() if p.name != STAGING_MARKER]
    if contents:
        raise ValueError(
            f"Refusing to use {staging_path} as a staging directory: it is not "
            f"empty and has no {STAGING_MARKER} marker, so it was probably not "
            f"created by this pipeline.\n"
            f"If this really is the staging directory, create the marker "
            f"manually:\n"
            f"    touch {staging_path / STAGING_MARKER}"
        )


def claim_staging_directory(staging_path):
    """Create the staging directory if needed and mark it as pipeline-owned"""
    staging_path = Path(staging_path)
    staging_path.mkdir(parents=True, exist_ok=True)
    marker = staging_path / STAGING_MARKER
    if not marker.exists():
        marker.write_text(
            "This directory is managed by the QBI Jupyter Books pipeline.\n"
            "Files not produced by a build may be pruned. Do not store "
            "anything here that is not either generated or listed in "
            "policy.PRESERVED_STAGING_NAMES.\n",
            encoding='utf-8',
        )


def write_if_changed(output_path, content):
    """
    Write text only when it differs from what is already on disk.

    Rewriting identical content would churn mtimes and fill `git status` in the
    staging repo with files that did not actually change.
    """
    output_path = Path(output_path)
    if output_path.exists():
        try:
            if output_path.read_text(encoding='utf-8') == content:
                return False
        except (UnicodeDecodeError, OSError):
            pass

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding='utf-8')
    return True


MANIFEST_NAME = '.qbi-manifest.json'


def load_manifest(staging_path):
    """
    Load the record of which source file produced each staged asset.

    Assets cannot be compared against their sources directly, because
    optimization rewrites the staged copy: a resized, metadata-stripped image
    never matches the original it came from, so every build would re-copy and
    re-optimize it. Repeated re-encoding of a JPEG also loses quality each
    time. Recording the source's size and mtime instead makes the check exact.
    """
    path = Path(staging_path) / MANIFEST_NAME
    if not path.exists():
        return {}
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError, OSError):
        # An unreadable manifest costs a rebuild, not correctness.
        return {}


def save_manifest(staging_path, manifest):
    path = Path(staging_path) / MANIFEST_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, sort_keys=True)


def source_signature(source):
    """Size and mtime of a source file, used to detect edits"""
    stat = Path(source).stat()
    return [stat.st_size, stat.st_mtime_ns]


def copy_asset_if_changed(source, output_path, staged_relative, manifest):
    """
    Copy an asset only when its source has changed since the last build.

    Returns True if the file was (re)written.
    """
    source = Path(source)
    output_path = Path(output_path)
    signature = source_signature(source)

    if output_path.exists() and manifest.get(staged_relative) == signature:
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, output_path)
    manifest[staged_relative] = signature
    return True


def is_valid_notebook(path):
    """True if a .ipynb file parses as JSON"""
    try:
        with open(path, encoding='utf-8') as f:
            json.load(f)
        return True
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError, OSError):
        return False


def prune_stale_files(staging_path, expected, dry_run=False):
    """
    Remove staged files that no longer correspond to a vault file.

    This is what makes unpublishing work. Without it a file deleted from a
    vault -- including one deleted *because* it should never have been public
    -- stays live on the site indefinitely (S-5).

    Preserved names are never pruned, so a `.git` directory, `_static` assets
    and the generated `myst.yml` survive.
    """
    staging_path = Path(staging_path)
    removed = []

    for path in sorted(staging_path.rglob('*'), reverse=True):
        relative = path.relative_to(staging_path)
        if is_preserved_staging_name(relative.parts[0]):
            continue

        if path.is_file():
            if str(relative).replace('\\', '/') not in expected:
                removed.append(relative)
                if not dry_run:
                    path.unlink()
        elif path.is_dir():
            if not dry_run and not any(path.iterdir()):
                path.rmdir()

    return removed


def sync_vault(source_path, staging_path, allowed_extensions=None, dry_run=False):
    """
    Sync one vault into a staging directory.

    Returns (census, changes) where changes counts added/updated/unchanged/
    removed/skipped files.
    """
    source_path = Path(source_path)
    staging_path = Path(staging_path)
    allowed = PUBLISHABLE_EXTENSIONS if allowed_extensions is None else allowed_extensions

    census = ExtensionCensus()
    changes = Counter()
    traversal_stats = {}

    print("Building file index...")
    file_index, path_set = build_file_index(source_path)
    print(f"Indexed {len(file_index)} unique filenames, {len(path_set)} total paths")

    # First pass: decide what is publishable. Pages are written in a second
    # pass so that link conversion already knows which vault files were skipped
    # and can flag references that would render as broken links.
    publishable = []
    unpublished = set()

    for item, relative_path in iter_vault_files(source_path, stats=traversal_stats):
        suffix = item.suffix.lower()
        staged_relative = sanitize_relative_path(relative_path)

        # A symlinked file resolves to content outside the vault, which the
        # vault owner never reviewed. Refuse rather than dereference (S-3).
        if item.is_symlink():
            print(f"Warning: skipping symlink (target is outside vault review): {relative_path}")
            changes['skipped_symlink'] += 1
            unpublished.add(staged_relative)
            continue

        if not is_publishable_extension(suffix, allowed):
            census.record(suffix, was_published=False)
            changes['skipped_type'] += 1
            unpublished.add(staged_relative)
            continue

        if suffix == '.ipynb' and not is_valid_notebook(item):
            print(f"Warning: skipping invalid notebook: {relative_path}")
            changes['skipped_invalid'] += 1
            unpublished.add(staged_relative)
            continue

        census.record(suffix, was_published=True)
        publishable.append((item, relative_path, staged_relative, suffix))

    census.absorb_traversal_stats(traversal_stats)
    expected = {staged for _, _, staged, _ in publishable}
    manifest = load_manifest(staging_path)

    # Second pass: write.
    for item, relative_path, staged_relative, suffix in publishable:
        output_path = staging_path / staged_relative

        if dry_run:
            changes['would_write'] += 1
            continue

        if suffix == '.md':
            content = item.read_text(encoding='utf-8', errors='replace')
            content = process_markdown_content(
                content, staged_relative, file_index, path_set, unpublished
            )
            changed = write_if_changed(output_path, content)
        else:
            changed = copy_asset_if_changed(item, output_path, staged_relative, manifest)
            if changed and output_path.suffix.lower() in WEB_IMAGE_EXTENSIONS:
                try:
                    optimize_image(output_path)
                except Exception as e:
                    print(f"Warning: could not optimize {output_path}: {e}")

        changes['updated' if changed else 'unchanged'] += 1

    if not dry_run:
        # Drop entries for assets that are no longer published, so the manifest
        # does not grow forever.
        save_manifest(staging_path, {k: v for k, v in manifest.items() if k in expected})

    removed = prune_stale_files(staging_path, expected, dry_run=dry_run)
    changes['removed'] = len(removed)
    for relative in removed:
        print(f"Removed (no longer in vault): {relative}")

    return census, changes


def render_changes(changes):
    """Summarize a sync as a single printable line"""
    return (
        f"  {changes['updated']} written, "
        f"{changes['unchanged']} unchanged, "
        f"{changes['removed']} removed, "
        f"{changes['skipped_type']} skipped by type"
        + (f", {changes['skipped_symlink']} symlinks refused" if changes['skipped_symlink'] else "")
        + (f", {changes['skipped_invalid']} invalid notebooks" if changes['skipped_invalid'] else "")
    )
