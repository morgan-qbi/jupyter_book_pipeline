import re
import shutil
from pathlib import Path

def convert_obsidian_images(text):
    """
    Convert Obsidian-style image links ( ![[image]] ) to standard Markdown image links ![](attachments/image)
    """
    pattern = r'!\[\[(.*?)\]\]'
    return re.sub(pattern, r'![](attachments/\1)', text)

def process_markdown_file(file_path, output_path):
    """
    Read markdown file, convert Obsidian syntax, write to output
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Convert image syntax
        converted_content = convert_obsidian_images(content)
        
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
    
    Returns: Path to staging directory
    """
    source_path = Path(source_path)
    staging_path = Path(staging_path)
    
    # Remove existing staging if it exists
    if staging_path.exists():
        shutil.rmtree(staging_path)
    
    staging_path.mkdir(parents=True)
    
    print(f"Creating staging directory: {staging_path}")
    
    # Walk through source directory
    for item in source_path.rglob('*'):
        if item.is_file():
            # Get relative path from source
            relative_path = item.relative_to(source_path)
            output_path = staging_path / relative_path
            
            # Process markdown files
            if item.suffix == '.md':
                print(f"Processing: {relative_path}")
                process_markdown_file(item, output_path)
            
            # Copy other files as-is
            else:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, output_path)
    
    print(f"Staging directory created at {staging_path}")
    return staging_path