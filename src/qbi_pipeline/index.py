"""
Vault file index.

Maps sanitized filenames and paths to their location in the vault, so that
`![[some file.png]]` can be resolved without knowing where it lives.

The index deliberately covers everything policy allows to be *traversed*, which
is wider than what may be *published* -- link conversion needs to know a file
exists in order to warn that a page references something the allow-list skipped.
"""

from .naming import sanitize_filename, sanitize_relative_path
from .policy import iter_vault_files

def build_file_index(source_path):
    """
    Build indices for file lookup.
    
    Returns:
        file_index: dict mapping sanitized filename -> relative path (for vault-wide lookup)
        path_set: set of all sanitized full paths (for O(1) existence checks)
    """
    file_index = {}
    path_set = set()

    for item, relative_path in iter_vault_files(source_path):
        sanitized_path_str = sanitize_relative_path(relative_path)
        sanitized_filename = sanitize_filename(item.name)

        # Add to path set for O(1) "does this path exist" checks
        path_set.add(sanitized_path_str)

        # Add to filename index for vault-wide lookup
        if sanitized_filename in file_index:
            if not isinstance(file_index[sanitized_filename], list):
                print(f"Found duplicate: {sanitized_filename}")
                print(f"   First:  {file_index[sanitized_filename]}")
                file_index[sanitized_filename] = [file_index[sanitized_filename]]
            print(f"   Another: {sanitized_path_str}")
            file_index[sanitized_filename].append(sanitized_path_str)
        else:
            file_index[sanitized_filename] = sanitized_path_str

    return file_index, path_set
