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
    qbi build ../path/to/vault ../_build_staging

    # Multi vault
    qbi build --config build_config.yml

    # Preview what would change, writing nothing
    qbi build --config build_config.yml --dry-run
"""

import argparse
import shutil
import sys
from pathlib import Path

import yaml

from .myst_config import (
    find_homepage,
    generate_multi_vault_config,
    generate_myst_config,
)
from .naming import configure_display_names, get_display_name
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


def resolve_display_names(config):
    """
    Merge the per-vault `name:` keys into the config's `display_names` table.

    A vault's display name is asked for where the vault is declared, not in a
    separate block further down the file, so a `vaults:` entry may carry a
    `name:` of its own. Both routes feed the same table, keyed by the folder
    name on disk, so every layer that titles that folder -- site title,
    navigation, generated index -- still reads one source of truth.

    `name:` is the more specific of the two, so it wins a disagreement, and
    says so rather than resolving it silently.
    """
    configured = config.get('display_names') or {}
    if not isinstance(configured, dict):
        raise ValueError("`display_names` must be a mapping of folder name to display name")

    display_names = dict(configured)

    for vault in config['vaults']:
        name = vault.get('name')
        if name is None:
            continue
        if not isinstance(name, str):
            raise ValueError(f"`name` for vault {vault['path']!r} must be a string")

        folder = Path(vault['path']).name
        shadowed = display_names.get(folder)
        if shadowed is not None and shadowed != name:
            print(
                f"Note: vault {folder} is named {name!r} in `vaults:`, "
                f"which overrides {shadowed!r} in `display_names:`"
            )
        display_names[folder] = name

    return display_names


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

    with open(config_path, encoding='utf-8') as f:
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

    try:
        configure_display_names(resolve_display_names(config))
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    return config


def build_single_vault(source_path, staging_dir, dry_run=False, display_name=None):
    """
    Sync a single vault into staging and generate its myst.yml.

    `display_name` is this mode's answer to `display_names:`, which it has no
    config to read. It goes into the same override table, so a name given here
    titles the site exactly as written -- `Research: Team One` rather than
    whatever prettifying the folder name happens to produce.
    """
    source_path = Path(source_path)
    staging_path = Path(staging_dir)
    bucket_name = source_path.name.replace('_local', '').replace('_gcs', '')

    if display_name is not None:
        configure_display_names({bucket_name: display_name})

    print("=" * 50)
    print("Starting single-vault build")
    print(f"Source: {source_path}")
    print(f"Output: {staging_path}")
    print(f"Title:  {get_display_name(bucket_name)}")
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
        # The title, here, because config generation is skipped on a dry run --
        # which is exactly when someone is checking whether a newly added vault
        # is named the way they meant.
        print(f"Title: {get_display_name(vault_name)}")
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
        if args.name:
            raise ValueError(
                "--name applies to single-vault mode. With a config, name the vault "
                "there: a `name:` on its `vaults:` entry, or a `display_names:` key"
            )
        build_multi_vault(load_build_config(args.config), dry_run=args.dry_run)
    elif args.source and args.output:
        validate_output_path(args.output, [args.source])
        build_single_vault(
            args.source, args.output, dry_run=args.dry_run, display_name=args.name
        )
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
               '  qbi build ../research-team-one ../_build_staging\n'
               '  qbi build ../research-team-one ../_build_staging '
               '--name "Research: Team One"\n'
               '  qbi build --config build_config.yml\n'
               '  qbi build --config build_config.yml --dry-run',
    )
    build.add_argument('source', nargs='?', default=None,
                       help='Source vault path (single vault mode)')
    build.add_argument('output', nargs='?', default=None,
                       help='Output staging directory (single vault mode)')
    build.add_argument('--config', '-c', default=None,
                       help='Path to build config YAML (multi vault mode)')
    build.add_argument('--name', default=None,
                       help='Exact display title for the vault (single vault mode); '
                            'with --config, name vaults in the config instead')
    build.add_argument('--dry-run', '-n', action='store_true',
                       help='Report what would change without writing anything')
    build.set_defaults(handler=run_build)

    audit = subcommands.add_parser(
        'audit',
        help='Report vault hygiene issues',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Examples:\n'
               '  qbi audit ../research-team-one\n'
               '  qbi audit /srv/qbi --all -d reports/',
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
