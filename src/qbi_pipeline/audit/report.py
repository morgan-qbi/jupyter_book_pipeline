"""
Vault audit reports: run the checks and render them as markdown.
"""

from datetime import datetime
from pathlib import Path

from ..policy import EXCLUDED_DIRS, IMAGE_EXTENSIONS
from .checks import (
    check_broken_anchors,
    check_broken_references,
    check_empty_files,
    check_generic_filenames,
    check_image_linebreaks,
    check_invalid_notebooks,
    check_notion_imports,
    check_pasted_images,
    get_all_files,
)

# =============================================================================
# REPORT GENERATION
# =============================================================================

def generate_report(vault_path, vault_name=None):
    """Run all audits and generate a report"""
    vault_path = Path(vault_path)
    if not vault_name:
        vault_name = vault_path.name

    print(f"Scanning vault: {vault_name}...")
    files = get_all_files(vault_path)

    md_count = len([f for f in files if f.suffix == '.md'])
    img_count = len([f for f in files if f.suffix.lower() in IMAGE_EXTENSIONS])

    report = []
    report.append(f"# Vault Audit: {vault_name}")
    report.append(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")
    report.append(f"**Stats:** {len(files)} files ({md_count} markdown, {img_count} images)\n")
    report.append("---\n")

    # Run all checks
    checks = [
        ("Broken References", check_broken_references(files, vault_path)),
        ("Links to Missing Headings", check_broken_anchors(files, vault_path)),
        ("Pasted/Screenshot Images to Rename", check_pasted_images(files, vault_path)),
        ("Generic Filenames", check_generic_filenames(files, vault_path)),
        ("Empty Files", check_empty_files(files, vault_path)),
        ("Notebooks That Cannot Be Published", check_invalid_notebooks(files, vault_path)),
        ("Inline Images (need linebreaks)", check_image_linebreaks(files, vault_path)),
        ("Notion Import Artifacts", check_notion_imports(files, vault_path)),
    ]

    total_issues = 0

    for check_name, issues in checks:
        if issues:
            total_issues += len(issues)
            report.append(f"## {check_name} ({len(issues)})\n")
            for issue in issues:
                if 'file' in issue:
                    report.append(f"- [ ] `{issue['file']}`")
                elif 'source_file' in issue:
                    report.append(f"- [ ] In `{issue['source_file']}`: reference to `{issue['reference']}`")

                if 'count' in issue:
                    report.append(f"  - {issue['count']} instance(s)")
                if 'suggestion' in issue:
                    report.append(f"  - *{issue['suggestion']}*")
                report.append("")
        else:
            report.append(f"## {check_name}\n")
            report.append("✅ No issues found.\n")

    report.append("---\n")
    report.append(f"**Total issues found: {total_issues}**\n")

    if total_issues == 0:
        report.append("🎉 Vault is clean! Nice work.\n")
    elif total_issues < 10:
        report.append("Not bad! A little cleanup and you're good.\n")
    elif total_issues < 30:
        report.append("Some housekeeping needed. Set aside an hour and knock these out.\n")
    else:
        report.append("This vault needs some love. Start with the broken references and work your way down.\n")

    return '\n'.join(report)


# =============================================================================
# MAIN
# =============================================================================

def run_audit_command(args):
    """
    Run the audit for `qbi audit`. Returns a process exit code.

    Audit reports name files and link targets, so they are written only for
    content that passed the publication policy -- confidential and
    .qbi-exclude subtrees never reach a report.
    """
    vault_path = Path(args.path)

    if not vault_path.is_dir():
        raise ValueError(f"Not a directory: {vault_path}")

    if args.all:
        output_dir = Path(args.output_dir) if args.output_dir else Path('audit_reports')
        output_dir.mkdir(parents=True, exist_ok=True)

        vaults = sorted([d for d in vault_path.iterdir()
                        if d.is_dir()
                        and not d.name.startswith('.')
                        and not d.name.startswith('_')
                        and d.name not in EXCLUDED_DIRS])

        for vault in vaults:
            report = generate_report(vault)
            output_file = output_dir / f"audit_{vault.name}.md"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"  Report saved: {output_file}")

        print(f"\nAll reports saved to {output_dir}/")

    else:
        report = generate_report(vault_path)

        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"Report saved: {args.output}")
        else:
            print(report)

    return 0
