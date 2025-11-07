# QBI Jupyter Books Pipeline

## What this does
Automates building Jupyter Books from GCS bucket structure for the Quantum Biology Institute (QBI).

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