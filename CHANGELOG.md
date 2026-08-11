# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-08-11

A security and reliability pass over the whole pipeline, plus a restructure into
an installable package. See REFACTOR_PLAN.md for the findings behind each change.

**Upgrading:** the entry point changed and the first build behaves differently.
Read `deploy/README.md` before running this on the server — in particular, the
build refuses to adopt the existing staging directory until it is marked with
`.qbi-staging`, and the first sync prunes anything no longer publishable.

### Changed
- **Installable package with a `qbi` command.** Code moved under
  `src/qbi_pipeline/`; install with `pip install -e .`. The entry point is now
  `qbi build` / `qbi audit` rather than `python build_pipeline.py` and
  `python vault_audit.py`.
- **Staging is synced, not rebuilt.** Only new and changed files are written,
  and files that no longer exist in a vault are pruned. The staging directory
  can therefore be kept under version control — the previous `shutil.rmtree`
  would have deleted `.git` along with everything else — and `git status` there
  shows exactly what a build changed.
- **Files are published by permission, not by omission.** Only allow-listed
  extensions are staged; anything else is skipped and reported. Extra types can
  be opted in via `publish_extensions` in the build config.
- Every build prints a per-vault **extension census**, and warns — naming both
  page and target — when a page links to a file the allow-list left out.
  Confidential and `.qbi-exclude` subtrees are reported as counts only, never
  by name.
- Text cleanup is **code-aware**: fenced blocks and inline code spans are left
  byte-for-byte intact, so `@decorator` and string literals inside code are no
  longer rewritten. Escaping `@` in prose is unchanged and intended — MyST reads
  a bare `@` as the start of a citation reference.
- Failures exit non-zero and report to stderr, so a failed build is
  distinguishable from a clean one by cron or CI.
- Transforms split one module per phase as pure functions; auditing split into
  checks and reporting.

### Added
- `.qbi-exclude` marker file: excludes the folder it sits in and everything
  beneath it, so content can be kept off the site without renaming anything.
- `--dry-run` to preview what a build would change without writing.
- **TIFF support.** TIFFs are converted to PNG on the way into staging, since no
  browser renders them inline. 16-bit and float images are rescaled to 8-bit for
  display — lossy in the measurement sense, so the original stays in the vault.
- **Video support.** `.mp4` renders inline as a `<video>` element; `.mov` and
  `.webm` publish as download links, because MyST renders those as a broken
  `<img>`.
- Publishable types now include bioinformatics artifacts (`.dna`, `.aln`,
  `.fa`, `.fasta`, `.treefile`, `.nwk`, `.gb`) and tabular data (`.csv`,
  `.tsv`).
- **Page-to-page wikilinks.** `[[Build Guide]]`, `[[Guide|alias]]` and
  `[[Guide#Heading]]` become real links; only `![[embeds]]` were handled before,
  so page links reached the site as literal double-bracketed text. Heading
  anchors match mystmd's own slugs, including the `id-` prefix it gives a slug
  that starts with a digit — which is most headings in a numbered protocol.
- **Audit: links to missing headings.** A link whose page exists but whose
  heading was renamed or renumbered passes every other check and silently drops
  the reader at the top of the page. Reported per source page.
- **Audit: broken page links and unterminated links.** `[[Page]]` links are
  checked against the vault, and a link missing its closing parenthesis — which
  renders as literal text on the site — is reported as such.
- Single source of truth for publication policy (`policy.py`) and naming
  (`naming.py`), shared by the build, config generation and audit tooling.
- `deploy/`: systemd timer and unit, a build wrapper that takes a lock, stops
  MyST, syncs and restarts it, plus setup documentation.
- Test suite: 328 tests. CI runs pytest and ruff on Python 3.12.

### Security
- Staging no longer deletes the directory `output` points at. Output paths that
  are, or contain, a vault or the root are rejected, and a non-empty directory
  without a `.qbi-staging` marker is refused outright.
- Symlinked files are refused rather than dereferenced, so a link inside a vault
  can no longer publish the contents of a file outside it.
