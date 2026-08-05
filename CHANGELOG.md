# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Fixed
- **Frontmatter injection no longer corrupts files that already have frontmatter.**
  Titles were spliced at a hardcoded string offset, colliding with the opening
  `---` delimiter and emitting invalid YAML (`---title: Entry`) for every vault
  file with frontmatter but no `title:` key.
- Content opening with a horizontal rule (`--- some text`) is no longer misread
  as frontmatter and silently left without a title.
- `subtitle:` is no longer mistaken for an existing `title:` (the check now
  parses the block instead of substring-matching).
- Titles containing colons, apostrophes, or both are now quoted and escaped by
  PyYAML rather than by hand, so they round-trip correctly.
- CRLF line endings are preserved when merging into existing frontmatter.

### Added
- `hide_footer_links` site option, emitted as a real YAML boolean.
- Test suite: 108 tests covering the transform chain, staging exclusion policy,
  and `myst.yml` generation.
- Pinned dependency versions in `requirements.txt`.

### Removed
- `generate_myst.py` and `utils.py` — both superseded and imported by nothing.

## [0.4.0] - 2025-02-25
### Added
- Image optimization pipeline (Phase 4): resizes images wider than 1200px and compresses for web delivery
- EXIF orientation handling to preserve correct image rotation after optimization
- Frontmatter injection (Phase 0a): auto-generates titles from filenames for MyST rendering
- Image linebreak normalization (Phase 0b): ensures images render as blocks, not inline
- Configurable exclusion prefixes for filtering directories (e.g., confidential `5_*` folders)
- Error handling for image optimization to prevent individual bad files from halting the pipeline

### Fixed
- Exclusion filter in `create_staging_directory` now uses `EXCLUDED_PREFIXES` constant instead of hardcoded tuple
- `EXCLUDED_PREFIXES` changed from set to tuple for compatibility with `str.startswith()`

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