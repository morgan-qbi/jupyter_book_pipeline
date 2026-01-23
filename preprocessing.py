import re
import shutil
from pathlib import Path
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

# =============================================================================
# CONFIGURATION
# =============================================================================

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp'}

# =============================================================================
# PATH UTILITIES
# =============================================================================

def sanitize_filename(filename):
    """Replace spaces and URL-encoded spaces with underscores"""
    return filename.replace('%20', '_').replace(' ', '_')


def sanitize_path(path_str):
    """Sanitize all parts of a path"""
    parts = path_str.replace('\\', '/').split('/')
    return '/'.join(sanitize_filename(part) for part in parts)


def get_relative_path(from_file, to_file):
    """Calculate relative path from one file to another"""
    from_dir = Path(from_file).parent
    try:
        rel_path = os.path.relpath(to_file, from_dir)
        return rel_path.replace('\\', '/')
    except ValueError:
        return str(to_file).replace('\\', '/')


# =============================================================================
# PHASE 0: IMAGE LINEBREAKS
# Ensure images are on their own line for block rendering
# =============================================================================

def ensure_image_linebreaks(content):
    """Ensure images render as blocks, not inline"""
    # If there's text immediately before ![[, split it to a new line
    # Match: any non-whitespace character followed by ![[
    content = re.sub(r'(\S)(\!\[\[)', r'\1\n\n\2', content)
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
        file_index: dict mapping sanitized filename → relative path (for vault-wide lookup)
        path_set: set of all sanitized full paths (for O(1) existence checks)
    """
    source_path = Path(source_path)
    file_index = {}
    path_set = set()
    
    for item in source_path.rglob('*'):
        if any(part.startswith(('.', '_')) for part in item.relative_to(source_path).parts):
            continue
        
        if item.is_file():
            relative_path = item.relative_to(source_path)
            sanitized_path = Path(*[sanitize_filename(part) for part in relative_path.parts])
            sanitized_path_str = str(sanitized_path).replace('\\', '/')
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
    - ![[filename.png]] → vault-wide lookup by filename
    - ![[path/to/file.png]] → explicit path (tries relative, then absolute from root)
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
            
            if ext in IMAGE_EXTENSIONS:
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
        
        if ext in IMAGE_EXTENSIONS:
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
    content = content.replace('–', '-')  # en-dash
    content = content.replace('—', '-')  # em-dash
    content = content.replace('−', '-')  # minus sign
    content = content.replace('@', '\\@')
    return content


# =============================================================================
# MAIN PROCESSING PIPELINE
# =============================================================================

def process_markdown_content(content, current_file, file_index, path_set):
    """Process markdown through the full pipeline"""
    content = ensure_image_linebreaks(content)  # Phase 0 - ensure block images
    content = normalize_all_paths(content)       # Phase 1
    content = convert_obsidian_links(content, current_file, file_index, path_set)  # Phase 2
    content = rewrite_absolute_paths(content, current_file, path_set)  # Phase 2b
    content = fix_text_issues(content)           # Phase 3
    return content


def process_markdown_file(file_path, output_path, file_index, path_set, source_root):
    """Read markdown file, process it, write to output"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        relative_file_path = file_path.relative_to(source_root)
        sanitized_relative_path = Path(*[sanitize_filename(part) for part in relative_file_path.parts])
        sanitized_relative_str = str(sanitized_relative_path).replace('\\', '/')
        
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
    
    for item in source_path.rglob('*'):
        if any(part.startswith(('.', '_')) for part in item.relative_to(source_path).parts):
            continue
        
        if item.is_file():
            relative_path = item.relative_to(source_path)
            sanitized_relative = Path(*[sanitize_filename(part) for part in relative_path.parts])
            output_path = staging_path / sanitized_relative
            
            if item.suffix == '.md':
                print(f"Processing: {relative_path}")
                process_markdown_file(item, output_path, file_index, path_set, source_path)
            else:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, output_path)
    
    print(f"Staging directory created at {staging_path}")
    return staging_path


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    test_content = """Here's a Notion image: ![](Lab%20Notebook%20216be76e722280c380fad6c0fc508250/test.png)
Another Notion style: ![image.png](__attachments/image%203.png)
Measured @50 mT with en-dash range 10–20.
An inline image that should get a linebreak: here's data ![[my image.png]]
An Obsidian path: ![[subfolder/another image.png]]
"""
    print("=== Original ===")
    print(test_content)
    
    print("\n=== After ensure_image_linebreaks ===")
    result = ensure_image_linebreaks(test_content)
    print(result)
    
    print("\n=== After normalize_all_paths ===")
    result = normalize_all_paths(result)
    print(result)
    
    print("\n=== After fix_text_issues ===")
    result = fix_text_issues(result)
    print(result)
