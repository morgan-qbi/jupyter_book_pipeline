"""
Phase 2: Obsidian link conversion.

Turns `![[...]]` embeds into standard markdown, resolving them against the
vault index, and rewrites absolute image paths as relative ones.
"""

import re
from pathlib import Path

from ..naming import get_relative_path, sanitize_filename, sanitize_path
from ..policy import WEB_IMAGE_EXTENSIONS

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
            sanitized_path = sanitize_path(raw_reference)
            filename = Path(raw_reference).name
            ext = Path(raw_reference).suffix.lower()
            
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

            if ext in WEB_IMAGE_EXTENSIONS:
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
        ext = Path(raw_reference).suffix.lower()
        warn_if_unpublished(file_path, raw_reference)

        if ext in WEB_IMAGE_EXTENSIONS:
            return f'![]({rel_path})'
        else:
            return f'[Download {raw_reference}]({rel_path})'
    
    return re.sub(pattern, replacement, content)


def rewrite_absolute_paths(content, current_file, path_set):
    """
    Check standard markdown image links for absolute paths and rewrite as relative.
    """
    pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
    
    def replacement(match):
        alt_text = match.group(1)
        url = match.group(2)
        
        # Skip external URLs
        if url.startswith(('http://', 'https://', 'data:')):
            return match.group(0)
        
        sanitized_url = sanitize_path(url)
        
        # Check if this is an absolute path from vault root
        if sanitized_url in path_set:
            # Rewrite as relative from current file
            sanitized_url = get_relative_path(current_file, sanitized_url)
        
        return f'![{alt_text}]({sanitized_url})'
    
    return re.sub(pattern, replacement, content)
