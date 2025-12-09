import yaml
import uuid
from pathlib import Path
from utils import prettify_folder_name

# Folders to never include in the TOC
EXCLUDED_FOLDERS = {
    'venv', 'node_modules', '__pycache__', '.git', '.obsidian',
    'site-packages', '.ipynb_checkpoints', 'dist-info', '__pypackages__'
}

# Chapter numbers to skip entirely
SKIP_CHAPTERS = {'5'}  # Confidential


def scan_folder_recursive(folder_path, bucket_path, max_depth=4, current_depth=0):
    """
    Recursively scan a folder for .md and .ipynb files.
    Returns a list of TOC entries (files and nested folders with children).
    """
    if current_depth >= max_depth:
        return []
    
    entries = []
    folder_path = Path(folder_path)
    
    # Get files in this folder
    files = sorted([f for f in folder_path.iterdir() 
                   if f.is_file() and f.suffix in ['.md', '.ipynb']])
    
    for file in files:
        file_path = str(file.relative_to(bucket_path)).replace('\\', '/')
        entries.append({'file': file_path})
    
    # Get subfolders (excluding bad ones)
    subfolders = sorted([d for d in folder_path.iterdir() 
                        if d.is_dir() 
                        and d.name not in EXCLUDED_FOLDERS
                        and not d.name.startswith('.')
                        and not d.name.endswith('.dist-info')])
    
    for subfolder in subfolders:
        children = scan_folder_recursive(subfolder, bucket_path, max_depth, current_depth + 1)
        
        # Only add folder if it has content
        if children:
            folder_entry = {
                'title': prettify_folder_name(subfolder.name),
                'children': children
            }
            entries.append(folder_entry)
    
    return entries


def scan_bucket_structure(bucket_path):
    """Generate TOC from bucket structure"""
    bucket_path = Path(bucket_path)
    toc = []
    
    # Get all PROJECT folders (skip hidden and underscore-prefixed)
    project_folders = sorted([d for d in bucket_path.iterdir() 
                             if d.is_dir() 
                             and not d.name.startswith('_')
                             and not d.name.startswith('.')
                             and d.name not in EXCLUDED_FOLDERS])
    
    for project in project_folders:
        project_title = prettify_folder_name(project.name)
        
        project_entry = {
            'title': f"Project: {project_title}",
            'children': []
        }
        
        # Get chapter folders (1_, 2_, 3_, 4_, etc)
        chapter_folders = sorted([d for d in project.iterdir() 
                                 if d.is_dir() and d.name[0].isdigit()])
        
        for chapter in chapter_folders:
            chapter_num = chapter.name[0]
            
            # Skip confidential and other excluded chapters
            if chapter_num in SKIP_CHAPTERS:
                continue
            
            chapter_names = {
                '1': 'ELN',
                '2': 'Curated Datasets',
                '3': 'Code',
                '4': 'Auxiliary Files'
            }
            chapter_title = chapter_names.get(chapter_num, prettify_folder_name(chapter.name))
            
            # Recursively scan the chapter folder
            children = scan_folder_recursive(chapter, bucket_path, max_depth=4, current_depth=0)
            
            if children:
                chapter_entry = {
                    'title': f"Chapter {chapter_num}: {chapter_title}",
                    'children': children
                }
                project_entry['children'].append(chapter_entry)
        
        if project_entry['children']:
            toc.append(project_entry)
    
    return toc


def find_or_create_homepage(bucket_path, bucket_name):
    """
    Find an existing homepage or create a placeholder.
    
    Search order:
    1. README.md / index.md / intro.md in bucket root
    2. README.md in any project folder
    3. Generate a placeholder index.md
    
    Returns: (file_path_relative_to_bucket, was_generated)
    """
    bucket_path = Path(bucket_path)
    
    # 1. Check bucket root for standard intro files
    root_intro_files = ['README.md', 'index.md', 'intro.md']
    for intro in root_intro_files:
        intro_path = bucket_path / intro
        if intro_path.exists():
            return (intro, False)
    
    # 2. Check each project folder for a README
    project_folders = sorted([d for d in bucket_path.iterdir() 
                             if d.is_dir() 
                             and not d.name.startswith('_')
                             and not d.name.startswith('.')
                             and d.name not in EXCLUDED_FOLDERS])
    
    for project in project_folders:
        project_readme = project / 'README.md'
        if project_readme.exists():
            return (str(project_readme.relative_to(bucket_path)).replace('\\', '/'), False)
    
    # 3. Generate a placeholder
    pretty_name = prettify_folder_name(bucket_name)
    placeholder_content = f"""# {pretty_name}

Research data and documentation from {pretty_name}.
"""
    
    placeholder_path = bucket_path / 'index.md'
    with open(placeholder_path, 'w', encoding='utf-8') as f:
        f.write(placeholder_content)
    
    print(f"Generated placeholder homepage: {placeholder_path}")
    return ('index.md', True)


def generate_myst_config(bucket_path, bucket_name, output_path="myst.yml"):
    """Generate complete myst.yml configuration"""
    bucket_path = Path(bucket_path)
    
    project_id = str(uuid.uuid4())
    toc = scan_bucket_structure(bucket_path)
    
    # Find or create homepage
    homepage_file, was_generated = find_or_create_homepage(bucket_path, bucket_name)
    homepage = {'file': homepage_file, 'title': 'Home'}
    
    config = {
        'version': 1,
        'project': {
            'id': project_id,
            'title': prettify_folder_name(bucket_name),
            'description': f'Research data from {prettify_folder_name(bucket_name)}',
            'open_access': True,
            'license': 'CC-BY-4.0',
            'toc': [homepage] + toc
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