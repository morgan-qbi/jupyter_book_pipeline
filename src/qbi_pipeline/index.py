"""
Vault file index.

Maps sanitized filenames and paths to their location in the vault, so that
`![[some file.png]]` can be resolved without knowing where it lives.

The index deliberately covers everything policy allows to be *traversed*, which
is wider than what may be *published* -- link conversion needs to know a file
exists in order to warn that a page references something the allow-list skipped.
"""

from .naming import sanitize_filename, staged_relative_path
from .policy import iter_vault_files


def build_file_index(source_path):
    """
    Build indices for file lookup.

    Returns:
        file_index: sanitized *vault* filename -> *staged* relative path
        path_set:   every staged relative path, for O(1) existence checks

    Keys are the names as written in the vault; values are where the file
    actually lands in staging. Those differ whenever a format is converted on
    the way in, so a `![[scan.tif]]` embed -- which carries no path at all --
    resolves to the `scan.png` that staging contains.
    """
    file_index = {}
    path_set = set()

    for item, relative_path in iter_vault_files(source_path):
        sanitized_path_str = staged_relative_path(relative_path)
        sanitized_filename = sanitize_filename(item.name)

        # Add to path set for O(1) "does this path exist" checks
        path_set.add(sanitized_path_str)

        # Add to filename index for vault-wide lookup
        if sanitized_filename in file_index:
            existing = file_index[sanitized_filename]
            if not isinstance(existing, list):
                file_index[sanitized_filename] = [existing]
            file_index[sanitized_filename].append(sanitized_path_str)
        else:
            file_index[sanitized_filename] = sanitized_path_str

    report_ambiguous_names(file_index)
    return file_index, path_set


# How many of the worst offenders to name. Enough to recognize the pattern --
# usually one analysis script writing the same plot filenames into every run
# folder -- without turning the summary back into the listing it replaces.
AMBIGUOUS_NAMES_SHOWN = 5


def report_ambiguous_names(file_index):
    """
    Summarize the filenames that more than one file claims.

    This used to print every duplicate name and every path it resolved to. On a
    vault of generated analysis plots that ran to tens of thousands of lines
    and buried the extension census and the link warnings underneath it.

    The listing was also reporting the wrong thing. A shared filename is only a
    problem when a page refers to it by filename alone, and link conversion
    already warns at exactly that point, naming the page, the reference and the
    copy it picked. Nothing here can say which duplicates matter; what it can
    say, and all it says now, is how much ambiguity the vault carries.
    """
    ambiguous = {
        name: paths for name, paths in file_index.items() if isinstance(paths, list)
    }
    if not ambiguous:
        return

    copies = sum(len(paths) for paths in ambiguous.values())
    print(f"  Ambiguous filenames: {len(ambiguous):,} names shared by {copies:,} files.")

    worst = sorted(ambiguous.items(), key=lambda item: (-len(item[1]), item[0]))
    for name, paths in worst[:AMBIGUOUS_NAMES_SHOWN]:
        print(f"    {name} ({len(paths)} copies)")
    if len(worst) > AMBIGUOUS_NAMES_SHOWN:
        print(f"    ... and {len(worst) - AMBIGUOUS_NAMES_SHOWN:,} more")

    print(
        "    Only matters where a page links one by filename alone: that page "
        "is warned about individually."
    )
