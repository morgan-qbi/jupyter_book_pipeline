# Running the pipeline on Frida

The build is incremental: it writes only files that changed and prunes files
that no longer exist in a vault. An unchanged vault costs one pass over the
file tree and writes nothing, so it is cheap to run on a timer.

## First run — read this, it will fail otherwise

**1. The build refuses to adopt an existing staging directory.**

`_build_staging` already has content and no `.qbi-staging` marker, so the very
first run will stop with *"Refusing to use ... it is not empty and has no
.qbi-staging marker"*. That guard exists because sync prunes files it considers
stale, and pointing `output:` at a real data directory would otherwise delete
it. Claim the directory once:

```bash
touch /mnt/raid-storage/shared/_build_staging/.qbi-staging
```

**2. The first build will be a large diff.** Behavior changed: page titles,
link resolution, TIFF→PNG conversion, and an allow-list that publishes only
permitted file types. Anything already in staging that is no longer publishable
gets pruned. Make that reviewable and revertable:

```bash
cd /mnt/raid-storage/shared/_build_staging
cp /mnt/raid-storage/shared/jupyter-book-pipeline/deploy/staging.gitignore .gitignore
git init && git add -A && git commit -m "site as it stands before the pipeline refactor"
```

**3. Look before you leap.** `--dry-run` writes nothing and prints the
extension census for every vault:

```bash
qbi build --config build_config.yml --dry-run
```

Read the SKIPPED lines. Anything there that belongs on the site goes in
`publish_extensions` in the build config. The build also warns, by page and by
target, whenever a page links to a file the allow-list skipped.

## Install

```bash
cd /mnt/raid-storage/shared/jupyter-book-pipeline
venv/bin/pip install -e .          # provides the `qbi` command
venv/bin/qbi build --config build_config.yml --dry-run
```

## Schedule it

```bash
cp deploy/qbi-build.service deploy/qbi-build.timer /etc/systemd/system/
chmod +x deploy/qbi-build.sh
systemctl daemon-reload
systemctl enable --now qbi-build.timer

systemctl list-timers qbi-build.timer     # when it next fires
journalctl -u qbi-build.service -f        # what it did
systemctl start qbi-build.service         # run one now
```

A systemd timer is preferred over crontab here because the job needs to
`systemctl stop/start` the MyST unit, so it has to run somewhere that can talk
to systemd, and because `journalctl -u` gives you the build log for free.

## Why it stops MyST

`myst start` serves and watches. Sync writes files one at a time, so a running
server can serve a half-updated site, and the watcher thrashes rebuilding on
every individual write. Stopping first avoids both. Downtime is proportional to
what changed, which on a normal day is a handful of files.

`qbi-build.sh` restarts MyST from an `EXIT` trap, so the site comes back even if
the build fails — a stale site beats no site.

## Things that would otherwise catch you out

**MyST's `_build/` is never touched.** The pipeline preserves anything at the
staging root beginning with `_` or `.`, so `_build/`, `_static/` and `.git/`
survive pruning. This matters more than it sounds: `_build/templates/.../
node_modules` is held open by a running `myst start`, and deleting it under a
live process is how you get a corrupted cache and a full re-download.

**Overlapping runs.** `qbi-build.sh` takes an `flock`. If a build overruns the
timer interval, the next firing exits immediately rather than writing into the
same tree.

**Restart only on change.** The script asks git whether staging actually
changed and skips the MyST restart if not — which is why the staging
`.gitignore` matters. Without it, `_build/` churn makes every run look dirty.

**Exit codes.** Failures exit non-zero, so `systemctl status qbi-build` and
`journalctl` show a failed unit rather than a silent success.

**Permissions.** The unit runs as root to control the MyST service. If you would
rather not, run it as the service account and grant a narrow sudoers rule:

```
qbi ALL=(root) NOPASSWD: /bin/systemctl stop myst, /bin/systemctl start myst
```

then prefix the two `systemctl` calls in `qbi-build.sh` with `sudo`.

**Vault permissions.** The build needs read on every vault and write on
staging. It never modifies a vault — sources are only ever read.

## Recovering

Staging is a git repo and the pipeline never touches `.git`, so a bad build is
recoverable:

```bash
cd /mnt/raid-storage/shared/_build_staging
git log --oneline
git diff HEAD~1                 # what the last build changed
git reset --hard HEAD~1         # roll the site back
systemctl restart myst
```
