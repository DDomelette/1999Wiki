#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
DEPLOY_ROOT="${DEPLOY_ROOT:-/srv/1999wiki}"
RELEASES_DIR="${RELEASES_DIR:-$DEPLOY_ROOT/releases}"
APP_COMPOSE_FILE="${APP_COMPOSE_FILE:-$REPO_ROOT/deploy/compose.app.yml}"
APP_ENV_FILE="${APP_ENV_FILE:-$DEPLOY_ROOT/protected/app.env}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-http://127.0.0.1}"
HEALTH_ATTEMPTS="${HEALTH_ATTEMPTS:-30}"
HEALTH_INTERVAL_SECONDS="${HEALTH_INTERVAL_SECONDS:-5}"

die() {
    printf 'deploy: %s\n' "$*" >&2
    exit 1
}

[[ "$#" -eq 2 ]] || die "usage: ${0##*/} sha-<7 lowercase hex> <blue|green>"
RELEASE="$1"
SLOT="$2"
RELEASE_ENV_FILE="${RELEASE_ENV_FILE:-$RELEASES_DIR/$RELEASE/$SLOT.env}"
PROJECT="1999wiki-$SLOT"

"$SCRIPT_DIR/preflight.sh" "$RELEASE" "$SLOT"

mapfile -t release_values < <(
    python3 - "$RELEASE_ENV_FILE" <<'PY'
import sys

wanted = ("BACKEND_IMAGE", "FRONTEND_IMAGE", "FRONTEND_PORT")
values = {}
with open(sys.argv[1], encoding="utf-8") as stream:
    for raw_line in stream:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if separator and key in wanted:
            values[key] = value.strip()
for key in wanted:
    print(values[key])
PY
)
[[ "${#release_values[@]}" -eq 3 ]] || die "validated release metadata is incomplete"
BACKEND_IMAGE="${release_values[0]}"
FRONTEND_IMAGE="${release_values[1]}"
FRONTEND_PORT="${release_values[2]}"
CANDIDATE_BASE_URL="http://127.0.0.1:$FRONTEND_PORT"
export APP_ENV_FILE

compose() {
    docker compose \
        -p "$PROJECT" \
        --env-file "$RELEASE_ENV_FILE" \
        -f "$APP_COMPOSE_FILE" \
        "$@"
}

TMP_DIR="$(mktemp -d)"
candidate_started=false
switched=false
cleanup() {
    local status=$?
    trap - EXIT
    if (( status != 0 )) && [[ "$candidate_started" == "true" && "$switched" == "false" ]]; then
        compose stop backend frontend >/dev/null 2>&1 || true
    fi
    rm -rf -- "$TMP_DIR"
    exit "$status"
}
trap cleanup EXIT

wait_for_candidate() {
    local attempt
    for ((attempt = 1; attempt <= HEALTH_ATTEMPTS; attempt++)); do
        if compose ps --format json backend frontend >"$TMP_DIR/compose-status.json" 2>/dev/null \
            && python3 - "$TMP_DIR/compose-status.json" <<'PY'
import json
import pathlib
import sys

raw = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").strip()
try:
    rows = json.loads(raw)
    if isinstance(rows, dict):
        rows = [rows]
except json.JSONDecodeError:
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
services = {
    str(row.get("Service")): row
    for row in rows
    if isinstance(row, dict) and row.get("Service")
}
if set(services) != {"backend", "frontend"}:
    raise SystemExit(1)
if any(
    row.get("State") != "running" or row.get("Health") != "healthy"
    for row in services.values()
):
    raise SystemExit(1)
PY
        then
            if curl \
                --silent \
                --show-error \
                --fail \
                --connect-timeout 3 \
                --max-time 10 \
                --output "$TMP_DIR/candidate-health.json" \
                "$CANDIDATE_BASE_URL/health" \
                && python3 - "$TMP_DIR/candidate-health.json" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
expected = {
    "status": "ok",
    "vectorstore_loaded": True,
    "provenance_status": "pass",
    "llm_ready": True,
}
if any(payload.get(key) != value for key, value in expected.items()):
    raise SystemExit(1)
PY
            then
                return 0
            fi
        fi
        if (( attempt < HEALTH_ATTEMPTS )); then
            sleep "$HEALTH_INTERVAL_SECONDS"
        fi
    done
    return 1
}

docker pull "$BACKEND_IMAGE"
docker pull "$FRONTEND_IMAGE"
compose up -d --no-build --pull never backend frontend
candidate_started=true

wait_for_candidate || die "candidate did not become healthy within the bounded wait"
"$SCRIPT_DIR/smoke-test.sh" "$CANDIDATE_BASE_URL" "$PUBLIC_BASE_URL"
"$SCRIPT_DIR/switch.sh" "$RELEASE" "$SLOT" "$FRONTEND_PORT"
switched=true

printf 'deployed %s to %s\n' "$RELEASE" "$SLOT"
