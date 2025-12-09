import re
import shutil
from pathlib import Path
import urllib.parse
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')


def sanitize_filename(filename):
    """Replace spaces and %20 with underscores"""
    return filename.replace('%20', '_').replace(' ', '_')


def fix_text_issues(content):
    """Fix text formatting issues that break MyST"""
    # Replace fancy dashes with regular hyphen, begone en- and em-dashes!
    content = content.replace('–', '-')  # en-dash (U+2013)
    content = content.replace('—', '-')  # em-dash (U+2014)
    content = content.replace('−', '-')  # minus sign (U+2212)
    
    # Escape @ symbols so they aren't parsed as citations
    # Scientists write @50 mT, @ALE, etc.
    content = content.replace('@', '\\@')
    
    return content


def fix_notion_export_paths(content):
    """Fix Notion's URL-encoded export folder names to point to attachments/"""
    # Notion exports create folders like "Lab%20Notebook%20216be76e722280c380fad6c0fc508250/"
    # The actual images end up in attachments/
    pattern = r'Lab%20Notebook%20[a-f0-9]+/'
    content = re.sub(pattern, 'attachments/', content, flags=re.IGNORECASE)
    return content


def build_file_index(source_path):
    """
    Build an index of all files in the project
    Returns: dict mapping filename -> relative path from source_path
    """
    source_path = Path(source_path)
    file_index = {}
    
    for item in source_path.rglob('*'):
        if any(part.startswith(('.', '_')) for part in item.relative_to(source_path).parts):
            continue
        if item.is_file():
            relative_path = item.relative_to(source_path)
            
            # Sanitize the path
            sanitized_path = Path(*[sanitize_filename(part) for part in relative_path.parts])
            
            filename = item.name
            sanitized_filename = sanitize_filename(filename)
            
            # Only index the sanitized version
            if sanitized_filename in file_index:
                if not isinstance(file_index[sanitized_filename], list):
                    print(f"Found duplicate: {sanitized_filename}")
                    print(f"   First:  {file_index[sanitized_filename]}")
                    file_index[sanitized_filename] = [file_index[sanitized_filename]]
                
                print(f"   Another: {str(sanitized_path)}")
                file_index[sanitized_filename].append(str(sanitized_path))
            else:
                file_index[sanitized_filename] = str(sanitized_path)
    
    return file_index


def get_relative_path(from_file, to_file):
    """
    Calculate relative path from one file to another
    """
    from_file = Path(from_file)
    to_file = Path(to_file)
    
    # Get the directory of the source file
    from_dir = from_file.parent
    
    # Calculate relative path
    try:
        rel_path = os.path.relpath(to_file, from_dir)
        return rel_path.replace('\\', '/')  # Use forward slashes for web
    except ValueError:
        # If on different drives on Windows, return absolute path
        return str(to_file).replace('\\', '/')


def convert_obsidian_links_with_lookup(text, current_file, file_index):
    """
    Convert Obsidian links using file index for lookup.
    
    Handles two cases:
    1. ![[filename.png]] - vault-wide lookup by filename
    2. ![[path/to/filename.png]] - explicit path, use directly
    """
    pattern = r'!\[\[(.*?)\]\]'
    
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp'}
    
    def replacement(match):
        raw_reference = match.group(1)
        
        # Check if this is a path or just a filename
        if '/' in raw_reference or '\\' in raw_reference:
            # Obsidian gave us an explicit path - sanitize and use it directly
            path_parts = raw_reference.replace('\\', '/').split('/')
            sanitized_path = '/'.join(sanitize_filename(part) for part in path_parts)
            file_ext = Path(raw_reference).suffix.lower()
            filename = Path(raw_reference).name
            
            if file_ext in image_extensions:
                return f'![]({sanitized_path})'
            else:
                return f'[Download {filename}]({sanitized_path})'
        
        # No path separator - do the vault-wide lookup by filename only
        filename = raw_reference
        sanitized_lookup = sanitize_filename(filename)
        
        if sanitized_lookup not in file_index:
            print(f"Warning: File not found in index: {filename} (referenced in {current_file})")
            # Leave it unconverted so it's obvious what's broken
            return f'![[{filename}]]'
        
        file_path = file_index[sanitized_lookup]
        
        if isinstance(file_path, list):
            file_path = file_path[0]
            print(f"Warning: Multiple files named '{filename}', using {file_path}")
        
        # Calculate relative path from current file to target file
        rel_path = get_relative_path(current_file, file_path)
        file_ext = Path(filename).suffix.lower()
        
        if file_ext in image_extensions:
            return f'![]({rel_path})'
        else:
            return f'[Download {filename}]({rel_path})'
    
    return re.sub(pattern, replacement, text)


def process_markdown_file(file_path, output_path, file_index, source_root):
    """
    Read markdown file, convert Obsidian syntax, write to output
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Fix Notion export paths FIRST (before link conversion)
        content = fix_notion_export_paths(content)
        
        # Get relative path from source root for lookup
        relative_file_path = file_path.relative_to(source_root)
        
        # Sanitize the relative path for lookup
        sanitized_relative_path = Path(*[sanitize_filename(part) for part in relative_file_path.parts])
        
        # Convert Obsidian links with file lookup
        content = convert_obsidian_links_with_lookup(
            content,
            sanitized_relative_path,
            file_index
        )
        
        # Fix text issues LAST (so we don't mess with filenames)
        content = fix_text_issues(content)
        
        # Write to output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return True
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False


def create_staging_directory(source_path, staging_path):
    """
    Create staging directory with processed files
    """
    source_path = Path(source_path)
    staging_path = Path(staging_path)
    
    # Remove existing staging
    if staging_path.exists():
        shutil.rmtree(staging_path)
    
    staging_path.mkdir(parents=True)
    
    print(f"Creating staging directory: {staging_path}")
    
    # Build file index first
    print("Building file index...")
    file_index = build_file_index(source_path)
    print(f"Indexed {len(file_index)} unique filenames")
    
    # Walk through source directory
    for item in source_path.rglob('*'):
        if any(part.startswith(('.', '_')) for part in item.relative_to(source_path).parts):
            continue
        if item.is_file():
            relative_path = item.relative_to(source_path)
            
            # Sanitize the output path
            sanitized_relative = Path(*[sanitize_filename(part) for part in relative_path.parts])
            output_path = staging_path / sanitized_relative
            
            # Process markdown files with file index
            if item.suffix == '.md':
                print(f"Processing: {relative_path}")
                process_markdown_file(item, output_path, file_index, source_path)
            
            # Copy other files with sanitized names
            else:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, output_path)
    
    print(f"Staging directory created at {staging_path}")
    return staging_path


if __name__ == "__main__":
    # Quick test
    test_content = """
Here's an image from Notion: ![](Lab%20Notebook%20216be76e722280c380fad6c0fc508250/test.png)
Measured @50 mT with en-dash range 10–20.
An Obsidian image: ![[my image.png]]
An Obsidian path: ![[subfolder/another image.png]]
"""
    print("=== Testing fix_notion_export_paths ===")
    result = fix_notion_export_paths(test_content)
    print(result)
    
    print("\n=== Testing fix_text_issues ===")
    result = fix_text_issues(result)
    print(result)