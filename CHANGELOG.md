# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-03-06
### Added
- Image optimization pipeline (Phase 4): resizes images wider than 1200px and compresses for web delivery
- EXIF orientation handling to preserve correct image rotation after optimization
- Frontmatter injection (Phase 0a): auto-generates titles from filenames for MyST rendering
- Image linebreak normalization (Phase 0b): ensures images render as blocks, not inline
- Configurable exclusion prefixes for filtering directories (e.g., confidential `5_*` folders)
- Error handling for image optimization to prevent individual bad files from halting the pipeline
- Multi-vault support: unified `myst.yml` generation across multiple research vaults via `generate_multi_vault_config()`
- Display name overrides (`DISPLAY_NAMES` dict) to preserve correct casing for vault names (e.g., "LA" no longer renders as "La")
- Expanded `EXCLUDED_DIRS` to filter `venv`, `node_modules`, `site-packages`, `.dist-info`, and other non-publishable directories from staging

### Fixed
- Exclusion filter in `create_staging_directory` now uses `EXCLUDED_PREFIXES` constant instead of hardcoded tuple
- `EXCLUDED_PREFIXES` changed from set to tuple for compatibility with `str.startswith()`
- Duplicate TOC entries caused by nested `for` loop in `scan_folder_recursive`
- `myst-eln.service` infinite rebuild loop triggered by empty/truncated `.ipynb` files
- Removed `--headless` flag from service config (MyST v1.8.0 silently skips the app server with this flag)

## [0.3.0] - 2025-11-13
### Added
- Command-line argument support for specifying source bucket path
- Error logging for missing files during link conversion
- Support for URL-encoded filenames (%20) in Obsidian links

### Fixed
- File lookup now sanitizes both source filenames and lookup queries to handle spaces and URL encoding
- Eliminated false "duplicate file" warnings caused by indexing files twice
- Non-image files (.stl, .ino, .ipynb) now correctly converted to download links instead of broken image embeds
- Images with spaces in filenames now render correctly

## [0.2.0] – 2025-11-11
### Added
- Non-image files are now converted into downloadable links.

### Fixed
- Files with spaces in their names are automatically renamed (spaces → underscores)
  to avoid MyST rendering failures.

## [0.1.0] – 2025-11-07
### Added
- Initial working pipeline: build `myst.yml`, preprocess Obsidian vaults, stage files safely.