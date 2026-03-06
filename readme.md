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
- Vault audit tooling and cleanup checklists for researchers (done)
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
pip install pyyaml pillow
npm install -g mystmd
```

## Usage
```bash
cd qbi_pipeline

# Single vault
python build_pipeline.py /path/to/vault [/path/to/staging/dir]

# Multi-vault (generated unified site)
python build_pipeline.py --config build_config.yml

cd /path/to/staging/dir
myst start
```

## Changelog
See [CHANGELOG.md](./CHANGELOG.md)