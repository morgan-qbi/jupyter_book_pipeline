"""
QBI Jupyter Books Build Pipeline

Orchestrates preprocessing and config generation for one or more Obsidian
research vaults into a single MyST site.

Staging is synced rather than rebuilt: only new and changed files are written,
and files that no longer exist in a vault are pruned. That keeps the staging
directory usable as a git repository, and makes `git status` there show exactly
what a build changed.

Usage:
    # Single vault
    python build_pipeline.py ../research_biology_la ../_build_staging

    # Multi vault
    python build_pipeline.py --config build_config.yml

    # Preview what would change, writing nothing
    python build_pipeline.py --config build_config.yml --dry-run
"""

import sys
import shutil
import argparse
import yaml
from pathlib import Path

from .myst_config import (
    find_homepage,
    generate_multi_vault_config,
    generate_myst_config,
)
from .policy import PUBLISHABLE_EXTENSIONS
from .staging import (
    assert_safe_staging_target,
    claim_staging_directory,
    render_changes,
    sync_vault,
)


def resolve_publishable_extensions(config):
    """
    Merge any `publish_extensions` from the build config into the default
    allow-list.

    Opting a file type in is a config change rather than a code change, so the
    extension census can be acted on directly.
    """
    extra = config.get('publish_extensions') or []
    normalized = {
        ext.lower() if ext.startswith('.') else f'.{ext.lower()}'
        for ext in extra
    }
    if normalized:
        print(f"Additional published extensions from config: {', '.join(sorted(normalized))}")
    return PUBLISHABLE_EXTENSIONS | normalized


def validate_output_path(output, vaults, root=None):
    """
    Refuse an output path that would put staging on top of source data.

    Sync prunes files it considers stale, so pointing `output` at a vault or at
    the shared root -- one typo away in the config -- must be rejected outright
    rather than discovered afterwards (S-4).
    """
    output = Path(output).resolve()

    protected = [Path(v).resolve() for v in vaults]
    if root:
        protected.append(Path(root).resolve())

    for path in protected:
        if output == path:
            raise ValueError(f"Output directory must not be a source path: {output}")
        if path.is_relative_to(output):
            raise ValueError(
                f"Output directory {output} contains source path {path}. "
                f"Staging would prune files inside it."
            )


def load_build_config(config_path):
    """Load and validate build configuration from YAML file"""
    config_path = Path(config_path)
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    if 'output' not in config:
        print("Error: Config must specify 'output' directory")
        sys.exit(1)

    if 'vaults' not in config or not config['vaults']:
        print("Error: Config must specify at least one vault")
        sys.exit(1)

    if 'root' in config:
        root_path = Path(config['root'])
        if not root_path.is_dir():
            print(f"Error: Root path not found: {root_path}")
            sys.exit(1)

    for vault in config['vaults']:
        vault_path = Path(vault['path'])
        if not vault_path.is_dir():
            print(f"Error: Vault path not found: {vault_path}")
            sys.exit(1)

    try:
        validate_output_path(
            config['output'],
            [v['path'] for v in config['vaults']],
            config.get('root'),
        )
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    return config


def build_single_vault(source_path, staging_dir, dry_run=False):
    """Sync a single vault into staging and generate its myst.yml"""
    source_path = Path(source_path)
    staging_path = Path(staging_dir)
    bucket_name = source_path.name.replace('_local', '').replace('_gcs', '')

    print("=" * 50)
    print("Starting single-vault build")
    print(f"Source: {source_path}")
    print(f"Output: {staging_path}")
    if dry_run:
        print("DRY RUN - nothing will be written")
    print("=" * 50)

    assert_safe_staging_target(staging_path)
    if not dry_run:
        claim_staging_directory(staging_path)

    census, changes = sync_vault(source_path, staging_path, dry_run=dry_run)
    print(render_changes(changes))
    print('\n'.join(census.render(source_path.name)))

    if not dry_run:
        print("\nGenerating myst.yml...")
        generate_myst_config(staging_path, bucket_name)

    print("\n" + "=" * 50)
    print("Build complete!")
    print(f"Staging directory: {staging_path}")
    print("\nTo build and preview:")
    print(f"  cd {staging_path}")
    print("  myst start")
    print("=" * 50)

    return staging_path


