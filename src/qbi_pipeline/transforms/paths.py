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


def normalize_markdown_link_urls(content):
    """Sanitize URLs in standard markdown links"""
    def fix_url(match):
        prefix = match.group(1)
        text = match.group(2)
        url = match.group(3)
        sanitized_url = sanitize_path(url)
        return f'{prefix}{text}]({sanitized_url})'
    
    return re.sub(r'(!?\[)([^\]]*)\]\(([^)]+)\)', fix_url, content)


def normalize_all_paths(content):
    """Phase 1: Normalize all paths before link processing"""
    content = normalize_notion_folders(content)
    content = normalize_markdown_link_urls(content)
    return content
