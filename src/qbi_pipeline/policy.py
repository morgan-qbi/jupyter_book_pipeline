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

# Image formats no browser renders inline, but which convert cleanly to one
# that does. These are published as the converted format under a rewritten
# filename -- microscopy TIFFs are the case that matters.
#
# The rename has to be applied when the vault is indexed, not just when files
# are copied: Obsidian embeds reference a bare filename with no path, so a
# lookup for `scan.tif` must resolve to the `scan.png` that staging actually
# contains, or every such link breaks.
CONVERTED_IMAGE_EXTENSIONS = {
    '.tif': '.png',
    '.tiff': '.png',
}


def staged_suffix(suffix):
    """The extension a file takes in staging, after any format conversion"""
    return CONVERTED_IMAGE_EXTENSIONS.get(suffix.lower(), suffix)


def is_converted_extension(suffix):
    """True if this format is re-encoded on the way into staging"""
    return suffix.lower() in CONVERTED_IMAGE_EXTENSIONS

# ---------------------------------------------------------------------------
# Publication allow-list
# ---------------------------------------------------------------------------
# The output of this pipeline is a public website, so file types are published
# by permission rather than by omission: anything not named here is skipped and
# reported, instead of being copied because nobody thought to forbid it.
#
# The default is deliberately conservative. Research vaults accumulate
# spreadsheets, exports and scratch files that nobody intends to publish, and
# the failure mode of a deny-list is silent disclosure. The failure mode of an
# allow-list is a missing file, which the extension census makes obvious on the
# very next build -- and extra types can be opted in via `publish_extensions`
# in the build config, without touching code.
# Video formats worth publishing at all.
WEB_VIDEO_EXTENSIONS = frozenset({'.mp4', '.webm', '.mov'})

# Video formats MyST turns into a <video> element. Verified against mystmd
# 1.6.4: `![](clip.mp4)` renders as <video>, while .mov and .webm both fall
# through to a broken <img>. Those are published as download links instead --
# an honest download beats a broken player.
#
# iPhone .mov is usually H.264 already, so remuxing to .mp4 would be lossless
# and cheap, but it needs ffmpeg as a system dependency. Not assumed here.
INLINE_VIDEO_EXTENSIONS = frozenset({'.mp4'})

# Everything that should render in the page rather than offer a download.
INLINE_EXTENSIONS = WEB_IMAGE_EXTENSIONS | INLINE_VIDEO_EXTENSIONS

PUBLISHABLE_EXTENSIONS = frozenset({
    # Pages
    '.md', '.ipynb',
    # Inline images
    *WEB_IMAGE_EXTENSIONS,
    # Converted to a renderable format on the way in (see
    # CONVERTED_IMAGE_EXTENSIONS); the original is never published.
    '.tif', '.tiff',
    # Video, played inline
    *WEB_VIDEO_EXTENSIONS,
    # Documents and 3D models offered as download links
    '.pdf', '.stl', '.obj', '.ino', '.py',
    # Bioinformatics artifacts: plasmid maps, alignments, sequences,
    # phylogenies. No browser renders these, so they are download links -- but
    # they are primary research output and belong on the site.
    '.dna', '.aln', '.fa', '.fasta', '.treefile', '.nwk', '.gb', '.genbank',
    # Tabular data
    '.csv', '.tsv',
})

# Files the pipeline writes into staging, or that are placed there by hand as
# site chrome. Never treated as stale, never pruned during a sync.
PRESERVED_STAGING_NAMES = frozenset({
    '.git', '.gitignore', '_static', 'myst.yml', '.qbi-staging',
    '.qbi-manifest.json',
})

# Written into a staging directory to mark it as owned by this pipeline.
# Sync refuses to prune a non-empty directory that lacks it, so pointing
# `output` at a real data directory cannot quietly delete its contents.
STAGING_MARKER = '.qbi-staging'


def is_publishable_extension(suffix, allowed=None):
    """True if a file extension may be copied into staging"""
    allowed = PUBLISHABLE_EXTENSIONS if allowed is None else allowed
    return suffix.lower() in allowed


def is_preserved_staging_name(name):
    """
    True if a top-level staging entry must never be pruned as stale.

    Anything beginning with `_` or `.` is preserved on principle: EXCLUDED_
    PREFIXES forbids those from vault content, so nothing this pipeline stages
    can ever start with them, and anything in staging that does belongs to
    someone else. That covers `_build` -- MyST's build cache and its theme's
    node_modules, which a running `myst start` holds open -- as well as
    `_static`, `.git`, and any artifact a future MyST version invents.
    """
    return name in PRESERVED_STAGING_NAMES or name.startswith(('_', '.'))


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


def iter_vault_files(root, stats=None):
    """
    Walk a vault, yielding (absolute_path, relative_path) for traversable files.

    Excluded subtrees are pruned during traversal rather than filtered after
    the fact, so a directory carrying a .qbi-exclude marker -- or matching any
    exclusion rule -- is never descended into.

    os.walk does not follow directory symlinks, so a linked directory cannot
    pull outside content into the vault. Symlinked *files* are still yielded;
    rejecting those is a separate concern handled at the staging layer.

    Yields everything policy allows to be *traversed*, which is deliberately
    wider than what may be *published* -- the index needs to know a file exists
    in order to warn that a page references something the allow-list skipped.

    `stats`, if given, is a dict updated with counts of what was pruned.
    Excluded subtrees are counted but never descended into, so their contents
    are reported as a directory count only and never by name.
    """
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        if QBI_EXCLUDE_MARKER in filenames:
            if stats is not None:
                stats['marked_dirs'] = stats.get('marked_dirs', 0) + 1
            dirnames[:] = []
            continue

        before = len(dirnames)
        _prune(dirnames)
        if stats is not None and before != len(dirnames):
            stats['excluded_dirs'] = stats.get('excluded_dirs', 0) + (before - len(dirnames))

        current = Path(dirpath)

        for filename in sorted(filenames):
            if is_excluded_name(filename):
                if stats is not None:
                    stats['excluded_files'] = stats.get('excluded_files', 0) + 1
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
