# Refactor & Security Plan

> **Working document.** Tracks the cleanup of the QBI Jupyter Books pipeline:
> what was wrong, what was decided and why, and what is left. Kept in the repo
> as a record — the reasoning here is not recoverable from the diffs.

**Baseline audited:** commit `ab4169e`, 2026-08-05
**Production runtime:** Python 3.12.3 on `/srv/qbi` (Linux); this Windows checkout is a synced copy.

> **Note:** this file was accidentally truncated during Phase 3 and reconstructed
> from the session record. Substance is intact; exact original wording of a few
> early paragraphs may differ.

---

## 1. Why this work

The pipeline publishes Obsidian research vaults to a **public** MyST site. Three things followed from that, and the original code got all three backwards:

1. Anything reaching the staging directory is world-readable. Staging was **copy-everything-except-a-denylist**.
2. The rules for "never publish this" were duplicated across three modules with **three different definitions**, and had already drifted apart.
3. There were **no tests**, so any change to those rules was unverifiable.

Structurally, the repo was 9 flat files at root with `prettify_folder_name` implemented four times in three different ways, and one file (`generate_myst.py`) that was the superseded ancestor of another.

---

## 2. Security findings

Severity reflects impact on a pipeline whose output is public.

### 🔴 Critical

**S-1 — Confidential-folder exclusion is fail-open and divergent.** — 🟡 **PARTLY FIXED** (Phase 1)
The divergence is gone: `policy.py` is the single implementation, imported by all three modules, and `vault_audit` no longer scans confidential folders. The `.qbi-exclude` marker gives researchers an opt-out at any depth. Still **fail-open on naming**, though — a folder called `Confidential` or `05_Private` publishes unless it carries a marker. Closing that fully needs D-2 option 3 (content scanning), still deferred.

*Original:* the `5_` prefix marked confidential folders, declared in `preprocessing.py` and `config_generator.py`, but `vault_audit.py` did not exclude it at all — so `vault_audit.py --all` read confidential folders and wrote their filenames and link references into `audit_reports/*.md`, which defaulted to the current working directory and was not gitignored.

**S-2 — Copy-everything staging with no allow-list.** — ✅ **FIXED** (Phase 2)
Staging publishes by permission: `PUBLISHABLE_EXTENSIONS` in `policy.py`, extendable per-deployment via `publish_extensions` in the build config. Every build prints a per-vault extension census, and a page linking to a file the allow-list skipped produces an explicit warning naming both.

*Original:* every file not explicitly excluded was copied into staging, and staging is published. A `grant_budget.xlsx`, `participant_data.csv`, or `api_keys.txt` in a vault shipped to the web.

**S-3 — Symlinked files are dereferenced and copied.** — ✅ **FIXED** (Phase 2)
Sync refuses symlinked files rather than dereferencing them, and counts them in the build summary. Directory symlinks became unreachable once traversal moved to `os.walk` in Phase 1.

*Original:* a symlinked *file* satisfied `item.is_file()` and `shutil.copy2` followed it, publishing the contents of a file outside the vault.

**S-4 — `shutil.rmtree` on an unvalidated config path.** — ✅ **FIXED** (Phase 2)
There is no `rmtree` any more. Three guards stack: `validate_output_path` rejects an output that is, or contains, a vault or the root; `assert_safe_staging_target` refuses any non-empty directory lacking a `.qbi-staging` marker; and pruning only removes files absent from the expected set, never whole trees. Both failure modes verified end-to-end with source data left intact.

*Original:* `staging_path` was recursively deleted with no guard, and `output` was never validated. `output: "/srv/qbi"` — one line above the real vault paths in the config — would have deleted the entire research share.

### 🟠 High

**S-5 — Stale files persist in multi-vault builds.** — ✅ **FIXED** (Phase 2)
`prune_stale_files` removes staged files with no corresponding vault file, so deleting a file — or marking a folder `.qbi-exclude` after it has been published — takes it down. Preserved names (`.git`, `_static`, `myst.yml`, the manifest) are never pruned.

