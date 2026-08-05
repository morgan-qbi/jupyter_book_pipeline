import re
import shutil
from pathlib import Path
import sys
from PIL import Image, ImageOps
import json
import yaml

from policy import WEB_IMAGE_EXTENSIONS, iter_vault_files
# Re-exported so existing callers and tests keep working; these now have a
# single implementation each rather than one copy per module.
from naming import (  # noqa: F401
    get_relative_path,
    prettify_folder_name,
    sanitize_filename,
    sanitize_path,
    sanitize_relative_path,
)

sys.stdout.reconfigure(encoding='utf-8')

# =============================================================================
# CONFIGURATION
# =============================================================================
# Exclusion rules and image extensions live in policy.py -- see that module for
# why publication and navigation exclusions are kept separate.

MAX_IMAGE_WIDTH = 1200  # pixels


# =============================================================================
# PHASE 0a: FRONTMATTER INJECTION
# Ensure every file has a title in frontmatter so MyST uses it
# =============================================================================

FRONTMATTER_DELIMITER = '---'
FRONTMATTER_TERMINATORS = (FRONTMATTER_DELIMITER, '...')


def format_title_line(title):
    """
    Render `title: <value>` as valid YAML.

    Delegates quoting and escaping to PyYAML rather than hand-rolling it, so
    titles containing colons, apostrophes, or both are emitted correctly.
    `width` is raised to stop the emitter line-wrapping long titles.
    """
    return yaml.safe_dump(
        {'title': title},
        default_flow_style=False,
        allow_unicode=True,
        width=4096,
    ).strip()


def find_frontmatter(content):
    """
    Locate an existing YAML frontmatter block.

    Returns (body, insert_at), where `body` is the YAML text between the
    delimiters and `insert_at` is the offset just past the opening delimiter
    line -- the correct splice point for a new key.

    Returns (None, None) when there is no usable frontmatter: either the
    content does not open with a bare `---` line, or that line is never closed.
    A `---` followed by text on the same line is a horizontal rule, not a
    delimiter, and is treated as body content.
    """
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return None, None

    for i, line in enumerate(lines[1:], start=1):
        if line.strip() in FRONTMATTER_TERMINATORS:
            return ''.join(lines[1:i]), len(lines[0])

    return None, None


def has_title(frontmatter_body):
    """
    True if the frontmatter already defines a top-level `title` key.

    Parses rather than substring-matching, so keys like `subtitle:` are not
    mistaken for an existing title.
    """
    try:
        parsed = yaml.safe_load(frontmatter_body)
    except yaml.YAMLError:
        # Malformed YAML: fall back to a conservative textual check so we never
        # clobber something that may already be a title.
        return 'title:' in frontmatter_body

    return isinstance(parsed, dict) and 'title' in parsed


def inject_frontmatter(content, title):
    """Add MyST frontmatter with a title, preserving any existing frontmatter"""
    body, insert_at = find_frontmatter(content)

    if body is None:
        return (
            f'{FRONTMATTER_DELIMITER}\n'
            f'{format_title_line(title)}\n'
            f'{FRONTMATTER_DELIMITER}\n\n'
            f'{content}'
        )

    if has_title(body):
        return content

    # Splice the title in as the first key, after the opening delimiter.
    newline = '\r\n' if content[:insert_at].endswith('\r\n') else '\n'
    return content[:insert_at] + format_title_line(title) + newline + content[insert_at:]


# =============================================================================
# PHASE 0b: IMAGE LINEBREAKS
# Ensure images are on their own line for block rendering
# =============================================================================

def ensure_image_linebreaks(content):
    """Ensure images render as blocks, not inline"""
    # If there's text immediately before ![[, split it to a new line
    content = re.sub(r'(\S)(\!\[\[)', r'\1\n\n\2', content)
    # Ensure blank line before ![[ even if already on own line (e.g. inside lists)
    content = re.sub(r'(?<!\n)\n([ \t]*\!\[\[)', r'\n\n\1', content)
    # Same for standard markdown images
    content = re.sub(r'(?<!\n)\n([ \t]*!\[)', r'\n\n\1', content)
    return content


# =============================================================================
# PHASE 1: PATH NORMALIZATION
# =============================================================================

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


# =============================================================================
# PHASE 2: LINK CONVERSION
# =============================================================================

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


def convert_obsidian_links(content, current_file, file_index, path_set):
    """
    Convert Obsidian ![[...]] links to standard markdown.
    
    Handles:
    - ![[filename.png]] -> vault-wide lookup by filename
    - ![[path/to/file.png]] -> explicit path (tries relative, then absolute from root)
    """
    pattern = r'!\[\[(.*?)\]\]'
    
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


# =============================================================================
# PHASE 3: TEXT CLEANUP
# =============================================================================

