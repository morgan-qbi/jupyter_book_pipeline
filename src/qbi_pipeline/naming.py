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
import re
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

# Terms that are written lowercase on disk but are not lowercase words.
#
# Capitalization already present in a folder or file name is preserved, so this
# table is only needed for names people typed in lowercase: `mfe_fit_analysis`
# has nothing to preserve, while `NI_DAQ_testing` and `HsuLOV` do. Add entries
# here as new instruments and constructs turn up.
ACRONYMS = {
    'ac': 'AC', 'adc': 'ADC', 'afm': 'AFM', 'api': 'API', 'csv': 'CSV',
    'dac': 'DAC', 'daq': 'DAQ', 'dc': 'DC', 'dna': 'DNA', 'eln': 'ELN',
    'epr': 'EPR', 'esr': 'ESR', 'fad': 'FAD', 'fmn': 'FMN', 'gui': 'GUI',
    'hplc': 'HPLC', 'ir': 'IR', 'kbet': 'kBET', 'led': 'LED', 'lov': 'LOV',
    'mfe': 'MFE', 'ni': 'NI', 'nmr': 'NMR', 'odmr': 'ODMR', 'pcr': 'PCR',
    'ph': 'pH', 'pid': 'PID', 'qbi': 'QBI', 'rf': 'RF', 'rna': 'RNA',
    'sem': 'SEM', 'stl': 'STL', 'tem': 'TEM', 'ttl': 'TTL', 'usb': 'USB',
    'uv': 'UV',
}

# An ordering prefix: one or two digits and an underscore, as in `1_eln` or
# `01_basic_tutorial`. Capped at two digits on purpose -- a greedy strip also
# ate the date off `20250918_maglov2_rampdown.md`, and a folder of entries
# distinguished only by date collapses to one repeated title. It also leaves
# the model count on `4state_kBET`, which has no underscore after the digit.
ORDERING_PREFIX = re.compile(r'^\d{1,2}_')


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


def capitalize_word(word):
    """
    Capitalize a word, unless it is already telling us how it wants to be cased.

    A word carrying any capital is left exactly as written. In this field the
    case is the meaning: `pRSETb` and `phrB` are lowercase-first by convention,
    `0p5mT` is a field strength of 0.5 mT, and `NDTiffStack` and `MagLOV2` are
    product and construct names. Capitalizing the first letter of those is as
    wrong as `str.title()` lowercasing the rest.

    Only an all-lowercase word has nothing to preserve, and that is the one
    the ACRONYMS table exists for.
    """
    if not word or any(character.isupper() for character in word):
        return word
    if word in ACRONYMS:
        return ACRONYMS[word]
    if not word[0].isalpha():
        # `4state`, `2025` -- a leading digit is not something to capitalize.
        return word
    return word[0].upper() + word[1:]


def prettify_folder_name(folder_name):
    """
    Convert a folder or file name to a display title.

    Existing capitalization is preserved: `NI_DAQ_testing` is what someone
    meant to write, and `str.title()` turned it into `Ni Daq Testing`, along
    with `LOV_domain_phylogenetics` -> `Lov Domain...` and `HsuLOV` -> `Hsulov`.
    It also mangled apostrophes, so `Morgan's_notes` became `Morgan'S Notes`.
    Names typed in lowercase have no capitals to preserve, so those go through
    the ACRONYMS table.
    """
    name = ORDERING_PREFIX.sub('', folder_name, count=1)
    if not name:
        return folder_name

    words = name.replace('_', ' ').replace('-', ' ').split(' ')
    return ' '.join(capitalize_word(word) for word in words)


def get_display_name(folder_name):
    """Get the display name for a folder, checking overrides first"""
    return DISPLAY_NAMES.get(folder_name, prettify_folder_name(folder_name))
