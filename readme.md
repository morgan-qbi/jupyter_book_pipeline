# QBI Jupyter Books Pipeline

## Overview

This project automates the generation of reproducible [MyST](https://mystmd.org/) Jupyter Books directly from Obsidian research vaults used by the **Quantum Biology Institute (QBI)**.
It transforms live research vaults into browsable, published documentation served from QBI's local infrastructure.

The pipeline builds a full `myst.yml` configuration based on vault structure, preprocesses files for MyST compatibility, and stages everything safely for compilation—ensuring that raw data and notes remain untouched.

## Why This Exists

QBI uses Obsidian for collaborative lab notebooks and local storage for research data.
This pipeline bridges the gap between private research notes and public scientific
publishing, enabling real-time iterative publication without manual reformatting.

## Install

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .            # add [dev] for the test suite: pip install -e ".[dev]"
npm install -g mystmd
```

This installs a `qbi` command. Editable mode (`-e`) links to the working copy,
so code changes take effect without reinstalling.

Requires Python 3.12+ (the server runs 3.12.3).

## Usage

```bash
# Multi vault (the normal case)
qbi build --config build_config.yml

# Single vault
qbi build ../path/to/vault ../_build_staging

# Single vault, titled exactly (multi-vault titles come from the config)
qbi build ../path/to/vault ../_build_staging --name "Research Team LA"

# Preview what would change, writing nothing
qbi build --config build_config.yml --dry-run

# Vault hygiene report: broken references and page links, links to headings
# that no longer exist, unterminated links, Notion import leftovers
qbi audit ../path/to/vault
qbi audit /srv/qbi --all -d reports/

cd _build_staging && myst start
```

Failures exit non-zero, so a broken build is visible to cron, CI, or a wrapper
script rather than passing silently.

See [build_config.example.yml](./build_config.example.yml) for the config
format, the publication allow-list, and how to keep content off the site.

## How publishing is decided

The site is public, so the pipeline publishes **by permission, not by omission**.

- **Allow-list.** Only permitted file types are staged. Every build prints a
  per-vault **extension census** of what was published and what was skipped,
  and warns — naming both page and target — when a page links to a file the
  allow-list left out. Add types via `publish_extensions` in the build config;
  no code change needed.
- **Confidential content.** Folders named `5_*` are confidential by convention,
  and a `.qbi-exclude` file excludes the folder it sits in plus everything
  beneath it, recursively. Both rules are enforced identically in staging, in
  site navigation, and in audit reports.
- **Incremental sync.** Staging is synced, not rebuilt: only changed files are
  written, and files removed from a vault are pruned. The staging directory can
  therefore be kept under version control, and `git status` there shows exactly
  what a build changed.

Source vaults are never modified.

## What the pipeline does to content

| Stage | Behavior |
| --- | --- |
| Frontmatter | Injects a title from the filename, preserving existing frontmatter and its keys |
| Images | Ensures embeds render as blocks; resizes above 1200px; **strips EXIF unconditionally** (GPS, device serials, timestamps) |
| TIFF | Converted to PNG, since no browser renders TIFF inline. 16-bit and float images are rescaled to 8-bit for display |
| Video | `.mp4` renders inline as `<video>`; `.mov` and `.webm` publish as download links, because MyST renders those as a broken `<img>` |
| Links | Resolves Obsidian `![[embeds]]`, `[[page links]]` and loose markdown paths against a vault-wide index — Obsidian resolves links by searching, not by strict relative path. Skips code, so pandas `df[['a','b']]` is left alone |
| Titles | Derived from the filename, but capitals already in a name are preserved: `NI_DAQ_testing` and `pRSETb` mean what they say. Lowercase acronyms come from `ACRONYMS` in `naming.py`; exact names come from a vault's `name:` or `display_names` in the build config, or `--name` in single-vault mode |
| Text | Normalizes dashes and escapes `@` for MyST citations, **skipping code blocks and inline code** |
| Notebooks | Malformed `.ipynb` files are skipped with a warning rather than failing the whole site build |

### A note on TIFF conversion

Rescaling 16-bit microscopy data to 8-bit is lossy *in the measurement sense*:
it maps the image's own min–max onto 0–255. The result is fine to look at and
**must not be read quantitatively**. The original stays in the vault, untouched.
Multi-page TIFFs keep only their first frame, and say so in the build log.

## Deployment

See [deploy/README.md](./deploy/README.md) for running this on the server: a
systemd timer and unit, a wrapper that stops MyST, syncs, and restarts it, and
the first-run setup — which is **not optional**, because the build refuses to
adopt an existing staging directory until it is marked.

## Development

```bash
pip install -e ".[dev]"
pytest          # 341 tests
ruff check src tests
```

The test suite is organized by concern; `tests/test_policy.py` and
`tests/test_staging_policy.py` are the security-relevant ones — they assert what
does and does not reach a public website.

[REFACTOR_PLAN.md](./REFACTOR_PLAN.md) records why the current design is the way
it is: the security findings behind it, the decisions taken, and what is still
open. Worth reading before changing the exclusion rules.

## Roadmap

Planned enhancements focus on deeper automation, FAIR compliance, and usability for researchers.

### Short term

- ~~Git-based version control with automated commits (no scientist-facing git interaction)~~ — staging is a git repo; `deploy/qbi-build.sh` commits each build
- ~~Vault audit tooling and cleanup checklists for researchers~~ — `qbi audit`
- LaTeX source sharing for micropublications
- Structured logging (levels, timestamps) for machine consumption

### Medium term

- OCR for scanned and handwritten lab notebook images (needs handwriting
  recognition, not classical OCR, plus a human review step)
- Convert `.py` scripts into executable `.ipynb` notebooks for live rendering
- 3D viewer for `.stl` and other scientific model files
- In-browser viewers for plasmid maps (`.dna`) and sequence alignments (`.aln`)
- Metadata templates (DOI, timestamps, authorship)
- DeSci Nodes archiving for micropublications

### Long term

- Static site backup/failover for availability when local infrastructure is offline
- AI-assisted metadata suggestion and error detection
- Containerized builds for full reproducibility across systems

## Changelog

See [CHANGELOG.md](./CHANGELOG.md)
