"""
Markdown transforms, applied in a fixed order.

Each module holds one phase and exposes pure functions, so a phase can be
tested and reasoned about on its own. `process_markdown_content` is the only
thing that knows what order they run in.
"""

from pathlib import Path

from ..naming import prettify_folder_name
from .frontmatter import (
    find_frontmatter,
    format_title_line,
    has_title,
    inject_frontmatter,
)
from .images import MAX_IMAGE_WIDTH, optimize_image, strip_exif
from .links import convert_obsidian_links, rewrite_absolute_paths
from .paths import (
    normalize_all_paths,
    normalize_markdown_link_urls,
    normalize_notion_folders,
)
from .text import ensure_image_linebreaks, fix_text_issues

__all__ = [
    'MAX_IMAGE_WIDTH',
    'convert_obsidian_links',
    'ensure_image_linebreaks',
    'find_frontmatter',
    'fix_text_issues',
    'format_title_line',
    'has_title',
    'inject_frontmatter',
    'normalize_all_paths',
    'normalize_markdown_link_urls',
    'normalize_notion_folders',
    'optimize_image',
    'process_markdown_content',
    'rewrite_absolute_paths',
    'strip_exif',
]


def process_markdown_content(content, current_file, file_index, path_set, unpublished=None):
    """Process markdown through the full pipeline"""
    # Phase 0a - inject frontmatter title from filename
    title = prettify_folder_name(Path(current_file).stem)
    content = inject_frontmatter(content, title)

    content = ensure_image_linebreaks(content)    # Phase 0b - ensure block images
    content = normalize_all_paths(content)         # Phase 1
    content = convert_obsidian_links(content, current_file, file_index, path_set, unpublished)  # Phase 2
    content = rewrite_absolute_paths(content, current_file, path_set)  # Phase 2b
    content = fix_text_issues(content)             # Phase 3
    return content
