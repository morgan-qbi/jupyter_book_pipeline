# QBI Jupyter Books Pipeline

## Overview
This project automates the generation of reproducible [MyST](https://mystmd.org/) Jupyter Books directly from Google Cloud Storage (GCS) buckets used by the **Quantum Biology Institute (QBI)**.
It transforms live research vaults into browsable, version-controlled documentation that can be pushed to the web daily.

The pipeline builds a full `myst.yml` configuration based on bucket structure, preprocesses files for MyST compatibility, and stages everything safely for compilation—ensuring that raw data and notes remain untouched.

## Why This Exists
   QBI uses Obsidian for collaborative lab notebooks and GCS for data storage. 
   This pipeline bridges the gap between private research notes and public scientific 
   publishing, enabling real-time iterative publication without manual reformatting.

## Current Status
The pipeline is **functional and in active development**.
It currently:
- Generates a valid `myst.yml` automatically from any bucket structure.
- Converts Obsidian-style image embeds (`![[...]]`) to standard Markdown image links.
- Normalizes filenames to avoid MyST build errors (spaces → underscores).
- Safely copies all content to a staging directory before build to prevent accidental data loss.
- Treats non-image files as downloadable links rather than attempting inline rendering.

These features collectively provide a deterministic, repeatable build process for QBI’s scientific documentation.

## Roadmap
Planned enhancements focus on deeper automation, FAIR compliance, and usability for researchers.

### Short term (next 1–2 months)
- Implement nightly changelog generation and automated sync to GCS.
- Add logging for renamed or reclassified files.
- Introduce basic configuration options for vault-specific build rules.

### Medium term
- Integrate lightweight OCR for scanned lab notebook images.
- Convert `.py` scripts into executable `.ipynb` notebooks for live rendering.
- Provide a 3D viewer for `.stl` and other scientific model files.
- Add support for metadata templates (DOI, timestamps, authorship).

### Long term
- Develop CI/CD integration for automatic Jupyter Book builds and publication.
- Implement AI-assisted metadata suggestion and error detection.
- Explore containerized builds for full reproducibility across systems.

## Setup
```bash
pip install pyyaml
npm install -g mystmd
```

## Usage
```bash
cd qbi_pipeline
python build_pipeline.py
cd ../_build_staging
myst start
```

## Changelog
See [CHANGELOG.md](./CHANGELOG.md)
## Current features
- Auto-generates myst.yml from folder structure
- Converts Obsidian image syntax
- Creates staging directory (doesn't modify source files)

## Known issues
- Spaces in image filenames break rendering
- .stl/.ino files treated as images (should be download links)

## Future enhancements
- OCR for lab notebook images
- .py → .ipynb conversion
- 3D STL viewer