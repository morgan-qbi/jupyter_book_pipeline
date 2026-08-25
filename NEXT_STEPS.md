# Next Steps

Where the work stopped and what to pick up. Written 2026-08-21, at commit
`69cb96b` on `main`.

Paths here use the `/srv/qbi` placeholder, same as the rest of the repo — this
repository is public. Substitute the real share path as you go; the real ones
live in `build_config.yml`, which is gitignored.

---

## State at handoff

The refactor is finished and verified against a real vault. Nothing has been
pushed to GitHub yet, and the deployment has never been run.

- **341 tests** passing, ruff clean, CI configured (`.github/workflows/ci.yml`)
- Verified end to end on `research-biology-la`: MyST exits 0, builds 71 pages,
  and a second consecutive build writes **zero files** — the incremental sync
  is genuinely idempotent, which is what makes staging viable as a git repo
- Three commits sit on `main` beyond the last push:

  ```
  69cb96b  audit malformed notebooks, move display names into config
  4b6d26f  audit heading anchors, and stop titles flattening capitals
  7f8e794  convert page-to-page wikilinks, and block images followed by text
  ```

Read [REFACTOR_PLAN.md](./REFACTOR_PLAN.md) if you need the reasoning behind any
of the design decisions — particularly before changing the exclusion rules.

---

## 1. Push to GitHub

Unblocked. The repo is public and has been checked: no credentials, no server
layout, no vault contents.

- [x] **`.csv` publishes by default — re-confirmed 2026-08-25.** Reviewed with
      the tradeoff in view and kept deliberately: publishing the data is worth
      more than withholding it. A `grant_budget.csv` dropped into a vault would
      also reach the site, and `5_*` folders plus `.qbi-exclude` are the only
      things stopping it — the decision rests on researchers knowing that
      nothing sensitive belongs in `1_` through `4_`. That is a briefing, not a
      control; see "naming rules fail open" in section 5.
- [ ] `git push origin main`

If you ever want `.csv` off again, remove it from `PUBLISHABLE_EXTENSIONS` in
`src/qbi_pipeline/policy.py` and let people opt in per-build via
`publish_extensions` in the config instead.

---

## 2. First run on the build server

**Do this on a weekend or evening.** Not because it endangers the vaults — the
pipeline only ever reads them, and staging refuses to touch a directory it has
not claimed — but because `qbi-build.sh` **stops `myst start`, syncs, and
restarts it**. The site goes down for the length of a full first sync, on
scripts that have never actually executed. Syntax-checked is not the same as
run.

Follow [deploy/README.md](./deploy/README.md) — it is the real procedure. The
two steps that are easiest to skip and most annoying to debug:

- [ ] **`touch /srv/qbi/_build_staging/.qbi-staging` before anything else.**
      Without the marker the build refuses the directory outright and stops.
      That guard is deliberate: sync prunes files it considers stale, so
      pointing `output:` at a real data directory has to be impossible.
- [ ] **Make the first build revertable.** `git init` the staging directory and
      commit the site as it stands *before* running the pipeline. The first
      build is a large diff — titles, links, TIFF→PNG, and the allow-list
      pruning anything no longer publishable. You want a commit to diff against
      and to roll back to.

Then, in order:

- [ ] `qbi build --config build_config.yml --dry-run` and read the SKIPPED
      lines in the extension census. Anything there that belongs on the site
      goes into `publish_extensions` — a config change, not a code change.
- [ ] **Run `./deploy/qbi-build.sh` by hand once**, before enabling the timer.
      This is the step that matters most. A typo in the unit file, a lock path
      the service user cannot write, a missing `chmod +x` — you want to find
      that while you are watching, not at 02:15.
- [ ] Only then `systemctl enable --now qbi-build.timer`.
- [ ] Check `journalctl -u qbi-build.service` after the first timed run.

### Carried over from the pre-refactor deployment

Recovered from the v0.4.0 history that was on GitHub (the March 2026 work, now
preserved on the `legacy/pre-refactor-main` branch). This refactor branched
before it, so none of it is encoded here — and it cannot be, because the MyST
service unit itself does not live in this repo. Both were learned the hard way
on the running server:

- [ ] **Do not pass `--headless` to `myst start`.** As of MyST v1.8.0 the flag
      makes it silently skip starting the app server. The unit looks healthy
      and the site does not serve.
- [ ] **Empty or truncated `.ipynb` files put MyST into an infinite rebuild
      loop.** The watcher fails to parse, retries, and spins. `qbi audit` now
      reports malformed notebooks, so clear them *before* the first build
      rather than debugging a pegged CPU afterwards — section 4 lists two
      known ones in the biology LA vault.

### The paths under `deploy/` are placeholders

`/srv/qbi` is a stand-in throughout this repo, including every file in
`deploy/`. The real root lives only in `build_config.yml`. Substitute it in the
copies you install, not in the repo:

- [ ] `qbi-build.service`: `ExecStart=` and the `Environment=` lines for
      `QBI_REPO`, `QBI_CONFIG` and `QBI_STAGING` all need the real paths.
      A wrong `ExecStart` fails instantly with a terse "No such file or
      directory" that reads like a broken script.
- [ ] `QBI_MYST_SERVICE` is a unit name, not a path. Confirmed 2026-08-25 as
      `myst-eln`, which is now the default in `qbi-build.sh`. The script
      verifies the unit exists and aborts if it does not, so a wrong name
      fails loudly instead of quietly syncing under a running server.

