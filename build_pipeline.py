"""
QBI Jupyter Books Build Pipeline

Orchestrates preprocessing and config generation for one or more Obsidian
research vaults into a single MyST site.

Usage:
    # Single vault (CLI mode, backwards compatible)
    python build_pipeline.py ../research_biology_la ../_build_staging

    # Multi vault (config file mode)
    python build_pipeline.py --config qbi_build.yml
"""

import sys
import argparse
import yaml
from pathlib import Path
from preprocessing import create_staging_directory
from config_generator import generate_myst_config, generate_multi_vault_config


def load_build_config(config_path):
    """Load and validate build configuration from YAML file"""
    config_path = Path(config_path)
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Validate required fields
    if 'output' not in config:
        print("Error: Config must specify 'output' directory")
        sys.exit(1)

    if 'vaults' not in config or not config['vaults']:
        print("Error: Config must specify at least one vault")
        sys.exit(1)

    # Validate vault paths exist
    for vault in config['vaults']:
        vault_path = Path(vault['path'])
        if not vault_path.is_dir():
            print(f"Error: Vault path not found: {vault_path}")
            sys.exit(1)

    return config


def build_single_vault(source_path, staging_dir):
    """
    Single vault pipeline (backwards compatible).
    Stage files, convert syntax, generate config, ready to build.
    """
    source_path = Path(source_path)
    staging_path = Path(staging_dir)
    bucket_name = source_path.name.replace('_local', '').replace('_gcs', '')

    print("=" * 50)
    print("Starting single-vault build preparation")
    print(f"Source: {source_path}")
    print(f"Output: {staging_path}")
    print("=" * 50)

    # Create staging directory with processed files
    staging_path = create_staging_directory(source_path, staging_path)

    # Generate myst.yml in staging directory
    print("\nGenerating myst.yml...")
    generate_myst_config(staging_path, bucket_name)

    print("\n" + "=" * 50)
    print("Build preparation complete!")
    print(f"Staging directory: {staging_path}")
    print("\nTo build and preview:")
    print(f"  cd {staging_path}")
    print("  myst start")
    print("=" * 50)

    return staging_path


def build_multi_vault(config):
    """
    Multi vault pipeline.
    Preprocess each vault into nested staging directories,
    then generate unified myst.yml.
    """
    staging_path = Path(config['output'])
    vault_configs = config['vaults']

    print("=" * 50)
    print("Starting multi-vault build preparation")
    print(f"Output: {staging_path}")
    print(f"Vaults: {len(vault_configs)}")
    print("=" * 50)

    # Track staged vault paths for config generation
    staged_vaults = []

    for vault in vault_configs:
        source_path = Path(vault['path'])
        vault_name = source_path.name

        print(f"\n{'─' * 50}")
        print(f"Processing vault: {vault_name}")
        print(f"{'─' * 50}")

        # Each vault gets its own subdirectory in staging
        vault_staging = staging_path / vault_name
        create_staging_directory(source_path, vault_staging)

        staged_vaults.append({
            'name': vault_name,
            'path': vault_staging,
        })

    # Generate unified myst.yml at staging root
    print(f"\n{'─' * 50}")
    print("Generating unified myst.yml...")
    print(f"{'─' * 50}")
    generate_multi_vault_config(staged_vaults, staging_path)

    print("\n" + "=" * 50)
    print("Build preparation complete!")
    print(f"Staging directory: {staging_path}")
    print("\nTo build and preview:")
    print(f"  cd {staging_path}")
    print("  myst start")
    print("=" * 50)

    return staging_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Preprocess Obsidian vaults for MyST',
        epilog='Examples:\n'
               '  python build_pipeline.py ../research_biology_la ../_build_staging\n'
               '  python build_pipeline.py --config qbi_build.yml',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('source', nargs='?', default=None,
                        help='Source vault path (single vault mode)')
    parser.add_argument('output', nargs='?', default=None,
                        help='Output staging directory (single vault mode)')
    parser.add_argument('--config', '-c', type=str, default=None,
                        help='Path to build config YAML (multi vault mode)')

    args = parser.parse_args()

    if args.config:
        # Multi vault mode
        config = load_build_config(args.config)
        build_multi_vault(config)
    elif args.source and args.output:
        # Single vault mode (backwards compatible)
        build_single_vault(args.source, args.output)
    else:
        parser.print_help()
        print("\nError: Provide either --config or both source and output paths")
        sys.exit(1)