"""
Vault hygiene checks.

Each check scans a vault and returns a list of issues. They are pure functions
over an already-filtered file list, so they never decide what is in scope --
that is policy.py's job, and it is why confidential folders no longer reach an
audit report.
"""

import re
from pathlib import Path

from ..policy import (
    EXCLUDED_DIRS,
    IMAGE_EXTENSIONS,
    is_excluded_name,
    iter_vault_dirs,
    iter_vault_files,
)

# =============================================================================
# CONFIGURATION
# =============================================================================
# Exclusion rules live in policy.py. This module previously kept its own copy
# that omitted the confidential-folder convention entirely, so audit reports
# listed the filenames and link targets inside `5_*` folders and wrote them to
# disk as markdown (S-1).

PASTED_IMAGE_PATTERN = re.compile(r'^Pasted[\s_]image[\s_]\d+', re.IGNORECASE)
SCREENSHOT_PATTERN = re.compile(r'^Screenshot[\s_]\d+', re.IGNORECASE)
GENERIC_NAME_PATTERN = re.compile(r'^(Untitled|New[\s_]Note|Note[\s_]\d+|Document[\s_]\d+)\.md$', re.IGNORECASE)

# Notion import patterns
# Notion exports append a 32-char hex ID to filenames, e.g. "My Page abc123def456.md"
NOTION_HEX_SUFFIX = re.compile(r'\s[0-9a-f]{32}(?:\.\w+)?$', re.IGNORECASE)
# Notion CSV exports
NOTION_CSV_PATTERN = re.compile(r'_all\.csv$|_[0-9a-f]{32}\.csv$', re.IGNORECASE)
# Notion-style folder names with hex IDs
NOTION_FOLDER_PATTERN = re.compile(r'\s[0-9a-f]{32}$', re.IGNORECASE)


# =============================================================================
# SCANNING FUNCTIONS
# =============================================================================

def should_skip_dir(dir_path):
    """Check if a path should be excluded from scanning"""
    return any(is_excluded_name(part) for part in Path(dir_path).parts)


def get_all_files(vault_path):
    """
    Get all auditable files in the vault.

    Uses the shared traversal, so confidential folders and any subtree carrying
    a .qbi-exclude marker are skipped. Audit reports are written to disk and
    may be shared, so they must never name files the vault owner has marked
    as not-for-publication.
    """
    return [absolute for absolute, _ in iter_vault_files(vault_path)]


def get_all_dirs(vault_path):
    """Get all auditable directories in the vault"""
    return [absolute for absolute, _ in iter_vault_dirs(vault_path)]


# =============================================================================
# AUDIT CHECKS
# =============================================================================

def check_pasted_images(files, vault_path):
    """Find default-named pasted images that should be renamed"""
    issues = []
    for f in files:
        if PASTED_IMAGE_PATTERN.match(f.stem) or SCREENSHOT_PATTERN.match(f.stem):
            rel = f.relative_to(vault_path)
            issues.append({
                'file': str(rel),
                'suggestion': 'Rename to something descriptive (e.g., what the image shows)'
            })
    return issues


def check_generic_filenames(files, vault_path):
    """Find generic/default note names"""
    issues = []
    for f in files:
        if GENERIC_NAME_PATTERN.match(f.name):
            rel = f.relative_to(vault_path)
            issues.append({
                'file': str(rel),
                'suggestion': 'Rename to describe the content'
            })
    return issues


