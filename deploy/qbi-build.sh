#!/usr/bin/env bash
#
# Rebuild the ELN site and restart MyST only if something actually changed.
#
# Intended to be driven by qbi-build.timer (systemd) rather than run by hand.
# See deploy/README.md for first-run setup, which is NOT optional -- the build
# refuses to adopt an existing staging directory without a marker file.

set -euo pipefail

REPO="${QBI_REPO:-/mnt/raid-storage/shared/jupyter-book-pipeline}"
CONFIG="${QBI_CONFIG:-$REPO/build_config.yml}"
STAGING="${QBI_STAGING:-/mnt/raid-storage/shared/_build_staging}"
SERVICE="${QBI_MYST_SERVICE:-myst}"
VENV="${QBI_VENV:-$REPO/venv}"
LOCK="${QBI_LOCK:-/var/lock/qbi-build.lock}"

log() { printf '%s  %s\n' "$(date -Is)" "$*"; }

# A build over a large vault takes minutes. Without a lock, a timer firing on a
# short interval will start a second build on top of the first, and both will
# write to the same staging tree.
exec 9>"$LOCK"
if ! flock -n 9; then
    log "another build is already running; exiting"
    exit 0
fi

staging_dirty() {
    # Staging is a git repo, so git itself is the change detector. Anything
    # MyST generates lives under _build/, which staging/.gitignore excludes.
    [ -d "$STAGING/.git" ] || return 0          # not a repo: assume changed
    [ -n "$(git -C "$STAGING" status --porcelain)" ]
}

log "starting build"

# Stop MyST first. Sync writes files one at a time, so a running server could
# otherwise serve a half-updated site, and MyST's file watcher would thrash
# rebuilding on every individual write.
if systemctl is-active --quiet "$SERVICE"; then
    log "stopping $SERVICE"
    systemctl stop "$SERVICE"
    STARTED_STOPPED=1
else
    log "$SERVICE was not running"
    STARTED_STOPPED=0
fi

# Always bring MyST back, even if the build fails: a stale site beats no site.
restart_myst() {
    if [ "$STARTED_STOPPED" = "1" ]; then
        log "starting $SERVICE"
        systemctl start "$SERVICE"
    fi
}
trap restart_myst EXIT

log "syncing vaults"
if ! "$VENV/bin/qbi" build --config "$CONFIG"; then
    log "BUILD FAILED - leaving staging as-is and restarting $SERVICE"
    exit 1
fi

if staging_dirty; then
    log "changes detected"
    if [ -d "$STAGING/.git" ]; then
        git -C "$STAGING" add -A
        git -C "$STAGING" commit -q -m "site rebuild $(date -Is)" || true
        log "committed staging snapshot"
    fi
else
    log "no changes; site is already current"
fi

log "done"
