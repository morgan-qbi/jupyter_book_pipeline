# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
