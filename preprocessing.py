import re
import shutil
from pathlib import Path
import urllib.parse
import os

def sanitize_filename(filename):
    """Replace spaces with underscores in filename"""
    return filename.replace(' ', '_')

def build_file_index(source_path):
    """
    Build an index of all files in the project
    Returns: dict mapping filename -> relative path from source_path
    """
    source_path = Path(source_path)
    file_index = {}
    
    for item in source_path.rglob('*'):
        if item.is_file():
            relative_path = item.relative_to(source_path)
            
            # Sanitize the path
            sanitized_path = Path(*[sanitize_filename(part) for part in relative_path.parts])
            
            filename = item.name
            sanitized_filename = sanitize_filename(filename)
            
            # Index both original and sanitized names
            for name in [filename, sanitized_filename]:
                if name in file_index:
                    if not isinstance(file_index[name], list):
                        file_index[name] = [file_index[name]]
                    file_index[name].append(str(sanitized_path))
                else:
                    file_index[name] = str(sanitized_path)
    
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
    Convert Obsidian links using file index for lookup
    """
    pattern = r'!\[\[(.*?)\]\]'
    
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp'}
    
    def replacement(match):
        filename = match.group(1)
        
        # Look up file in index
        if filename not in file_index:
            return f'![[{filename}]]'
        
        file_path = file_index[filename]
        
        if isinstance(file_path, list):
            file_path = file_path[0]
            print(f"Warning: Multiple files named '{filename}', using {file_path}")
        
        # Calculate relative path
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
        
        # Get relative path from source root for lookup
        relative_file_path = file_path.relative_to(source_root)
        
        # Sanitize the relative path for lookup
        sanitized_relative_path = Path(*[sanitize_filename(part) for part in relative_file_path.parts])
        
        # Convert with file lookup
        converted_content = convert_obsidian_links_with_lookup(
            content, 
            sanitized_relative_path, 
            file_index
        )
        
        # Write to output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(converted_content)
        
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