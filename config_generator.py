"""
QBI MyST Config Generator

Generates myst.yml configuration files from Obsidian vault structure.
Supports both single-vault and multi-vault configurations.

Single vault:
    generate_myst_config(vault_path, vault_name)

Multi vault:
    generate_multi_vault_config(staged_vaults, staging_path)
"""

import os
from pathlib import Path
import yaml
import uuid


EXCLUDED_PREFIXES = ('.', '_', '5_')

EXCLUDED_DIRS = {
    'venv', 'node_modules', '__pycache__', 'site-packages', '.git', '.obsidian',
    '.ipynb_checkpoints', 'dist-info', '__pypackages__', '.trash',
    'attachments', 'Discourse Canvas'
}

CHAPTER_NAMES = {
    '1': 'ELN',
    '2': 'Curated Datasets',
    '3': 'Code',
    '4': 'Auxiliary Files'
}

# Display name overrides for vault/project folder names.
# Keys are the folder names on disk, values are exact display names.
# Anything not in this dict falls through to prettify_folder_name().
DISPLAY_NAMES = {
    'ecoli_flavoprotein_expression': 'E. coli Flavoprotein Expression',
    'research-biology-la': 'Research Biology LA',
    'research-biology-md': 'Research Biology MD',
    'research-bio-redox': 'Research Bio Redox',
    'bacterioscope': 'Bacterioscope',
}


def prettify_folder_name(folder_name):
    """Convert folder_name to Title Case with spaces"""
    name = folder_name.lstrip('0123456789_')
    if not name:
        # Folder name is only digits/underscores (e.g., "2025"), keep as-is
        return folder_name
    name = name.replace('_', ' ').replace('-', ' ')
    return name.title()


def get_display_name(folder_name):
    """Get display name for a folder, checking overrides first."""
    return DISPLAY_NAMES.get(folder_name, prettify_folder_name(folder_name))


def should_skip_dir(dir_name):
    """Check if a directory should be skipped"""
    if dir_name in EXCLUDED_DIRS:
        return True
    if any(dir_name.startswith(p) for p in EXCLUDED_PREFIXES):
        return True
    return False


def find_homepage(search_path):
    """Look for an intro/readme file to use as homepage"""
    candidates = ['README.md', 'index.md', 'intro.md']
    for name in candidates:
        intro_path = search_path / name
        if intro_path.exists():
            return intro_path
    return None


def scan_chapter_contents(chapter_path, base_path):
    """Scan a chapter folder for publishable files"""
    children = []

    # Check for chapter-level README first
    readme = find_homepage(chapter_path)
    if readme:
        file_path = str(readme.relative_to(base_path)).replace('\\', '/')
        children.append({'file': file_path, 'title': 'Overview'})

    # Get publishable files (excluding README which is already added)
    files = sorted([
        f for f in chapter_path.iterdir()
        if f.is_file()
        and f.suffix in ['.md', '.ipynb']
        and f.name not in ['README.md', 'index.md', 'intro.md']
    ])

    for file in files:
        file_path = str(file.relative_to(base_path)).replace('\\', '/')
        children.append({'file': file_path})

    # Scan subdirectories (one level deep) for additional files
    subdirs = sorted([
        d for d in chapter_path.iterdir()
        if d.is_dir() and not should_skip_dir(d.name)
    ])

    for subdir in subdirs:
        sub_files = sorted([
            f for f in subdir.iterdir()
            if f.is_file() and f.suffix in ['.md', '.ipynb']
        ])
        if sub_files:
            sub_entry = {
                'title': prettify_folder_name(subdir.name),
                'children': []
            }
            # Check for subdir README
            sub_readme = find_homepage(subdir)
            if sub_readme:
                sub_path = str(sub_readme.relative_to(base_path)).replace('\\', '/')
                sub_entry['children'].append({'file': sub_path, 'title': 'Overview'})

            for file in sub_files:
                if file.name in ['README.md', 'index.md', 'intro.md']:
                    continue
                file_path = str(file.relative_to(base_path)).replace('\\', '/')
                sub_entry['children'].append({'file': file_path})

            if sub_entry['children']:
                children.append(sub_entry)

    return children


