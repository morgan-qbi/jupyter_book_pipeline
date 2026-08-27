#!/usr/bin/env bash
#
# Rebuild the ELN site and restart MyST only if something actually changed.
#
# Intended to be driven by qbi-build.timer (systemd) rather than run by hand.
# See deploy/README.md for first-run setup, which is NOT optional -- the build
# refuses to adopt an existing staging directory without a marker file.

set -euo pipefail

REPO="${QBI_REPO:-/srv/qbi/jupyter-book-pipeline}"
CONFIG="${QBI_CONFIG:-$REPO/build_config.yml}"
STAGING="${QBI_STAGING:-/srv/qbi/_build_staging}"
SERVICE="${QBI_MYST_SERVICE:-myst-eln}"
VENV="${QBI_VENV:-$REPO/venv}"
LOCK="${QBI_LOCK:-/var/lock/qbi-build.lock}"

# The build runs as root while the staging repo is owned by the service
# account, which trips git's dubious-ownership guard and makes every git
# command in staging fail. Declare the directory trusted for these invocations
# only, rather than mutating root's global gitconfig -- the fix then travels
# with the script instead of living undocumented on one machine.
GIT_STAGING=(git -C "$STAGING" -c "safe.directory=$STAGING")

# A daemon has no git identity of its own, and git refuses to commit without
# one. The snapshot is the rollback mechanism, so it must not depend on
# whatever `git config --global` happens to say for the user running the unit.
COMMIT_NAME="${QBI_COMMIT_NAME:-QBI build}"
COMMIT_EMAIL="${QBI_COMMIT_EMAIL:-qbi-build@localhost}"

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
    [ -n "$("${GIT_STAGING[@]}" status --porcelain)" ]
}

# `systemctl is-active` answers "no" both for a stopped service and for one
# that does not exist, and those need opposite responses. Left conflated, a
# typo in QBI_MYST_SERVICE reads as "not running", so the build never stops
# the server, syncs underneath it with the watcher live, and reports success.
# Resolve the unit up front instead -- before the EXIT trap is armed, so a
# bad name cannot leave a half-handled service behind.
if [ "$(systemctl show -p LoadState --value "$SERVICE.service" 2>/dev/null)" != "loaded" ]; then
    log "FATAL: no systemd unit named $SERVICE.service"
    log "       Set QBI_MYST_SERVICE to the real MyST unit name."
    log "       Refusing to sync: an unstopped server would be served a"
    log "       half-written site and its watcher would thrash."
    exit 1
fi

# Same absent-vs-inactive trap as the service check, one layer down: a git
# command that fails prints nothing to stdout, so `staging_dirty` reads the
# error as "nothing changed" and quietly skips the snapshot. The build looks
# clean and the rollback point silently never exists. Check that git actually
# works here while nothing has been stopped yet.
if [ -d "$STAGING/.git" ]; then
    if ! git_check="$("${GIT_STAGING[@]}" status --porcelain 2>&1)"; then
        log "FATAL: git cannot operate in $STAGING"
        while IFS= read -r line; do log "       $line"; done <<< "$git_check"
        log "       The staging snapshot is what makes a bad build revertable."
        log "       Refusing to build without it."
        exit 1
    fi
fi

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
        "${GIT_STAGING[@]}" add -A
        # `|| true` used to swallow this. A commit fails for reasons that
        # matter -- no identity, no disk, a stale lock -- and losing the
        # rollback point silently is the exact failure this script keeps
        # walking into. Say so instead.
        if "${GIT_STAGING[@]}" -c "user.name=$COMMIT_NAME" -c "user.email=$COMMIT_EMAIL" commit -q -m "site rebuild $(date -Is)"; then
            log "committed staging snapshot"
        else
            log "WARNING: staging snapshot commit failed -- this build has no"
            log "         rollback point. The published site itself is fine."
        fi
    fi
else
    log "no changes; site is already current"
fi

log "done"