def build_multi_vault(config, dry_run=False):
    """Sync every configured vault into staging and generate a unified myst.yml"""
    staging_path = Path(config['output'])
    vault_configs = config['vaults']
    allowed = resolve_publishable_extensions(config)

    print("=" * 50)
    print("Starting multi-vault build")
    print(f"Output: {staging_path}")
    print(f"Vaults: {len(vault_configs)}")
    if dry_run:
        print("DRY RUN - nothing will be written")
    print("=" * 50)

    assert_safe_staging_target(staging_path)
    if not dry_run:
        claim_staging_directory(staging_path)

    staged_vaults = []
    censuses = []

    for vault in vault_configs:
        source_path = Path(vault['path'])
        vault_name = source_path.name

        print(f"\n{'─' * 50}")
        print(f"Processing vault: {vault_name}")
        print(f"{'─' * 50}")

        vault_staging = staging_path / vault_name
        census, changes = sync_vault(
            source_path, vault_staging, allowed_extensions=allowed, dry_run=dry_run
        )
        print(render_changes(changes))
        censuses.append((vault_name, census))

        staged_vaults.append({'name': vault_name, 'path': vault_staging})

    # Copy the top-level README from the root directory into staging
    if 'root' in config and not dry_run:
        root_readme = find_homepage(Path(config['root']))
        if root_readme:
            shutil.copy2(root_readme, staging_path / root_readme.name)
            print(f"\nCopied top-level homepage: {root_readme.name}")

    if not dry_run:
        print(f"\n{'─' * 50}")
        print("Generating unified myst.yml...")
        print(f"{'─' * 50}")
        generate_multi_vault_config(staged_vaults, staging_path)

    print(f"\n{'=' * 50}")
    print("Extension census")
    print(f"{'=' * 50}")
    for vault_name, census in censuses:
        print('\n'.join(census.render(vault_name)))

    print("\n" + "=" * 50)
    print("Build complete!")
    print(f"Staging directory: {staging_path}")
    print("\nTo build and preview:")
    print(f"  cd {staging_path}")
    print("  myst start")
    print("=" * 50)

    return staging_path


def run_build(args):
    """`qbi build` — sync vaults into staging and generate myst.yml"""
    if args.config:
        build_multi_vault(load_build_config(args.config), dry_run=args.dry_run)
    elif args.source and args.output:
        validate_output_path(args.output, [args.source])
        build_single_vault(args.source, args.output, dry_run=args.dry_run)
    else:
        raise ValueError("Provide either --config, or both a source and an output path")
    return 0


def run_audit(args):
    """`qbi audit` — report vault hygiene issues"""
    from .audit.report import run_audit_command
    return run_audit_command(args)


def build_parser():
    parser = argparse.ArgumentParser(
        prog='qbi',
        description='Build MyST Jupyter Books from Obsidian research vaults',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subcommands = parser.add_subparsers(dest='command', required=True)

    build = subcommands.add_parser(
        'build',
        help='Sync vaults into the staging directory',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Examples:\n'
               '  qbi build ../research-biology-la ../_build_staging\n'
               '  qbi build --config build_config.yml\n'
               '  qbi build --config build_config.yml --dry-run',
    )
    build.add_argument('source', nargs='?', default=None,
                       help='Source vault path (single vault mode)')
    build.add_argument('output', nargs='?', default=None,
                       help='Output staging directory (single vault mode)')
    build.add_argument('--config', '-c', default=None,
                       help='Path to build config YAML (multi vault mode)')
    build.add_argument('--dry-run', '-n', action='store_true',
                       help='Report what would change without writing anything')
    build.set_defaults(handler=run_build)

    audit = subcommands.add_parser(
        'audit',
        help='Report vault hygiene issues',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Examples:\n'
               '  qbi audit ../research-biology-la\n'
               '  qbi audit /mnt/raid-storage/shared --all -d reports/',
    )
    audit.add_argument('path', help='Path to a vault, or a parent directory of vaults')
    audit.add_argument('--all', action='store_true',
                       help='Treat each subdirectory as a separate vault')
    audit.add_argument('--output', '-o', help='Write a single report to this file')
    audit.add_argument('--output-dir', '-d', help='Write per-vault reports to this directory')
    audit.set_defaults(handler=run_audit)

    return parser


def main(argv=None):
    """
    Entry point. Returns a process exit code.

    Errors exit non-zero so that a failed build is distinguishable from a clean
    one by anything scripting this -- cron, CI, or a wrapper (S-12). Previously
    every failure path printed and returned success.
    """
    # Reports and progress output contain non-ASCII; a cp1252 console would
    # otherwise raise UnicodeEncodeError mid-build.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    args = build_parser().parse_args(argv)

    try:
        return args.handler(args) or 0
    except ValueError as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
