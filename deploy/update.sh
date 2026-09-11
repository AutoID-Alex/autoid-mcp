#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/home/autoidtes45/autoid-mcp"
SERVICE="autoid-mcp.service"
TEST_PORT="3001"
LOCAL_READY="http://127.0.0.1:3000/ready"
TEST_READY="http://127.0.0.1:${TEST_PORT}/ready"
PUBLIC_READY="https://mcp.autoid.ro/ready"
TEST_LOG="/tmp/autoid-mcp-deploy-test.log"

OLD_COMMIT=""
TEST_PID=""

log() {
  printf '[deploy] %s\n' "$*"
}

cleanup_test() {
  if [[ -n "${TEST_PID}" ]] && kill -0 "${TEST_PID}" 2>/dev/null; then
    kill "${TEST_PID}" 2>/dev/null || true
    wait "${TEST_PID}" 2>/dev/null || true
  fi
}

wait_ready() {
  local url="$1"
  local attempts="${2:-20}"
  local delay="${3:-1}"
  local i

  for ((i = 1; i <= attempts; i++)); do
    if curl -fsS --max-time 5 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$delay"
  done
  return 1
}

rollback() {
  local failed_line="$1"
  trap - ERR
  set +e
  cleanup_test

  printf '\n[deploy] ERROR at line %s. Rolling back to %s\n' "$failed_line" "${OLD_COMMIT:-unknown}" >&2

  if [[ -n "${OLD_COMMIT}" ]]; then
    cd "$ROOT" || exit 1
    git reset --hard "$OLD_COMMIT"
    npm ci
    npm run build

    local current_pid
    current_pid="$(systemctl show -p MainPID --value "$SERVICE" 2>/dev/null)"
    if [[ "$current_pid" =~ ^[1-9][0-9]*$ ]]; then
      kill "$current_pid" 2>/dev/null || true
    fi

    if wait_ready "$LOCAL_READY" 30 1; then
      log "Rollback successful. MCP is healthy on the previous commit."
    else
      printf '[deploy] CRITICAL: rollback completed on disk, but MCP is not healthy.\n' >&2
      systemctl status "$SERVICE" --no-pager -l >&2 || true
    fi
  fi

  exit 1
}

trap 'rollback "$LINENO"' ERR
trap cleanup_test EXIT

cd "$ROOT"

if [[ ! -d .git ]]; then
  printf '[deploy] ERROR: %s is not a Git checkout.\n' "$ROOT" >&2
  exit 1
fi

if [[ "$(git branch --show-current)" != "main" ]]; then
  printf '[deploy] ERROR: production checkout must be on main.\n' >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  printf '[deploy] ERROR: working tree is not clean. Commit, move, or remove local files first.\n' >&2
  git status --short >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  printf '[deploy] ERROR: %s/.env is missing.\n' "$ROOT" >&2
  exit 1
fi

OLD_COMMIT="$(git rev-parse HEAD)"
log "Current commit: $OLD_COMMIT"

log "Fetching origin/main..."
git fetch origin main
TARGET_COMMIT="$(git rev-parse origin/main)"
log "Target commit:  $TARGET_COMMIT"

if [[ "$OLD_COMMIT" == "$TARGET_COMMIT" ]]; then
  log "Already up to date. Nothing to deploy."
  exit 0
fi

if ! git merge-base --is-ancestor "$OLD_COMMIT" "$TARGET_COMMIT"; then
  printf '[deploy] ERROR: origin/main is not a fast-forward from the current production commit.\n' >&2
  exit 1
fi

log "Fast-forwarding production checkout..."
git merge --ff-only origin/main

log "Installing exact dependencies..."
npm ci

log "Running TypeScript check..."
npm run check

log "Building production bundle..."
npm run build

log "Starting pre-deploy test on 127.0.0.1:${TEST_PORT}..."
rm -f "$TEST_LOG"
(
  set -a
  . "$ROOT/.env"
  set +a
  exec env PORT="$TEST_PORT" node "$ROOT/dist/server.js"
) >"$TEST_LOG" 2>&1 &
TEST_PID="$!"

if ! wait_ready "$TEST_READY" 20 1; then
  cat "$TEST_LOG" >&2 || true
  false
fi
log "Pre-deploy readiness check passed."
cleanup_test
TEST_PID=""

OLD_PID="$(systemctl show -p MainPID --value "$SERVICE")"
if [[ ! "$OLD_PID" =~ ^[1-9][0-9]*$ ]]; then
  printf '[deploy] ERROR: could not determine the running systemd MainPID.\n' >&2
  false
fi

log "Triggering systemd restart by terminating PID $OLD_PID..."
kill "$OLD_PID"

if ! wait_ready "$LOCAL_READY" 30 1; then
  systemctl status "$SERVICE" --no-pager -l >&2 || true
  false
fi

NEW_PID="$(systemctl show -p MainPID --value "$SERVICE")"
if [[ "$NEW_PID" == "$OLD_PID" || ! "$NEW_PID" =~ ^[1-9][0-9]*$ ]]; then
  printf '[deploy] ERROR: systemd did not replace the MCP process as expected.\n' >&2
  false
fi

log "Local production readiness passed. New PID: $NEW_PID"

if wait_ready "$PUBLIC_READY" 5 2; then
  log "Public readiness passed: $PUBLIC_READY"
else
  log "WARNING: local MCP is healthy, but the public readiness endpoint did not answer successfully."
fi

log "Deployment successful: $(git rev-parse --short HEAD)"
