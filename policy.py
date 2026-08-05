"""
Publication policy: the single source of truth for what may be published.

This pipeline renders private research vaults to a PUBLIC site, so this module
is security-critical. It replaces three divergent copies of the exclusion rules
that had drifted apart in preprocessing.py, config_generator.py and
vault_audit.py -- most seriously, vault_audit.py's copy omitted the
confidential-folder rule entirely, so audit reports listed the filenames and
link targets inside `5_*` folders.

Two distinct kinds of exclusion, deliberately kept separate. Flattening them
into one list is what caused the drift, because each module needed a slightly
different answer:

  EXCLUDED          Never published, never mentioned, never traversed.
  NON_NAVIGABLE     Staged, because the files are needed as page assets, but
                    never listed in site navigation. `attachments/` is the
                    case that matters: images must be copied or every embed
                    breaks, but the folder should not appear as a chapter.

Exclusion is applied by PRUNING during traversal, not by filtering afterwards,
so an excluded subtree is never descended into at all.
"""

import os
from pathlib import Path

# A marker file researchers can drop in any folder to keep it off the website.
# Excludes the folder it sits in AND everything beneath it, recursively. The
# marker itself is never published (it starts with a dot).
QBI_EXCLUDE_MARKER = '.qbi-exclude'

# Folder naming convention for confidential material.
CONFIDENTIAL_PREFIX = '5_'

# Name prefixes that are never published: hidden files, build/internal folders,
# and the confidential convention.
EXCLUDED_PREFIXES = ('.', '_', CONFIDENTIAL_PREFIX)

# Directory names that are never published anywhere.
EXCLUDED_DIRS = frozenset({
    'venv', 'node_modules', '__pycache__', 'site-packages', '.git', '.obsidian',
    '.ipynb_checkpoints', 'dist-info', '__pypackages__', '.trash', '_build',
    '_build_staging', 'Folder Template Structure', 'Discourse Canvas',
})

# Staged so that pages can reference them, but kept out of navigation.
NON_NAVIGABLE_DIRS = frozenset({'attachments'})

# Image types a browser renders inline. Used to decide whether a vault
# reference becomes an embedded image or a download link, so it must contain
# only formats that actually display -- TIFF, for instance, does not.
WEB_IMAGE_EXTENSIONS = frozenset({
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp',
})

# Everything counted as an image for reporting purposes. A superset of the
# renderable set.
IMAGE_EXTENSIONS = WEB_IMAGE_EXTENSIONS | frozenset({'.tiff', '.tif'})


def is_confidential_name(name):
    """True if a path component uses the confidential folder convention"""
    return name.startswith(CONFIDENTIAL_PREFIX)


def is_excluded_name(name):
    """
    True if a single path component must never be published.

    Applies to files as well as directories, so a stray `5_notes.md` or
    `_draft.md` is excluded just like a folder would be.
    """
    return (
        name in EXCLUDED_DIRS
        or name.startswith(EXCLUDED_PREFIXES)
        or name.endswith('.dist-info')
    )


def is_navigable_name(name):
    """
    True if a directory may appear in site navigation.

    Stricter than `is_excluded_name`: also rejects directories that are staged
    as assets but should not be browsable, such as `attachments/`.
    """
    return not is_excluded_name(name) and name not in NON_NAVIGABLE_DIRS


def is_excluded_relative_path(relative_path):
    """True if any component of a vault-relative path is excluded"""
    return any(is_excluded_name(part) for part in Path(relative_path).parts)


def is_marked_excluded(dirpath):
    """True if this directory carries a .qbi-exclude marker"""
    return (Path(dirpath) / QBI_EXCLUDE_MARKER).is_file()


def _prune(dirnames):
    """Filter os.walk's dirnames in place so excluded subtrees are skipped"""
    dirnames[:] = sorted(d for d in dirnames if not is_excluded_name(d))


def iter_vault_files(root):
    """
    Walk a vault, yielding (absolute_path, relative_path) for publishable files.

    Excluded subtrees are pruned during traversal rather than filtered after
    the fact, so a directory carrying a .qbi-exclude marker -- or matching any
    exclusion rule -- is never descended into.

    os.walk does not follow directory symlinks, so a linked directory cannot
    pull outside content into the vault. Symlinked *files* are still yielded;
    rejecting those is a separate concern handled at the staging layer.
    """
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        if QBI_EXCLUDE_MARKER in filenames:
            dirnames[:] = []
            continue

        _prune(dirnames)
        current = Path(dirpath)

        for filename in sorted(filenames):
            if is_excluded_name(filename):
                continue
            absolute = current / filename
            yield absolute, absolute.relative_to(root)


def iter_vault_dirs(root):
    """
    Walk a vault, yielding (absolute_path, relative_path) for publishable
    directories. The root itself is not yielded.
    """
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        if QBI_EXCLUDE_MARKER in filenames:
            dirnames[:] = []
            continue

        _prune(dirnames)
        current = Path(dirpath)

        if current != root:
            yield current, current.relative_to(root)