*Original:* `build_multi_vault` wiped each vault's *subdirectory* but never the staging root, so unpublishing silently did not work.

**S-6 — Image EXIF is published intact, and optimization is switched off.** — ✅ **FIXED** (Phase 2)
EXIF stripping is unconditional and optimization is back on. `strip_exif` clears `img.info` on a copy rather than rebuilding from raw pixel data — that drops the metadata the JPEG encoder would otherwise write back, while keeping palettes and transparency intact. `exif_transpose` runs first so orientation is baked into the pixels before the tag is discarded. Resizing above 1200px, a 64-megapixel decompression-bomb guard, and per-format tests (JPEG/PNG/WebP/palette-PNG/animated-GIF/EXIF-rotated/corrupt) are in place; only the staged copy is ever rewritten.

*Original:* `optimize_image` returned immediately with its body parked in a string literal, so lab-notebook photographs shipped full-size with GPS coordinates, device serials and timestamps embedded.

**S-7 — Unpinned dependencies.** — ✅ **FIXED** (Phase 0)
Pinned to the versions production runs: `PyYAML==6.0.3`, `pillow==12.1.1`, `pytest==8.3.4`, declared in `pyproject.toml` with `requirements.txt` kept in step. The `MAX_IMAGE_PIXELS` bomb guard landed with S-6.

**S-8 — `.gitignore` is actively harmful.** — ✅ **FIXED** (Phase 0)
The blanket `*.yml` was narrowed to `/build_config.yml`; it would otherwise have silently swallowed any `.github/workflows/*.yml`. `venv/`, `reports/`, `audit_reports/` and secret patterns added. Local test-vault patterns added later, so research content copied into the repo for testing cannot be swept into history by `git add -A`.

### 🟡 Medium — correctness

