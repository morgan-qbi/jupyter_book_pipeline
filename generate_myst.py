import os
from pathlib import Path
import yaml
import uuid

def prettify_folder_name(folder_name):
    """Convert folder_name to Title Case with spaces"""
    name = folder_name.lstrip('0123456789_')
    name = name.replace('_', ' ')
    return name.title()

def scan_bucket_structure(bucket_path):
    """Generate TOC from bucket structure"""
    bucket_path = Path(bucket_path)
    toc = []
    
    # Get all PROJECT folders
    project_folders = sorted([d for d in bucket_path.iterdir() if d.is_dir()])
    
    for project in project_folders:
        project_title = prettify_folder_name(project.name)
        
        project_entry = {
            'title': f"Project: {project_title}",
            'children': []
        }
        
        # Get chapter folders (1_, 2_, 3_, 4_)
        chapter_folders = sorted([d for d in project.iterdir() if d.is_dir() and d.name[0].isdigit()])
        
        for chapter in chapter_folders:
            chapter_names = {
                '1': 'ELN',
                '2': 'Curated Datasets',
                '3': 'Code',
                '4': 'Auxiliary Files'
            }
            chapter_num = chapter.name[0]
            chapter_title = chapter_names.get(chapter_num, prettify_folder_name(chapter.name))
            
            chapter_entry = {
                'title': f"Chapter {chapter_num}: {chapter_title}",
                'children': []
            }
            
            # Get files in this chapter
            files = sorted([f for f in chapter.iterdir() 
                          if f.is_file() and f.suffix in ['.md', '.ipynb']])
            
            for file in files:
                # Use forward slashes for cross-platform compatibility
                file_path = str(file.relative_to(bucket_path)).replace('\\', '/')
                file_entry = {'file': file_path}
                chapter_entry['children'].append(file_entry)
            
            if chapter_entry['children']:
                project_entry['children'].append(chapter_entry)
        
        if project_entry['children']:
            toc.append(project_entry)
    
    return toc

def generate_myst_config(bucket_path, bucket_name, output_path="myst.yml"):
    """Generate complete myst.yml configuration"""
    bucket_path = Path(bucket_path)
    
    project_id = str(uuid.uuid4())
    toc = scan_bucket_structure(bucket_path)
    
    # Check for intro file, or create placeholder
    intro_files = ['README.md', 'index.md', 'intro.md', 
                   f'Intro to {bucket_name}.md']
    homepage = None
    for intro in intro_files:
        intro_path = bucket_path / intro
        if intro_path.exists():
            homepage = {'file': intro.replace('\\', '/'), 'title': 'Home'}
            break
    
    # If no intro exists, use first file found as homepage
    if not homepage and toc:
        # Find first actual file in the structure
        first_project = toc[0]
        if first_project['children']:
            first_chapter = first_project['children'][0]
            if first_chapter['children']:
                first_file = first_chapter['children'][0]['file']
                homepage = {'file': first_file, 'title': 'Home'}
    
    # Build config WITHOUT sphinx section
    config = {
        'version': 1,
        'project': {
            'id': project_id,
            'title': prettify_folder_name(bucket_name),
            'description': f'Research data from {prettify_folder_name(bucket_name)}',
            'open_access': True,
            'license': 'CC-BY-4.0',
            'toc': [homepage] + toc if homepage else toc
        },
        'site': {
            'template': 'book-theme',
            'options': {
                'favicon': '_static/Favicon - institute.png',
                'logo': '_static/Copy of QuBio Institute Primary Light Mode.png',
                'logo_dark': '_static/Copy of QuBio Institute Primary Dark Mode.png',
                'style': '_static/style.css'
            }
        }
    }
    
    # Write to file
    output_file = bucket_path / output_path
    with open(output_file, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    
    print(f"Generated myst.yml at {output_file}")
    return config

if __name__ == "__main__":
    # Test with your example folder
    test_path = "./" # "./research_biology_md_local"
    bucket_name = "research_biology_md"
    
    config = generate_myst_config(test_path, bucket_name)
    
    # Also print to see what it looks like
    print("\nGenerated config:")
    print(yaml.dump(config, default_flow_style=False, sort_keys=False))