# QBI Jupyter Books Pipeline

## Overview
This project automates the generation of reproducible [MyST](https://mystmd.org/) Jupyter Books directly from Obsidian research vaults used by the **Quantum Biology Institute (QBI)**.
It transforms live research vaults into browsable, published documentation served from QBI's local infrastructure.

The pipeline builds a full `myst.yml` configuration based on vault structure, preprocesses files for MyST compatibility, and stages everything safely for compilation—ensuring that raw data and notes remain untouched.

## Why This Exists
QBI uses Obsidian for collaborative lab notebooks and local storage for research data.
This pipeline bridges the gap between private research notes and public scientific
publishing, enabling real-time iterative publication without manual reformatting.

## Current Status
The pipeline is **functional and in active development**.

### Preprocessing pipeline
- **Frontmatter injection** — auto-generates page titles from filenames for MyST rendering
- **Image linebreak normalization** — ensures embedded images render as blocks, not inline text
- **Path normalization** — fixes Notion export artifacts and sanitizes filenames (spaces → underscores)
- **Link conversion** — converts Obsidian `![[...]]` embeds to standard Markdown with vault-wide file lookup
- **Text cleanup** — escapes special characters and normalizes dashes for MyST compatibility
- **Image optimization** — resizes images >1200px and compresses for web delivery, with EXIF orientation handling

### Build pipeline
- Generates a valid `myst.yml` automatically from any vault structure
- Safely copies all content to a staging directory before build (source files are never modified)
- Configurable directory exclusions (hidden folders, confidential data, virtual environments)

## Roadmap
Planned enhancements focus on deeper automation, FAIR compliance, and usability for researchers.

### Short term
- Git-based version control with automated commits (no scientist-facing git interaction)
- Vault audit tooling and cleanup checklists for researchers
- LaTeX source sharing for micropublications

### Medium term
- Lightweight OCR for scanned lab notebook images
- Convert `.py` scripts into executable `.ipynb` notebooks for live rendering
- 3D viewer for `.stl` and other scientific model files
- Metadata templates (DOI, timestamps, authorship)
- DeSci Nodes archiving for micropublications

### Long term
- Static site backup/failover for availability when local infrastructure is offline
- AI-assisted metadata suggestion and error detection
- Containerized builds for full reproducibility across systems

## Setup
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .            # add [dev] for the test suite: pip install -e ".[dev]"
npm install -g mystmd
```

This installs a `qbi` command. Editable mode (`-e`) links to the working copy,
so code changes take effect without reinstalling.

## Usage
```bash
# Multi vault (the normal case)
qbi build --config build_config.yml

# Single vault
qbi build ../path/to/vault ../_build_staging

# Preview what would change, writing nothing
qbi build --config build_config.yml --dry-run

# Vault hygiene report
qbi audit ../path/to/vault
qbi audit /mnt/raid-storage/shared --all -d reports/

cd _build_staging && myst start
```

See [build_config.example.yml](./build_config.example.yml) for the config
format, the publication allow-list, and how to keep content off the site.

## How publishing is decided

The site is public, so the pipeline publishes **by permission, not by omission**.

- Only allow-listed file types are staged. Every build prints a per-vault
  **extension census** of what was published and what was skipped, and warns
  when a page links to a file the allow-list left out. Add types via
  `publish_extensions` in the build config.
- Folders named `5_*` are confidential by convention, and a `.qbi-exclude` file
  excludes the folder it sits in plus everything beneath it. Both rules are
  enforced identically in staging, navigation and audit reports.
- Staging is **synced, not rebuilt**: only changed files are written, and files
  removed from a vault are pruned. The staging directory can therefore be kept
  under version control, and `git status` there shows exactly what a build
  changed.

Source vaults are never modified.

## Changelog
See [CHANGELOG.md](./CHANGELOG.md)