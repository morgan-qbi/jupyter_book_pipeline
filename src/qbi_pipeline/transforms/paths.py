"""
Phase 1: path normalization.

Runs before link conversion so that everything downstream sees sanitized,
forward-slash paths.
"""

import re

from ..naming import sanitize_path


def normalize_notion_folders(content):
    """Fix Notion's weird export folder names"""
    content = re.sub(
        r'Lab%20Notebook%20[a-f0-9]+/',
        'attachments/',
        content,
        flags=re.IGNORECASE
    )
    content = content.replace('__attachments/', 'attachments/')
    return content


# Anything with a scheme, a protocol-relative prefix, or a page anchor is not a
# path into the vault and must be left exactly as written.
EXTERNAL_URL_PREFIXES = ('http://', 'https://', 'data:', 'mailto:', 'ftp://', '//', '#')


def is_external_url(url):
    """True if a link target points outside the vault"""
    return url.strip().startswith(EXTERNAL_URL_PREFIXES)


def normalize_markdown_link_urls(content):
    """
    Sanitize URLs in standard markdown links.

    External URLs are skipped (S-15). Sanitizing rewrites `%20` and spaces to
    underscores, which is right for a vault path and wrong for a remote one --
    it turned `https://example.org/my%20paper.pdf` into `.../my_paper.pdf` and
    broke the link.
    """
    def fix_url(match):
        prefix, text, url = match.group(1), match.group(2), match.group(3)
        if is_external_url(url):
            return match.group(0)
        return f'{prefix}{text}]({sanitize_path(url)})'

    return re.sub(r'(!?\[)([^\]]*)\]\(([^)]+)\)', fix_url, content)


def normalize_all_paths(content):
    """Phase 1: Normalize all paths before link processing"""
    content = normalize_notion_folders(content)
    content = normalize_markdown_link_urls(content)
    return content