def check_broken_references(files, vault_path):
    """Find wikilinks and markdown image links that point to nonexistent files"""
    md_files = [f for f in files if f.suffix == '.md']
    all_filenames = {f.name: f for f in files}
    all_filenames_lower = {f.name.lower(): f for f in files}
    all_relative_paths = {str(f.relative_to(vault_path)).replace('\\', '/'): f for f in files}

    broken = []

    for md_file in md_files:
        try:
            content = md_file.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue

        rel_md = str(md_file.relative_to(vault_path))

        # Find ![[...]] references
        for match in re.finditer(r'!\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]', content):
            ref = match.group(1).strip()
            ref_filename = Path(ref).name

            if (ref_filename not in all_filenames and
                ref_filename.lower() not in all_filenames_lower and
                ref.replace('\\', '/') not in all_relative_paths):
                broken.append({
                    'source_file': rel_md,
                    'reference': ref,
                    'type': 'wikilink',
                    'suggestion': 'File not found in vault. Rename the reference or add the missing file.'
                })

        # Find ![...](...) references
        for match in re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', content):
            url = match.group(2).strip()
            if url.startswith(('http://', 'https://', 'data:')):
                continue

            ref_filename = Path(url).name
            if (ref_filename not in all_filenames and
                ref_filename.lower() not in all_filenames_lower and
                url.replace('\\', '/') not in all_relative_paths):
                broken.append({
                    'source_file': rel_md,
                    'reference': url,
                    'type': 'markdown_link',
                    'suggestion': 'File not found in vault. Check the path or add the missing file.'
                })

    return broken


def check_image_linebreaks(files, vault_path):
    """Find images that are inline (text immediately before ![[) instead of block"""
    md_files = [f for f in files if f.suffix == '.md']
    issues = []

    for md_file in md_files:
        try:
            content = md_file.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue

        rel_md = str(md_file.relative_to(vault_path))

        # Find cases where non-whitespace immediately precedes an image
        inline_matches = re.findall(r'(\S)(\!\[\[)', content)
        if inline_matches:
            issues.append({
                'file': rel_md,
                'count': len(inline_matches),
                'suggestion': 'Add a blank line before images so they render as blocks, not inline.'
            })

        # Also check standard markdown images
        inline_md_matches = re.findall(r'(\S)(!\[)', content)
        if inline_md_matches:
            real_count = len(inline_md_matches) - len(inline_matches)
            if real_count > 0:
                issues.append({
                    'file': rel_md,
                    'count': real_count,
                    'suggestion': 'Add a blank line before markdown images so they render as blocks.'
                })

    return issues


def check_empty_files(files, vault_path):
    """Find empty or near-empty markdown files"""
    issues = []
    for f in files:
        if f.suffix == '.md':
            try:
                content = f.read_text(encoding='utf-8', errors='ignore').strip()
                if len(content) < 10:  # basically empty
                    rel = f.relative_to(vault_path)
                    issues.append({
                        'file': str(rel),
                        'suggestion': 'This file is empty or nearly empty. Add content or delete it.'
                    })
            except Exception:
                continue
    return issues


def check_notion_imports(files, vault_path):
    """Find files and folders that look like raw Notion exports"""
    issues = []
    seen_files = set()

    # Check files with Notion's 32-char hex suffix
    for f in files:
        if NOTION_HEX_SUFFIX.search(f.stem):
            rel = f.relative_to(vault_path)
            rel_str = str(rel)
            if rel_str not in seen_files:
                seen_files.add(rel_str)
                issues.append({
                    'file': rel_str,
                    'suggestion': 'This looks like a Notion import (hex ID in filename). Please consolidate into your primary lab notebook files and remove the Notion export artifacts.'
                })

        # Notion CSV exports
        if NOTION_CSV_PATTERN.search(f.name):
            rel = f.relative_to(vault_path)
            rel_str = str(rel)
            if rel_str not in seen_files:
                seen_files.add(rel_str)
                issues.append({
                    'file': rel_str,
                    'suggestion': 'This looks like a Notion CSV export. Please consolidate relevant data into your primary lab notebook files.'
                })

    # Check for Notion-style folder names with hex IDs
    dirs = get_all_dirs(vault_path)
    for d in dirs:
        if NOTION_FOLDER_PATTERN.search(d.name):
            rel = d.relative_to(vault_path)
            issues.append({
                'file': str(rel) + '/',
                'suggestion': 'This folder looks like a Notion import (hex ID in name). Please consolidate its contents into your primary lab notebook and remove the Notion export folder.'
            })

    return issues