- Audit reports no longer scan or name files inside confidential folders. That
  divergence — `vault_audit.py` not knowing about the `5_*` convention the rest
  of the pipeline enforced — was the most direct disclosure risk.
- Site navigation enforces the confidential-folder rule itself rather than
  relying on preprocessing having already stripped those folders.
- Image EXIF (GPS coordinates, device serials, timestamps) is stripped
  unconditionally.

### Fixed
- **Frontmatter injection no longer corrupts files that already have
  frontmatter.** Titles were spliced at a hardcoded string offset, colliding
  with the opening `---` delimiter and emitting invalid YAML (`---title: Entry`)
  for every vault file with frontmatter but no `title:` key.
- `subtitle:` is no longer mistaken for an existing `title:`, and content
  opening with a horizontal rule is no longer misread as frontmatter.
- Titles containing colons, apostrophes, or both are quoted and escaped by
  PyYAML rather than by hand. CRLF line endings are preserved.
- **Loose Obsidian link paths now resolve.** Obsidian resolves links by
  searching the vault, not by treating paths as literally relative to the page,
  so a note in `2025/` can reference `attachments/plot.png` for a file in the
  parent folder. 33 of 225 image references in a real vault were broken this
  way; after the fix, none are.
- URL sanitizing no longer rewrites external links, which turned
  `https://example.org/my%20paper.pdf` into `.../my_paper.pdf`.
- **MyST's `_build/` is no longer pruned.** Sync deleted everything under the
  staging root that did not correspond to a vault file, including MyST's build
  cache and the theme's `node_modules` — which a running `myst start` holds
  open. Anything at the staging root beginning with `_` or `.` is now preserved.
- Malformed notebooks are skipped with a warning. A file containing `{}` is
  valid JSON but not a valid notebook, and used to fail the entire MyST build.
- Image optimization works again: resizing above 1200px, recompression, EXIF
  orientation applied before metadata is dropped, and a decompression-bomb
  guard. Optimized images are no longer re-encoded on every build, which was
  degrading JPEG quality cumulatively.
- The MyST project id is stable across builds instead of a fresh UUID each run.
- `vault_audit.py` no longer crashes with `UnicodeEncodeError` when printing a
  report on a Windows console.
- `prettify_folder_name` had three different behaviors across four copies. Page
  titles for all-digit filenames (e.g. `2025.md`) were empty, and hyphenated
  names rendered as `Research-Biology-La` rather than `Research Biology La`.
- **Display titles no longer flatten capitals that carry meaning.** `str.title()`
  lowercases the rest of every word, so `NI_DAQ_testing` became "Ni Daq Testing",
  `LOV_domain_phylogenetics` became "Lov Domain...", and `0p5mT` — a field
  strength of 0.5 mT — became "P5Mt". A word carrying any capital is now left as
  written, which also preserves the lowercase-first convention in `pRSETb` and
  `phrB`. All-lowercase words, which have nothing to preserve, go through an
  acronym table in `naming.py`; add entries there as new ones turn up.
  `DISPLAY_NAMES` overrides now apply at any depth, not only to vaults and
  projects.
- Only a one- or two-digit ordering prefix is stripped from a display title. The
  greedy strip also ate the date off `20250918_rampdown.md`, and a folder of
  entries distinguished only by date collapsed into one repeated nav title.
- **Two vault names that sanitize alike no longer overwrite each other.**
  `to order.dna` and `to_order.dna` both stage as `to_order.dna`; both were
  written to that path, so the published file was whichever was walked last and
  every build reported them as changed forever — a spurious commit in the
  staging repo every night. The collision is now reported and resolved
  deterministically.
- Wikilink conversion is code-aware. `df[['time', 'signal']]` is pandas column
  selection, and a vault with a matching page name would have had its published
  code rewritten into a markdown link.
- Audit link scanning handles balanced parentheses in a filename.
  `Linear_ramp_B(5100).png` is real, and the previous regex truncated it at the
  first `)` and reported a broken reference to a file nobody had written.

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