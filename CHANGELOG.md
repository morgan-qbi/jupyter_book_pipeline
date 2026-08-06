# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Changed
- **Staging is now synced incrementally instead of deleted and rebuilt.** Only
  new and changed files are written, and files that no longer exist in a vault
  are pruned. The staging directory can therefore be kept under version
  control — the previous `shutil.rmtree` would have deleted `.git` along with
  everything else — and `git status` there now shows exactly what a build
  changed.
- **Files are published by permission, not by omission.** Only allow-listed
  extensions are staged; anything else is skipped and reported. Extra types can
  be opted in via `publish_extensions` in the build config.
- Every build prints a per-vault **extension census** of what was published and
  what was skipped, and warns when a page links to a file the allow-list left
  out. Confidential and `.qbi-exclude` subtrees are reported as counts only,
  never by name.

### Added
- `.qbi-exclude` marker file: excludes the folder it sits in and everything
  beneath it, so content can be kept off the site without renaming anything.
- `--dry-run` to preview what a build would change without writing.
- Single source of truth for publication policy (`policy.py`) and naming
  (`naming.py`), shared by the build, config generation and audit tooling.

### Security
- Staging no longer deletes the directory `output` points at. Output paths that
  are, or contain, a vault or the root are rejected, and a non-empty directory
  without a `.qbi-staging` marker is refused outright.
- Symlinked files are refused rather than dereferenced, so a link inside a vault
  can no longer publish the contents of a file outside it.
- Audit reports no longer scan or name files inside confidential folders.
- Site navigation enforces the confidential-folder rule itself rather than
  relying on preprocessing having already stripped those folders.
- Image EXIF (GPS coordinates, device serials, timestamps) is now stripped
  unconditionally.

### Fixed
- Image optimization is working again: resizing above 1200px, recompression,
  EXIF orientation applied before metadata is dropped, and a decompression-bomb
  guard. Optimized images are no longer re-encoded on every build, which was
  degrading JPEG quality cumulatively.
- The MyST project id is stable across builds instead of a fresh UUID each run.
- `vault_audit.py` no longer crashes with `UnicodeEncodeError` when printing a
  report on a Windows console.
- `prettify_folder_name` had three different behaviors across four copies. Page
  titles for all-digit filenames (e.g. `2025.md`) were empty, and hyphenated
  names rendered as `Research-Biology-La` rather than `Research Biology La`.
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