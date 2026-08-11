"""
Naming and path helpers.

Single source of truth for turning on-disk names into display names and for
sanitizing filenames for the web.

`prettify_folder_name` previously existed in four places with three different
behaviors: the copy in preprocessing.py neither handled hyphens (so every
real vault name, e.g. `research-biology-la`, rendered as `Research-Biology-La`)
nor guarded against names made entirely of digits (so a `2025` folder produced
an empty string). This module carries the corrected implementation, and every
caller now uses it.
"""

import os
from pathlib import Path

# Display-name overrides for vault and project folder names.
# Keys are the folder names on disk, values are exact display names.
# Anything not listed falls through to prettify_folder_name().
DISPLAY_NAMES = {
    'ecoli_flavoprotein_expression': 'E. coli Flavoprotein Expression',
    'research-biology-la': 'Research: Biology LA',
    'research-biology-md': 'Research: Biology MD',
    'research-bio-redox': 'Research: Bio Redox',
    'bacterioscope': 'Bacterioscope',
    'research-physics-la': 'Research: Physics LA',
    'research-physics-theory': 'Research: Physics Theory',
}


def sanitize_filename(filename):
    """Replace spaces and URL-encoded spaces with underscores"""
    return filename.replace('%20', '_').replace(' ', '_')


def sanitize_path(path_str):
    """Sanitize all parts of a path"""
    parts = path_str.replace('\\', '/').split('/')
    return '/'.join(sanitize_filename(part) for part in parts)


def sanitize_relative_path(relative_path):
    """Sanitize every component of a Path and return it as a forward-slash string"""
    sanitized = Path(*[sanitize_filename(part) for part in Path(relative_path).parts])
    return str(sanitized).replace('\\', '/')


def staged_relative_path(relative_path):
    """
    Where a vault file lands in staging: sanitized, and with its extension
    rewritten if the format is converted on the way in (e.g. .tif -> .png).

    Everything that resolves a link must go through this, so that a reference
    to `scan.tif` points at the `scan.png` staging actually contains.
    """
    from .policy import staged_suffix

    sanitized = sanitize_relative_path(relative_path)
    path = Path(sanitized)
    new_suffix = staged_suffix(path.suffix)

    if new_suffix == path.suffix:
        return sanitized
    return str(path.with_suffix(new_suffix)).replace('\\', '/')


def get_relative_path(from_file, to_file):
    """Calculate relative path from one file to another"""
    from_dir = Path(from_file).parent
    try:
        rel_path = os.path.relpath(to_file, from_dir)
        return rel_path.replace('\\', '/')
    except ValueError:
        return str(to_file).replace('\\', '/')


def prettify_folder_name(folder_name):
    """Convert a folder name to Title Case with spaces"""
    name = folder_name.lstrip('0123456789_')
    if not name:
        # Name is only digits and underscores (e.g. "2025"); keep it as-is
        # rather than returning an empty string.
        return folder_name
    name = name.replace('_', ' ').replace('-', ' ')
    return name.title()


def get_display_name(folder_name):
    """Get the display name for a folder, checking overrides first"""
    return DISPLAY_NAMES.get(folder_name, prettify_folder_name(folder_name))