def fix_text_issues(content):
    """Fix text formatting issues that break MyST"""
    content = content.replace('\u2013', '-')  # en-dash
    content = content.replace('\u2014', '-')  # em-dash
    content = content.replace('\u2212', '-')  # minus sign
    content = content.replace('@', '\\@')
    return content

# =============================================================================
# PHASE 4: IMAGE OPTIMIZATION
# =============================================================================

def optimize_image(image_path):
    """Resize and compress images for web delivery"""
    return  # DISABLED for now — skipping optimization, images ship as-is
    
    """
    ext = image_path.suffix.lower()
    if ext not in {'.jpg', '.jpeg', '.png', '.webp'}:
        return  # skip SVG, GIF, BMP

    try:
        img = Image.open(image_path)
        img.load()  # force full read before any save (avoids streamed-PNG _idat bug)
        img = ImageOps.exif_transpose(img)  # apply EXIF rotation to actual pixels

        if img.width > MAX_IMAGE_WIDTH:
            ratio = MAX_IMAGE_WIDTH / img.width
            new_height = int(img.height * ratio)
            img = img.resize((MAX_IMAGE_WIDTH, new_height), Image.LANCZOS)

        # Save with compression
        if ext in {'.jpg', '.jpeg'}:
            img.save(image_path, quality=80, optimize=True)
        elif ext == '.png':
            img.save(image_path, optimize=True)
        elif ext == '.webp':
            img.save(image_path, quality=80)

    except Exception as e:
        print(f"  [skip] couldn't optimize {image_path}: {e}")
        return  # leave original in place, keep the build going
    """
# =============================================================================
# MAIN PROCESSING PIPELINE
# =============================================================================

def process_markdown_content(content, current_file, file_index, path_set):
    """Process markdown through the full pipeline"""
    # Phase 0a - inject frontmatter title from filename
    title = prettify_folder_name(Path(current_file).stem)
    content = inject_frontmatter(content, title)
    
    content = ensure_image_linebreaks(content)    # Phase 0b - ensure block images
    content = normalize_all_paths(content)         # Phase 1
    content = convert_obsidian_links(content, current_file, file_index, path_set)  # Phase 2
    content = rewrite_absolute_paths(content, current_file, path_set)  # Phase 2b
    content = fix_text_issues(content)             # Phase 3
    return content


def process_markdown_file(file_path, output_path, file_index, path_set, source_root):
    """Read markdown file, process it, write to output"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        relative_file_path = file_path.relative_to(source_root)
        sanitized_relative_str = sanitize_relative_path(relative_file_path)

        content = process_markdown_content(content, sanitized_relative_str, file_index, path_set)
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return True
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False


def create_staging_directory(source_path, staging_path):
    """Create staging directory with processed files"""
    source_path = Path(source_path)
    staging_path = Path(staging_path)
    
    if staging_path.exists():
        shutil.rmtree(staging_path)
    staging_path.mkdir(parents=True)
    
    print(f"Creating staging directory: {staging_path}")
    print("Building file index...")
    file_index, path_set = build_file_index(source_path)
    print(f"Indexed {len(file_index)} unique filenames, {len(path_set)} total paths")
    
    for item, relative_path in iter_vault_files(source_path):
        output_path = staging_path / sanitize_relative_path(relative_path)

        if item.suffix == '.md':
            print(f"Processing: {relative_path}")
            process_markdown_file(item, output_path, file_index, path_set, source_path)
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if item.suffix == '.ipynb':
                try:
                    with open(item, encoding='utf-8') as f:
                        json.load(f)
                except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
                    print(f"⚠️  Skipping invalid notebook: {relative_path}")
                    continue
            shutil.copy2(item, output_path)
            if output_path.suffix.lower() in WEB_IMAGE_EXTENSIONS:
                try:
                    optimize_image(output_path)
                except Exception as e:
                    print(f"Warning: Could not optimize {output_path}: {e}")


    print(f"Staging directory created at {staging_path}")
    return staging_path


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    test_content = """Here's a Notion image: ![](Lab%20Notebook%20216be76e722280c380fad6c0fc508250/test.png)
Another Notion style: ![image.png](__attachments/image%203.png)
Measured @50 mT with en-dash range 10\u201320.
An inline image that should get a linebreak: here's data ![[my image.png]]
An Obsidian path: ![[subfolder/another image.png]]
A list with an image:
* Some bullet point
  ![[chart.png]]
"""
    print("=== Original ===")
    print(test_content)
    
    print("\n=== After inject_frontmatter ===")
    result = inject_frontmatter(test_content, "Test Document")
    print(result)
    
    print("\n=== After ensure_image_linebreaks ===")
    result = ensure_image_linebreaks(result)
    print(result)
    
    print("\n=== After normalize_all_paths ===")
    result = normalize_all_paths(result)
    print(result)
    
    print("\n=== After fix_text_issues ===")
    result = fix_text_issues(result)
    print(result)