Things worth knowing before you start, all covered in `deploy/README.md`: the
unit runs as root to control the MyST service (there is a narrower sudoers
option), overlapping runs are prevented by `flock`, MyST restarts from an `EXIT`
trap so the site comes back even on a failed build, and recovery is
`git reset --hard HEAD~1` in staging followed by a MyST restart.

---

## 3. Audit the remaining vaults

You have run `qbi audit` on `research-biology-la` only. Do the rest before they
are published — the audit is cheap, reads nothing confidential, and reports
things the build cannot.

```bash
qbi audit /srv/qbi --all -d reports/
```

Confidential folders and `.qbi-exclude` subtrees are never scanned or named, so
these reports are safe to share with the teams that own the content.

- [ ] Run it across all vaults
- [ ] Hand each team its own report

Expect the same classes of problem this vault had — in particular the name
collision, which is silent data loss and worth checking for everywhere.

---

## 4. Content issues to hand back to the biology LA team

Found by running the audit on their vault. None are pipeline bugs; all are
things only they can fix.

- [ ] **Two files differ only by a space, and one of them is not published.**
      `Aer-PAS-domain_reference_3mutations_to order.dna` and
      `..._to_order.dna` both sanitize to the same staged filename. The build
      now warns and keeps one deterministically, but they should delete or
      rename whichever is the stray.
- [ ] **Two notebooks are malformed** and have been silently absent from the
      site. `full_exp_MF_on_first.ipynb` in
      `bacterioscope/3_code_bacterioscope/Operation_test/` is one. Re-save from
      Jupyter or delete.
- [ ] **`EXPERIMENTAL_PROTOCOL.md` has two stale heading links** in its own
      contents list — `[[#6. Step 2 — Degauss...]]` where the heading is now
      numbered `## 5.` Someone renumbered and two links kept the old numbers.
      These are broken in Obsidian too, not just on the site.
- [ ] **One unterminated image link** in `ELN - Bacterioscope experiment log.md`
      — missing its closing `)`, so the whole `![...](app://...` renders as
      literal text on the page.
- [ ] ~52 pasted images with default names, and 6 near-empty files. Cosmetic,
      but the audit lists them with checkboxes if anyone wants to work through
      it.

---

## 5. Known-open, deliberately deferred

Not bugs. Decisions taken with reasons, recorded so they are not rediscovered
as surprises.

- **Naming rules fail open.** A folder called `Confidential` publishes unless it
  is renamed `5_*` or marked with `.qbi-exclude`. Closing this properly needs
  content scanning, which you deferred. The current controls are conventions,
  and conventions need people to know them — worth a line in whatever onboarding
  the researchers get.
- **Logging is `print`-based.** Structured logging was deprioritized because
  journald timestamps stdout under systemd, so the practical gap is small.
  Revisit if you ever want machine-readable build logs.
- **Single-vault mode has no display-name overrides.** `qbi build src out` takes
  no config, and `display_names` lives in the config. Multi-vault is unaffected.
- **Date prefixes now stay in page titles.** `20250918_rampdown.md` titles as
  "20250918 Rampdown" rather than "Rampdown". Deliberate — the greedy strip
  collapsed a folder of date-distinguished entries into one repeated nav title —
  but it is a one-line change in `ORDERING_PREFIX` (`naming.py`) if you dislike
  how it reads.

---

## 6. Ideas, not commitments

Raised in passing and never started. Listed so they are not lost.

- Inline STL viewer for `.stl` models
- In-browser rendering for `.dna` plasmid maps and `.aln` alignments
- OCR/HTR for handwritten lab notebook scans — needs handwriting recognition
  rather than classical OCR, plus a human review step
- LaTeX source sharing for micropublications
- **Provenance history for the ELNs: Syncthing plus commits on a timer.**
  Syncthing gives each scientist a local replica of their vault; a timer then
  commits each vault hourly, or at end of day, so there is a record of when
  every section changed.

  Deliberately *not* the Obsidian Git plugin, and deliberately no human in the
  commit loop. Anything that depends on a researcher remembering to commit or
  push does not happen — that is an observation about how people actually work,
  not a complaint about them.

  This must live outside this pipeline. The build never writes to a vault, and
  that invariant is the reason it is safe to run unattended against the research
  share: a wrong path can cost you staging, never someone's data. Vault-side
  commits need their own mechanism on their own schedule.

  Two things that already work in our favour when a vault becomes a git repo:
  `.git` is in `EXCLUDED_DIRS` (`policy.py`), and Syncthing's `.stfolder` /
  `.stversions` / `.stignore` all begin with `.`, which `EXCLUDED_PREFIXES`
  excludes. So neither the repo metadata nor the sync metadata reaches the site
  without any change here.

---

## Reference: local development

```bash
pip install -e ".[dev]"
pytest                  # 341 tests
ruff check src tests

qbi build --config local_test_config.yml     # gitignored; real vault copy
cd _build_staging && myst start
```

`local_test_config.yml` and any vault copy in the repo are gitignored
(`/research-*/`, `/_vaults/`, `/*_vault/`). Keep it that way — a vault must
never be committed.

When adding acronyms that display wrong in titles, `ACRONYMS` in
`src/qbi_pipeline/naming.py` is the lowercase-word table; exact folder names go
in `display_names` in the build config.
