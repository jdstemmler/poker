#!/usr/bin/env bash
# auto-deploy.sh — Polls GitHub for new commits on main and rebuilds via Docker Compose.
#
# Usage:
#   REPO_DIR=/path/to/poker-game ./auto-deploy.sh
#
# Environment variables:
#   REPO_DIR          — Path to the cloned repo (required)
#   BRANCH            — Branch to track (default: main)
#   POLL_INTERVAL     — Seconds between checks (default: 60)
#   COMPOSE_PROFILES  — Optional Docker Compose profiles

set -euo pipefail

REPO_DIR="${REPO_DIR:?REPO_DIR must be set}"
BRANCH="${BRANCH:-main}"
POLL_INTERVAL="${POLL_INTERVAL:-60}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

cd "$REPO_DIR"

log "Auto-deploy started — watching '$BRANCH' every ${POLL_INTERVAL}s"
log "Repo: $REPO_DIR"

while true; do
    # Fetch latest from origin (quiet, no merge)
    if ! git fetch origin "$BRANCH" --quiet 2>/dev/null; then
        log "WARNING: git fetch failed, will retry"
        sleep "$POLL_INTERVAL"
        continue
    fi

    LOCAL=$(git rev-parse "$BRANCH" 2>/dev/null || echo "none")
    REMOTE=$(git rev-parse "origin/$BRANCH" 2>/dev/null || echo "none")

    if [ "$LOCAL" != "$REMOTE" ]; then
        log "New commits detected: $LOCAL -> $REMOTE"

        # Pull changes
        if git pull origin "$BRANCH" --ff-only; then
            log "Pull successful, rebuilding containers..."

            # Rebuild and restart — pull fresh base images too
            if docker compose up --build --force-recreate -d; then
                # Prune old images to save disk space
                docker image prune -f --filter "until=24h" >/dev/null 2>&1 || true
                log "Deploy complete: $(git log --oneline -1)"
            else
                log "ERROR: docker compose up failed!"
            fi
        else
            log "ERROR: git pull failed (possible divergence). Manual intervention needed."
        fi
    fi

    sleep "$POLL_INTERVAL"
done