**S-9 — `fix_text_issues` escapes every `@` in the document.** — ✅ **FIXED** (Phase 3)
`apply_outside_code` splits a document into prose and code spans (fenced ``` / ~~~ blocks and inline spans) and applies text cleanup to prose only, so decorators and string literals inside code survive untouched. Escaping `@` in *prose* is correct and stays: MyST reads a bare `@` as the start of a citation reference.

*Original:* the escape was applied to the whole document, corrupting Python decorators inside code fences.

**S-10 — `json.load(open(item))` leaks its handle and omits `encoding=`.** — ✅ **FIXED** (Phase 2)
The notebook check uses a context manager with an explicit encoding, and both `myst.yml` writes pass `encoding='utf-8'` and `allow_unicode=True`.

**S-11 — `uuid.uuid4()` regenerates the MyST project id on every build.** — ✅ **FIXED** (Phase 2)
An id already present in a generated `myst.yml` is reused, so identity survives even a site rename; otherwise it is derived deterministically with `uuid5` from the site title.

**S-12 — Bare `except Exception` swallowing errors into `print`.** — 🟡 **PARTLY FIXED** (Phase 3)
Exit codes work: every failure path returns non-zero and errors go to stderr, so cron or CI can tell a failed build from a clean one. **Structured logging is still outstanding** — output remains `print`-based, which suits the human-readable census but is wrong for machine consumption. No levels, no timestamps, no `--verbose`.

**S-13 — Site options edited in the dead file, so the change never shipped.** — ✅ **RESOLVED** (Phase 0)
`generate_myst.py` carried an *uncommitted* edit adding `hide_footer_links` to the site options, but that module was imported by nothing, so the change never took effect. Rescued before deletion. Resolved per D-3: `hide_footer_links` is now set in `build_site_config` as a real YAML boolean, and `logo_dark` **intentionally** reuses the Light Mode asset — the only logo file that exists. A test records that so it is not "corrected" later toward a path that is not there.

**S-14 — `inject_frontmatter` corrupts files that already have frontmatter.** — ✅ **FIXED** (Phase 0)
The title was spliced in at a hardcoded offset of 3, colliding with the opening delimiter and emitting `---title: Entry`. Confirmed in real build output, not just tests, which is why it was fixed first.

Rewritten around three helpers: `find_frontmatter` (recognizes a block only when the first line is a bare `---` and a later line is a bare `---` or `...`, and returns the true splice offset); `has_title` (parses with `yaml.safe_load` rather than substring-matching `'title:'`, which previously matched `subtitle:`); and `format_title_line` (delegates quoting to `yaml.safe_dump`, so colons, apostrophes and both together round-trip). Unterminated `---` blocks get a fresh block prepended rather than being left titleless. CRLF preserved.

**S-15 — URL sanitizing is applied to external links.** — ✅ **FIXED**
`normalize_markdown_link_urls` rewrites every link target, including remote ones, so `https://example.org/my%20paper.pdf` becomes `.../my_paper.pdf` and the link 404s. It should skip `http`/`https`/`data:` the way `rewrite_absolute_paths` already does. Small fix, locked by a characterization test that currently asserts the broken behavior.

**S-16 — The TOC layer has no confidential-folder defense of its own.** — ✅ **FIXED** (Phase 1)
`scan_project_structure` now applies `should_skip_dir` to chapter folders, so the TOC layer enforces the policy independently rather than relying on preprocessing having already stripped `5_*` from staging.

**S-17 — `vault_audit.py` crashes when printing a report on Windows.** — ✅ **FIXED** (Phase 1)
The report contains status glyphs a cp1252 console cannot encode, and the module never reconfigured stdout. Invisible in production (Linux/UTF-8). Now handled centrally in `cli.main`.

**S-18 — Optimized images were re-copied and re-encoded on every build.** — ✅ **FIXED** (Phase 2)
Found by end-to-end verification, not by tests: a no-op rebuild still reported files written. Optimization rewrites the staged copy, so a resized, metadata-stripped image can never match its source, and comparing the two marked every image as changed on every run. `git status` stayed clean because optimization is deterministic, which is exactly why it would have gone unnoticed — but every build re-encoded every JPEG, and repeated lossy re-encoding degrades quality cumulatively. A `.qbi-manifest.json` records each source's size and mtime, making the check exact.

**S-19 — Obsidian's loose link paths break once published.** — ✅ **FIXED**
Obsidian resolves a link by *searching* the vault, not by treating the path as literally relative to the page. A note in `2025/` can write `attachments/plot.png` for a file that actually lives in the parent folder's `attachments/`; it renders fine in Obsidian and 404s on the site. Wikilinks already had a vault-wide fallback, but standard markdown images did not.

`rewrite_absolute_paths` now tries three resolutions in order: exact vault-root path, already-correct-relative, then a vault-wide filename lookup — the last being what Obsidian itself would do.

Found only by running a real vault: **33 of 225 image references were broken this way**, and none of the synthetic fixtures reproduced it.

**S-20 — TIFFs could not be published at all.** — ✅ **FIXED** (feature)
No browser renders TIFF inline, so microscopy images were either skipped or emitted as broken `<img>` tags. They are now converted to PNG on the way into staging.

The conversion renames the file, and that rename has to reach every place a link is resolved — Obsidian embeds carry a bare filename with no path, so the rename is applied when the vault is **indexed**, not when files are copied. `build_file_index` therefore keys on the vault name (`scan.tif`) and stores the staged path (`scan.png`).

16-bit and float TIFFs are rescaled to 8-bit for display, which is lossy in the measurement sense: it maps the image's own min..max onto 0..255. Fine to look at, **not** to read quantitatively. The original stays in the vault untouched. Multi-page TIFFs keep the first frame, with a note in the build log.

**S-21 — Sync deleted MyST's build directory.** — ✅ **FIXED**
Pruning removed everything under the staging root that did not correspond to a vault file, including `_build/` -- MyST's build cache, its rendered site, and the theme's `node_modules`. On the server, `myst start` runs as a systemd service holding those open, so every scheduled build would have deleted them underneath the live process.

Anything at the staging root beginning with `_` or `.` is now preserved on principle: `EXCLUDED_PREFIXES` forbids those from vault content, so nothing the pipeline stages can ever start with them, and anything in staging that does belongs to something else. That covers `_build`, `_static`, `.git`, and whatever a future MyST version invents.

Found while preparing the deployment, not by the test suite -- the staging fixtures had no reason to contain a `_build`.

### ✅ Cleared

Full 13-commit history reviewed — every blob is a small source file. **No secrets or large binaries have ever been committed.** History is clean; no rewrite required.

---

## 3. Layout

As built in Phase 3:

```text
src/qbi_pipeline/
├── cli.py            qbi build / qbi audit, exit codes
├── policy.py         what may be published (single source of truth)
├── naming.py         sanitizing, prettifying, display names
├── index.py          vault file index
├── staging.py        incremental sync, census, safety guards
├── myst_config.py    TOC and myst.yml generation
├── transforms/       one module per phase, pure functions
│   ├── frontmatter.py  paths.py  links.py  text.py  images.py
└── audit/
    ├── checks.py     the scans
    └── report.py     rendering and the audit command
tests/                one file per concern; test_policy.py is the security one
pyproject.toml        packaging, pinned deps, pytest and ruff config
```

`policy.py` is the load-bearing piece. Confidential data could leak because "what must never be published" was expressed three times in three ways.

Deviations from the original target layout, both deliberate:

- `config.py` was not split out. Config loading and validation is ~60 lines and only `cli.py` uses it; a separate module would be indirection without benefit. Revisit if config grows.
- `myst_config.py` rather than `myst/config.py` — a package for one module earns nothing.

---

## 4. Phases

| Phase | Work | Addresses |
| --- | --- | --- |
| **0 — Safety net** ✅ | Fix `.gitignore`; delete dead modules; pin deps; characterization tests. Then: fix frontmatter corruption; apply rescued site options | S-7, S-8, S-13, S-14 |
| **1 — Unify** ✅ | Extract `policy.py` (incl. `.qbi-exclude`) and `naming.py`; all three modules import them | S-1, S-16, S-17 |
| **2 — Harden** ✅ | Incremental sync, allow-list staging + extension census, symlink rejection, output guards, stale pruning, EXIF stripping + restored optimization, stable project id | S-2 … S-6, S-10, S-11, S-18 |
| **3 — Restructure** ✅ | `src/` layout, split transforms, unified `qbi` CLI, exit codes, fence-aware transforms | S-9, S-12 (partly) |
| **4 — Polish** | CI running tests + ruff; structured logging; S-15 | S-12 (rest), S-15 |

### Phase 0 — ✅ COMPLETE

- [x] `.gitignore` rewritten; `venv/` was one `git add -A` from being committed
- [x] Deleted `generate_myst.py` and `utils.py` (imported by nothing; options rescued into S-13 first)
- [x] Pinned dependencies
- [x] Characterization tests locking behavior *as it was*, bugs included, each tagged with its finding ID
- [x] S-14 fixed; S-13 resolved

**Findings discovered *by* writing the tests:** S-14, S-15, S-16 — none visible from reading alone.

### Phase 1 — ✅ COMPLETE

**The divergence was not purely accidental.** Merging the three exclusion lists naively would have broken the site: `config_generator` excluded `attachments/` and `preprocessing` did not, because attachments must be *staged* (or every image embed 404s) but must *not* appear as a browsable chapter. Two different questions; flattening them into one list is what let the copies drift.

| Tier | Meaning | Example |
| --- | --- | --- |
| `EXCLUDED_DIRS` / `EXCLUDED_PREFIXES` | Never published, never traversed | `5_*`, `.obsidian`, `venv` |
| `NON_NAVIGABLE_DIRS` | Staged as page assets, never in navigation | `attachments/` |

The same reasoning applied to image extensions: `preprocessing` used its set to choose embed-vs-download, `vault_audit` used its own (including TIFF) purely for counting. Unifying them would have turned TIFFs into broken `<img>` tags, so they are now `WEB_IMAGE_EXTENSIONS` (renderable) and `IMAGE_EXTENSIONS` (a reporting superset).

**Traversal prunes rather than filters.** `iter_vault_files` / `iter_vault_dirs` drop excluded directories from `os.walk`'s `dirnames` in place, so an excluded subtree is never descended into — required for `.qbi-exclude` to mean "and everything beneath", and it extends `os.walk`'s refusal to follow directory symlinks to every consumer.

**Behavior changes from unifying `prettify_folder_name`** (preprocessing had the buggy copy, and it generates page titles): `2025.md` produced an **empty title**, now `2025`; hyphenated names rendered `Research-Biology-La`, now `Research Biology La`.

### Phase 2 — ✅ COMPLETE

**Incremental sync replaced delete-and-rebuild.** Requested so the staging directory could be a git repository, and it turned out to be a prerequisite rather than an optimization: `shutil.rmtree(staging_path)` deletes everything under the output path *including `.git`*, so the moment staging was initialized as a repo, the next build would have destroyed it. Not wiping also forces deletions to be reconciled explicitly, which is what finally fixes S-5.

Verified end-to-end with a real git repo in staging:

| Scenario | Result |
| --- | --- |
| Rebuild, no source changes | `0 written, 4 unchanged`; `git status` clean |
| Edit one page | `1 written, 3 unchanged`; exactly one file modified |
| Delete a source file | `1 removed`; staged copy deleted |
| Mark a folder `.qbi-exclude` after publishing | staged copy deleted |
| `.git`, `_static`, `myst.yml` | untouched by pruning |

**The allow-list needed a second safety net.** A census reports *types*, but the failure that bites is a page linking to a file the allow-list skipped — a broken link, on a specific page, that no type-level summary points at. Link conversion receives the set of skipped paths and warns with both page and target. That required splitting sync into two passes: classify everything, then write.

**Staging safety is three independent guards**, not one check.

### Phase 3 — ✅ COMPLETE

200 tests passing. The package lives under `src/qbi_pipeline/` and installs with `pip install -e .`, providing a real `qbi` command.

**Verified as a true refactor.** The pre-refactor commit `b9f2121` was checked out in a git worktree, both versions run against the same vault, and the staged output diffed **byte-for-byte identical**. Note the fixture contains no code fences, so it does not exercise the S-9 change — that is a deliberate behavior change, covered by tests rather than by the diff.

`tests/conftest.py` no longer manipulates `sys.path`; that was a Phase 0 stopgap for the flat layout, and the editable install replaces it.

---

## 5. Open decisions

**D-1 — Allow-list vs. deny-list for publishing.** ✅ **DECIDED: allow-list. IMPLEMENTED in Phase 2.**
Default is deliberately conservative: pages (`.md`, `.ipynb`), web images, and `.pdf/.stl/.obj/.ino/.py`. Everything else is skipped and reported. **Worth checking on the first real build:** the "2_Curated Datasets" chapters likely hold CSVs, which are currently skipped. A census line saying `.csv 14 SKIPPED` is recoverable; silently publishing `grant_budget.xlsx` is not. Adding types is one line in `publish_extensions`.

The census reports skipped extensions grouped and sorted by count, counts files rather than extension presence, and reports confidential/marked subtrees separately as counts only, never filenames.

**D-2 — How aggressive should confidential detection be?** ✅ **DECIDED: options 1 and 2 now, 3 later. IMPLEMENTED in Phase 1.**

1. The `5_` convention, centralized in `policy.py`.
2. `.qbi-exclude` — dropping the file in any folder excludes **that folder and everything beneath it**, recursively. No renaming required, works at any depth. The marker itself is never published.
3. Content-scanning for secret patterns — **deferred, not rejected**. This is what would close S-1's remaining fail-open gap.

**D-3 — Reconcile the site options rescued from `generate_myst.py`.** ✅ **DECIDED — applied.** See S-13.

---

## 6. Remaining work

- **S-15** — external URLs are mangled by link sanitizing. Small, self-contained.
- **S-12 (rest)** — structured logging.
- **S-1 (rest)** — fail-open naming rule; needs D-2 option 3.
- **Phase 4** — CI running tests and ruff.
- ~~Run a real vault through it.~~ **Done.** See below.


---

## 7. Real-vault run (research-biology-la)

8160 files in, 1003 staged. The vendored virtualenv inside
`3_code_bacterioscope/Revised_experiment_code` (2427 `.py`, 2285 `.pyc`,
`.dist-info`, `.pyd`) was correctly excluded by policy.

**MyST built cleanly: 63 HTML pages, zero errors.** Remaining MyST warnings are
all content-level (Notion frontmatter keys, empty link text, a legacy link
target), not pipeline failures.

**Link verification: 225 image references, 0 broken** after S-19. Before the
fix, 33 were broken.

Two findings came only from this run — S-19 and S-18 both surfaced end-to-end
rather than in tests. Worth remembering that the synthetic fixtures are too
tidy to catch this class of bug.

### Decisions waiting on you

13 non-image links point at file types the allow-list skips. These are
publication decisions, not bugs:

| Type | Count | What it is |
| --- | --- | --- |
| `.dna` | 2 | plasmid maps (SnapGene) |
| `.mov` / `.mp4` | 4 | experiment videos |
| `.csv` | 2 | phylogenetic tree data |
| `.aln`, `.fa`, `.treefile` | 3 | sequence alignments and phylogenies |
| `LICENSE` | 1 | no extension, so never matched |

The sequence and plasmid formats look like exactly the research artifacts worth
publishing as downloads. Add to `publish_extensions` to include them.

Two genuine vault-content problems, which `qbi audit` reports:

- 6 `Pasted image NNN.png` references with no matching file in the vault
- one link written relative to the project root rather than the page
  (`3_code_bacterioscope/Operation_test/systematic_calibration.ipynb`)

### Resolved since

Non-image links now get the same resolution as images, so the broken `.ipynb`
link is fixed. The allow-list gained video, bioinformatics and tabular formats.
After all of it: **228 image references, 0 broken**; one broken link remains, to
a `LICENSE` file with no extension.

**Video was settled empirically against mystmd 1.6.4**, not assumed:
`![](clip.mp4)` renders as `<video>`, while `.mov` and `.webm` fall through to a
broken `<img>`. Only `.mp4` is emitted inline; the others publish as download
links. Remuxing `.mov` to `.mp4` would be lossless for iPhone footage but needs
ffmpeg as a system dependency.

**Note on `.csv`:** now published by default, because the vault links to
phylogenetic data as CSV. That does mean a spreadsheet dropped in a vault
reaches the site. The `5_*` convention and `.qbi-exclude` are the controls.


---

## 8. Remaining

**Structured logging (S-12, remainder).** Output is still `print`-based: no
levels, no timestamps, no `--verbose`. Deprioritized rather than forgotten —
under systemd, journald already timestamps stdout and `journalctl -u
qbi-build` gives per-run history, which covers most of what logging would have
bought. Worth doing if the pipeline ever needs to be consumed by anything other
than a human reading a terminal.

**S-1 remainder.** The naming rule is still fail-open: a folder called
`Confidential` publishes unless it carries a `.qbi-exclude`. Closing it needs
D-2 option 3, content scanning, still deferred.

**Ideas raised, not started.** Each is a project rather than a fix:

- *Inline STL viewer.* MyST renders `.stl` as a broken `<img>`, so they publish
  as downloads today. A viewer means injecting a JS component
  (`<model-viewer>` or three.js) into the built site.
- *Rendering `.dna` / `.aln` in the browser.* No standard exists. There are JS
  libraries (seqviz for plasmid maps, MSA viewers for alignments) but nothing
  MyST supports natively, so this is custom work.
- *OCR for handwritten lab notes.* Worth knowing that classical OCR
  (Tesseract) is poor at handwriting; this needs handwriting recognition — a
  vision model or a specialist HTR service — and a human review step, since a
  wrong transcription of a lab notebook is worse than none.