def scan_project_structure(project_path, base_path):
    """Generate TOC entries for a single project"""
    project_title = get_display_name(project_path.name)

    project_entry = {
        'title': project_title,
        'children': []
    }

    # Check for project-level README
    readme = find_homepage(project_path)
    if readme:
        file_path = str(readme.relative_to(base_path)).replace('\\', '/')
        project_entry['children'].append({'file': file_path, 'title': 'Overview'})

    # Get chapter folders (1_, 2_, 3_, 4_)
    chapter_folders = sorted([
        d for d in project_path.iterdir()
        if d.is_dir() and d.name[0:1].isdigit()
    ])

    for chapter in chapter_folders:
        chapter_num = chapter.name[0]
        chapter_title = CHAPTER_NAMES.get(chapter_num, prettify_folder_name(chapter.name))

        children = scan_chapter_contents(chapter, base_path)

        if children:
            chapter_entry = {
                'title': f"Chapter {chapter_num}: {chapter_title}",
                'children': children
            }
            project_entry['children'].append(chapter_entry)

    return project_entry


def scan_vault_structure(vault_path, base_path):
    """Generate TOC entries for a vault (contains multiple projects)"""
    vault_path = Path(vault_path)
    vault_title = get_display_name(vault_path.name)

    vault_entry = {
        'title': vault_title,
        'children': []
    }

    # Check for vault-level README
    readme = find_homepage(vault_path)
    if readme:
        file_path = str(readme.relative_to(base_path)).replace('\\', '/')
        vault_entry['children'].append({'file': file_path, 'title': 'Overview'})

    # Get project folders (skip excluded dirs)
    project_folders = sorted([
        d for d in vault_path.iterdir()
        if d.is_dir() and not should_skip_dir(d.name)
    ])

    for project in project_folders:
        project_entry = scan_project_structure(project, base_path)
        if project_entry['children']:
            vault_entry['children'].append(project_entry)

    return vault_entry


def build_site_config(toc, site_title="QBI Research"):
    """Build the full myst.yml config dict"""
    return {
        'version': 1,
        'project': {
            'id': str(uuid.uuid4()),
            'title': site_title,
            'description': 'Research documentation from the Quantum Biology Institute',
            'open_access': True,
            'license': 'CC-BY-4.0',
            'toc': toc
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


def generate_multi_vault_config(staged_vaults, staging_path):
    """
    Generate a unified myst.yml for multiple vaults.

    Args:
        staged_vaults: list of dicts with 'name' and 'path' keys
        staging_path: root staging directory where myst.yml will be written
    """
    staging_path = Path(staging_path)
    toc = []

    # Check for a root-level homepage
    homepage = find_homepage(staging_path)
    if homepage:
        file_path = str(homepage.relative_to(staging_path)).replace('\\', '/')
        toc.append({'file': file_path, 'title': 'Home'})
    else:
        # Generate a simple index page
        index_path = staging_path / 'index.md'
        vault_names = [get_display_name(v['name']) for v in staged_vaults]
        index_content = '---\ntitle: QBI Research\n---\n\n'
        index_content += '# QBI Research Documentation\n\n'
        index_content += 'Research vaults:\n\n'
        for name in vault_names:
            index_content += f'- {name}\n'
        index_path.write_text(index_content, encoding='utf-8')
        toc.append({'file': 'index.md', 'title': 'Home'})

    for vault in staged_vaults:
        vault_path = Path(vault['path'])
        vault_entry = scan_vault_structure(vault_path, staging_path)
        if vault_entry['children']:
            toc.append(vault_entry)

    config = build_site_config(toc)

    output_file = staging_path / 'myst.yml'
    with open(output_file, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    print(f"Generated myst.yml at {output_file}")
    return config


def generate_myst_config(bucket_path, bucket_name, output_path="myst.yml"):
    """
    Generate myst.yml for a single vault. Kept for backwards compatibility.
    """
    bucket_path = Path(bucket_path)
    toc = []

    # Check for vault-level homepage
    readme = find_homepage(bucket_path)
    if readme:
        file_path = str(readme.relative_to(bucket_path)).replace('\\', '/')
        toc.append({'file': file_path, 'title': 'Home'})

    # Scan projects
    project_folders = sorted([
        d for d in bucket_path.iterdir()
        if d.is_dir() and not should_skip_dir(d.name)
    ])

    for project in project_folders:
        project_entry = scan_project_structure(project, bucket_path)
        if project_entry['children']:
            toc.append(project_entry)

    config = build_site_config(toc, get_display_name(bucket_name))

    output_file = bucket_path / output_path
    with open(output_file, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    print(f"Generated myst.yml at {output_file}")
    return config


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        test_path = sys.argv[1]
    else:
        test_path = "./"

    bucket_name = Path(test_path).name
    config = generate_myst_config(test_path, bucket_name)

    print("\nGenerated config:")
    print(yaml.dump(config, default_flow_style=False, sort_keys=False))