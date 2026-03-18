"""
QBI MyST Config Generator

Generates myst.yml configuration files from Obsidian vault structure.
Supports both single-vault and multi-vault configurations.

Single vault:
    generate_myst_config(vault_path, vault_name)

Multi vault:
    generate_multi_vault_config(staged_vaults, staging_path)

Structure assumptions:
    vault/
    ├── project_a/
    │   ├── 1_eln_project_a/
    │   │   ├── notebook1.md
    │   │   └── subfolder/
    │   │       └── nested_notebook.md
    │   ├── 2_curated_datasets_project_a/
    │   ├── 3_code_project_a/
    │   └── 4_auxiliary_files_project_a/
    └── project_b/
        └── ...

Chapter folders are identified by a leading digit (1_, 2_, 3_, 4_).
Chapter 5 is excluded by default (confidential).
"""

import os
from pathlib import Path
import yaml
import uuid


# =============================================================================
# CONFIGURATION
# =============================================================================

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

# How deep to recurse into chapter subdirectories
MAX_SCAN_DEPTH = 4


# =============================================================================
# HELPERS
# =============================================================================

def prettify_folder_name(folder_name):
    """Convert folder_name to Title Case with spaces.

    Strips leading digits and underscores, replaces remaining underscores
    and hyphens with spaces, then title-cases the result. If the folder name
    is only digits/underscores (e.g. '2025'), returns it unchanged.
    """
    name = folder_name.lstrip('0123456789_')
    if not name:
        return folder_name
    name = name.replace('_', ' ').replace('-', ' ')
    return name.title()


def get_display_name(folder_name):
    """Get display name for a folder, checking DISPLAY_NAMES overrides first."""
    return DISPLAY_NAMES.get(folder_name, prettify_folder_name(folder_name))


def should_skip_dir(dir_name):
    """Check if a directory should be skipped.

    Skips directories that:
    - Are in the EXCLUDED_DIRS set (venv, node_modules, etc.)
    - Start with any prefix in EXCLUDED_PREFIXES (., _, 5_)
    """
    if dir_name in EXCLUDED_DIRS:
        return True
    if any(dir_name.startswith(p) for p in EXCLUDED_PREFIXES):
        return True
    return False


def find_homepage(search_path):
    """Look for an intro/readme file to use as homepage.

    Checks for README.md, index.md, and intro.md in the given directory.
    Returns the Path if found, None otherwise.
    """
    candidates = ['README.md', 'index.md', 'intro.md']
    for name in candidates:
        intro_path = search_path / name
        if intro_path.exists():
            return intro_path
    return None


def find_or_create_homepage(bucket_path, bucket_name):
    """Find an existing homepage or create a placeholder.

    Search order:
    1. README.md / index.md / intro.md in bucket root
    2. README.md in any project folder
    3. Generate a placeholder index.md

    Returns:
        tuple: (file_path_relative_to_bucket, was_generated)
    """
    bucket_path = Path(bucket_path)

    # 1. Check bucket root for standard intro files
    homepage = find_homepage(bucket_path)
    if homepage:
        return (str(homepage.relative_to(bucket_path)).replace('\\', '/'), False)

    # 2. Check each project folder for a README
    project_folders = sorted([
        d for d in bucket_path.iterdir()
        if d.is_dir() and not should_skip_dir(d.name)
    ])

    for project in project_folders:
        project_readme = project / 'README.md'
        if project_readme.exists():
            return (str(project_readme.relative_to(bucket_path)).replace('\\', '/'), False)

    # 3. Generate a placeholder
    pretty_name = get_display_name(bucket_name)
    placeholder_content = f"""# {pretty_name}

Research data and documentation from {pretty_name}.
"""

    placeholder_path = bucket_path / 'index.md'
    with open(placeholder_path, 'w', encoding='utf-8') as f:
        f.write(placeholder_content)

    print(f"Generated placeholder homepage: {placeholder_path}")
    return ('index.md', True)


# =============================================================================
# TOC SCANNING
# =============================================================================

def scan_chapter_contents(chapter_path, base_path, max_depth=MAX_SCAN_DEPTH, current_depth=0):
    """Scan a chapter folder for publishable files.

    Recursively walks the chapter directory up to max_depth levels,
    collecting .md and .ipynb files into a TOC-compatible list.
    README/index/intro files at each level become 'Overview' entries.

    Args:
        chapter_path: Path to the chapter directory
        base_path: Root path for computing relative file paths
        max_depth: Maximum recursion depth (default: MAX_SCAN_DEPTH)
        current_depth: Current recursion depth (internal use)

    Returns:
        list: TOC entries (dicts with 'file' and optionally 'title'/'children')
    """
    if current_depth >= max_depth:
        return []

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

    # Scan subdirectories recursively
    subdirs = sorted([
        d for d in chapter_path.iterdir()
        if d.is_dir() and not should_skip_dir(d.name)
    ])

    for subdir in subdirs:
        sub_children = scan_chapter_contents(subdir, base_path, max_depth, current_depth + 1)

        if sub_children:
            sub_entry = {
                'title': prettify_folder_name(subdir.name),
                'children': sub_children
            }
            children.append(sub_entry)

    return children


def scan_project_structure(project_path, base_path):
    """Generate TOC entries for a single project.

    Scans a project directory for numbered chapter folders (1_, 2_, 3_, 4_)
    and generates a hierarchical TOC. Checks for a project-level README
    to use as an overview page.

    Args:
        project_path: Path to the project directory
        base_path: Root path for computing relative file paths

    Returns:
        dict: TOC entry with 'title' and 'children' keys
    """
    project_title = get_display_name(project_path.name)

    project_entry = {
        'title': f"Project: {project_title}",
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
    """Generate TOC entries for a vault containing multiple projects.

    Scans a vault directory for project folders, skipping excluded directories.
    Checks for a vault-level README to use as an overview page.

    Args:
        vault_path: Path to the vault directory
        base_path: Root path for computing relative file paths

    Returns:
        dict: TOC entry with 'title' and 'children' keys
    """
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


# =============================================================================
# CONFIG GENERATION
# =============================================================================

def build_site_config(toc, site_title="QBI Research"):
    """Build the full myst.yml config dict.

    Args:
        toc: List of TOC entries
        site_title: Title for the site (default: 'QBI Research')

    Returns:
        dict: Complete myst.yml configuration
    """
    return {
        'version': 1,
        'project': {
            'id': str(uuid.uuid4()),
            'title': site_title,
            'description': f'Research documentation from {site_title}',
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
    """Generate a unified myst.yml for multiple vaults.

    Creates a single myst.yml at the staging root that references all vaults.
    Generates an index.md landing page if one doesn't exist.

    Args:
        staged_vaults: list of dicts with 'name' and 'path' keys
        staging_path: root staging directory where myst.yml will be written

    Returns:
        dict: The generated configuration
    """
    staging_path = Path(staging_path)
    toc = []

    # Check for a root-level homepage, or create one
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
    """Generate myst.yml for a single vault.

    Kept for backwards compatibility with single-vault workflows.
    Scans the vault for projects, finds or creates a homepage,
    and writes a complete myst.yml.

    Args:
        bucket_path: Path to the vault directory
        bucket_name: Name of the vault (used for title/display)
        output_path: Filename for the config (default: 'myst.yml')

    Returns:
        dict: The generated configuration
    """
    bucket_path = Path(bucket_path)
    toc = []

    # Find or create homepage (generates placeholder if needed)
    homepage_file, was_generated = find_or_create_homepage(bucket_path, bucket_name)
    toc.append({'file': homepage_file, 'title': 'Home'})

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