"""
Phase 2: Obsidian link conversion.

Turns `![[...]]` embeds into standard markdown, resolving them against the
vault index, and rewrites absolute image paths as relative ones.
"""

import posixpath
import re
from pathlib import Path

from ..naming import get_relative_path, sanitize_filename, staged_relative_path
from ..policy import INLINE_EXTENSIONS


def convert_obsidian_links(content, current_file, file_index, path_set, unpublished=None):
    """
    Convert Obsidian ![[...]] links to standard markdown.

    Handles:
    - ![[filename.png]] -> vault-wide lookup by filename
    - ![[path/to/file.png]] -> explicit path (tries relative, then absolute from root)

    `unpublished` is the set of vault paths that exist but were skipped by the
    publication allow-list. A page referencing one of those would render a link
    to a file that was never staged, so it is reported: that is the failure mode
    an allow-list has, and it is silent unless something says so.
    """
    pattern = r'!\[\[(.*?)\]\]'
    unpublished = unpublished or set()

    def warn_if_unpublished(resolved_path, reference):
        if resolved_path in unpublished:
            print(
                f"Warning: {current_file} references {reference}, which exists "
                f"in the vault but is not a published file type. The link will "
                f"be broken. Add its extension to `publish_extensions` if it "
                f"belongs on the site."
            )

    def replacement(match):
        raw_reference = match.group(1)

        # Explicit path provided
        if '/' in raw_reference or '\\' in raw_reference:
            # Resolve against where the file lands in staging, not where it sits
            # in the vault: converted formats are renamed on the way in.
            sanitized_path = staged_relative_path(raw_reference)
            filename = Path(sanitized_path).name
            ext = Path(sanitized_path).suffix.lower()

            # First, check if this is an absolute path from vault root
            if sanitized_path in path_set:
                # Rewrite as relative path from current file
                final_path = get_relative_path(current_file, sanitized_path)
            else:
                # Try as relative path (already relative, just use it)
                # Build what the full path would be and check
                current_dir = str(Path(current_file).parent).replace('\\', '/')
                if current_dir == '.':
                    candidate = sanitized_path
                else:
                    candidate = f"{current_dir}/{sanitized_path}"

                if candidate in path_set:
                    final_path = sanitized_path  # It's already relative and correct
                else:
                    # Path doesn't exist either way - leave sanitized and hope for the best
                    print(f"Warning: Path not found: {sanitized_path} (referenced in {current_file})")
                    final_path = sanitized_path

            warn_if_unpublished(sanitized_path, raw_reference)

            if ext in INLINE_EXTENSIONS:
                return f'![]({final_path})'
            else:
                return f'[Download {filename}]({final_path})'

        # Filename only - vault-wide lookup
        sanitized_lookup = sanitize_filename(raw_reference)

        if sanitized_lookup not in file_index:
            print(f"Warning: File not found in index: {raw_reference} (referenced in {current_file})")
            return f'![[{raw_reference}]]'

        file_path = file_index[sanitized_lookup]
        if isinstance(file_path, list):
            print(f"Warning: Multiple files named '{raw_reference}', using {file_path[0]}")
            file_path = file_path[0]

        rel_path = get_relative_path(current_file, file_path)
        # The staged extension decides embed-vs-download: a .tif is published as
        # a .png and must render inline, not offer itself as a download.
        ext = Path(file_path).suffix.lower()
        warn_if_unpublished(file_path, raw_reference)

        if ext in INLINE_EXTENSIONS:
            return f'![]({rel_path})'
        else:
            return f'[Download {raw_reference}]({rel_path})'

    return re.sub(pattern, replacement, content)


def rewrite_absolute_paths(content, current_file, path_set, file_index=None):
    """
    Resolve standard markdown image links against the vault.

    Obsidian does not require link paths to be correct relative to the page
    they sit on -- it resolves them by searching the vault, so a note in
    `2025/` can write `attachments/plot.png` for a file that actually lives in
    the parent folder's `attachments/`. Those paths are wrong as literal
    relative links and the image silently fails to render once published.

    Three resolutions are tried, in order of how confident we can be:

    1. an exact vault-root path -> rewritten relative to this page
    2. already correct relative to this page -> left alone
    3. otherwise, a vault-wide lookup on the filename, which is what Obsidian
       itself would have done
    """
    # Both images and plain links: a link to a notebook or a dataset suffers
    # from exactly the same loose-path problem as an image.
    pattern = r'(!?)\[([^\]]*)\]\(([^)]+)\)'

    def replacement(match):
        bang = match.group(1)
        alt_text = match.group(2)
        url = match.group(3)

        # Skip external URLs and in-page anchors
        if url.startswith(('http://', 'https://', 'data:', 'mailto:', '#', '//')):
            return match.group(0)

        # Resolve to the staged name, so a standard markdown link to a
        # converted format points at the file staging actually holds.
        sanitized_url = staged_relative_path(url)

        # 1. An absolute path from the vault root.
        if sanitized_url in path_set:
            return f'{bang}[{alt_text}]({get_relative_path(current_file, sanitized_url)})'

        # 2. Already correct relative to this page.
        current_dir = posixpath.dirname(str(current_file).replace('\\', '/'))
        candidate = posixpath.normpath(
            posixpath.join(current_dir, sanitized_url) if current_dir else sanitized_url
        )
        if candidate in path_set:
            return match.group(0)

        # 3. Fall back to a vault-wide filename lookup.
        if file_index:
            target = file_index.get(sanitize_filename(posixpath.basename(sanitized_url)))
            if isinstance(target, list):
                print(
                    f"Warning: {current_file} references {url}, and several files "
                    f"share that name; using {target[0]}"
                )
                target = target[0]
            if target:
                return f'{bang}[{alt_text}]({get_relative_path(current_file, target)})'

        return f'{bang}[{alt_text}]({sanitized_url})'

    return re.sub(pattern, replacement, content)
