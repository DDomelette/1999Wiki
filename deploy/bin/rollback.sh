#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
DEPLOY_ROOT="${DEPLOY_ROOT:-/srv/1999wiki}"
STATE_DIR="${STATE_DIR:-$DEPLOY_ROOT/deploy-state}"
APP_COMPOSE_FILE="${APP_COMPOSE_FILE:-$REPO_ROOT/deploy/compose.app.yml}"
APP_ENV_FILE="${APP_ENV_FILE:-$DEPLOY_ROOT/protected/app.env}"
CADDY_CONFIG="${CADDY_CONFIG:-/etc/caddy/Caddyfile}"
CADDY_ENV_FILE="${CADDY_ENV_FILE:-$DEPLOY_ROOT/protected/caddy.env}"
CADDY_IMPORT_PATH="${CADDY_IMPORT_PATH:-/etc/caddy/active-upstream.caddy}"
ACTIVE_FRAGMENT="${ACTIVE_FRAGMENT:-/etc/caddy/active-upstream.caddy}"
ACTIVE_STATE_FILE="${ACTIVE_STATE_FILE:-$STATE_DIR/active.env}"
PRIOR_FRAGMENT="${PRIOR_FRAGMENT:-$STATE_DIR/previous-upstream.caddy}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-http://127.0.0.1}"
VERIFY_ATTEMPTS="${VERIFY_ATTEMPTS:-6}"
VERIFY_INTERVAL_SECONDS="${VERIFY_INTERVAL_SECONDS:-2}"

die() {
    printf 'rollback: %s\n' "$*" >&2
    exit 1
}

[[ "$#" -eq 0 ]] || die "usage: ${0##*/}"
for required_file in \
    "$ACTIVE_STATE_FILE" \
    "$PRIOR_FRAGMENT" \
    "$ACTIVE_FRAGMENT" \
    "$CADDY_CONFIG" \
    "$CADDY_ENV_FILE" \
    "$APP_COMPOSE_FILE" \
    "$APP_ENV_FILE"; do
    [[ -f "$required_file" ]] || die "required file is missing: $required_file"
done
[[ -d "$STATE_DIR" ]] || die "deployment state directory is missing"

mapfile -t state_values < <(
    python3 - "$ACTIVE_STATE_FILE" "$PRIOR_FRAGMENT" <<'PY'
import re
import sys

wanted = (
    "ACTIVE_SLOT",
    "ACTIVE_RELEASE",
    "ACTIVE_PROJECT",
    "ACTIVE_FRONTEND_PORT",
    "ACTIVE_RELEASE_ENV_FILE",
    "PREVIOUS_SLOT",
    "PREVIOUS_RELEASE",
    "PREVIOUS_PROJECT",
    "PREVIOUS_FRONTEND_PORT",
    "PREVIOUS_RELEASE_ENV_FILE",
    "PRIOR_FRAGMENT",
)
values = {}
with open(sys.argv[1], encoding="utf-8") as stream:
    for raw_line in stream:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key in values:
            raise SystemExit("rollback: malformed active state")
        values[key] = value
if not all(values.get(key) for key in wanted):
    raise SystemExit("rollback: no complete previous deployment is recorded")
for prefix in ("ACTIVE", "PREVIOUS"):
    slot = values[f"{prefix}_SLOT"]
    release = values[f"{prefix}_RELEASE"]
    project = values[f"{prefix}_PROJECT"]
    port = values[f"{prefix}_FRONTEND_PORT"]
    if slot not in {"blue", "green"} or project != "1999wiki-" + slot:
        raise SystemExit(f"rollback: {prefix.lower()} slot state is invalid")
    if not re.fullmatch(r"sha-[0-9a-f]{7}", release):
        raise SystemExit(f"rollback: {prefix.lower()} release state is invalid")
    if not port.isdecimal() or not 1024 <= int(port) <= 65535:
        raise SystemExit(f"rollback: {prefix.lower()} port state is invalid")
if values["ACTIVE_SLOT"] == values["PREVIOUS_SLOT"]:
    raise SystemExit("rollback: active and previous slots must differ")
if values["PRIOR_FRAGMENT"] != sys.argv[2]:
    raise SystemExit("rollback: recorded prior fragment path is unexpected")
for key in wanted:
    print(values[key])
PY
)
ACTIVE_SLOT="${state_values[0]}"
ACTIVE_RELEASE="${state_values[1]}"
ACTIVE_PROJECT="${state_values[2]}"
ACTIVE_FRONTEND_PORT="${state_values[3]}"
ACTIVE_RELEASE_ENV_FILE="${state_values[4]}"
PREVIOUS_SLOT="${state_values[5]}"
PREVIOUS_RELEASE="${state_values[6]}"
PREVIOUS_PROJECT="${state_values[7]}"
PREVIOUS_FRONTEND_PORT="${state_values[8]}"
PREVIOUS_RELEASE_ENV_FILE="${state_values[9]}"
RECORDED_PRIOR_FRAGMENT="${state_values[10]}"
[[ "$RECORDED_PRIOR_FRAGMENT" == "$PRIOR_FRAGMENT" ]] \
    || die "recorded prior fragment mismatch"
[[ -f "$PREVIOUS_RELEASE_ENV_FILE" ]] || die "previous release metadata is missing"
[[ -f "$ACTIVE_RELEASE_ENV_FILE" ]] || die "active release metadata is missing"
[[ "$PREVIOUS_RELEASE_ENV_FILE" != *.example ]] \
    || die "previous release metadata must not be a checked example"

mapfile -t caddy_values < <(
    python3 - "$CADDY_ENV_FILE" <<'PY'
import sys

wanted = ("SITE_ADDRESS", "MINIO_PROXY_UPSTREAM")
values = {}
with open(sys.argv[1], encoding="utf-8") as stream:
    for raw_line in stream:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if separator and key in wanted:
            if key in values or not value.strip():
                raise SystemExit("rollback: invalid Caddy environment")
            values[key] = value.strip()
if set(values) != set(wanted):
    raise SystemExit("rollback: incomplete Caddy environment")
for key in wanted:
    print(values[key])
PY
)
SITE_ADDRESS="${caddy_values[0]}"
MINIO_PROXY_UPSTREAM="${caddy_values[1]}"
export SITE_ADDRESS MINIO_PROXY_UPSTREAM APP_ENV_FILE

previous_compose() {
    docker compose \
        -p "$PREVIOUS_PROJECT" \
        --env-file "$PREVIOUS_RELEASE_ENV_FILE" \
        -f "$APP_COMPOSE_FILE" \
        "$@"
}

active_compose() {
    docker compose \
        -p "$ACTIVE_PROJECT" \
        --env-file "$ACTIVE_RELEASE_ENV_FILE" \
        -f "$APP_COMPOSE_FILE" \
        "$@"
}

verify_health_url() {
    local base_url="$1"
    local output="$2"
    local attempt
    for ((attempt = 1; attempt <= VERIFY_ATTEMPTS; attempt++)); do
        if curl \
            --silent \
            --show-error \
            --fail \
            --connect-timeout 3 \
            --max-time 10 \
            --output "$output" \
            "$base_url/health" \
            && python3 - "$output" <<'PY'
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
        if (( attempt < VERIFY_ATTEMPTS )); then
            sleep "$VERIFY_INTERVAL_SECONDS"
        fi
    done
    return 1
}

CADDY_DIR="$(dirname -- "$ACTIVE_FRAGMENT")"
RESTORE_TMP="$(mktemp "$CADDY_DIR/.active-upstream.rollback.XXXXXX")"
TEMP_CONFIG="$(mktemp "$CADDY_DIR/.Caddyfile.rollback.XXXXXX")"
CURRENT_FRAGMENT_TMP="$(mktemp "$STATE_DIR/.current-upstream.XXXXXX")"
PRIOR_PERSIST_TMP="$(mktemp "$STATE_DIR/.previous-upstream.persist.XXXXXX")"
STATE_TMP="$(mktemp "$STATE_DIR/.active-state.XXXXXX")"
CANDIDATE_HEALTH_TMP="$(mktemp "$STATE_DIR/.rollback-candidate-health.XXXXXX")"
PUBLIC_HEALTH_TMP="$(mktemp "$STATE_DIR/.rollback-public-health.XXXXXX")"
FRAGMENT_REPLACED=false
COMMITTED=false

restore_current_fragment() {
    local recovery_tmp
    recovery_tmp="$(mktemp "$CADDY_DIR/.active-upstream.recovery.XXXXXX")"
    cp -p "$CURRENT_FRAGMENT_TMP" "$recovery_tmp"
    mv -f "$recovery_tmp" "$ACTIVE_FRAGMENT"
    caddy reload --config "$CADDY_CONFIG" --adapter caddyfile >/dev/null
}

cleanup() {
    local status=$?
    trap - EXIT
    if (( status != 0 )) && [[ "$FRAGMENT_REPLACED" == "true" && "$COMMITTED" == "false" ]]; then
        set +e
        restore_current_fragment
        local restore_status=$?
        set -e
        if (( restore_status != 0 )); then
            printf 'rollback: CRITICAL: failed to restore the current Caddy fragment\n' >&2
        fi
    fi
    rm -f -- \
        "$RESTORE_TMP" \
        "$TEMP_CONFIG" \
        "$CURRENT_FRAGMENT_TMP" \
        "$PRIOR_PERSIST_TMP" \
        "$STATE_TMP" \
        "$CANDIDATE_HEALTH_TMP" \
        "$PUBLIC_HEALTH_TMP"
    exit "$status"
}
trap cleanup EXIT

previous_compose start backend frontend
verify_health_url \
    "http://127.0.0.1:$PREVIOUS_FRONTEND_PORT" \
    "$CANDIDATE_HEALTH_TMP" \
    || die "recorded previous app did not become healthy"

cp -p "$PRIOR_FRAGMENT" "$RESTORE_TMP"
python3 \
    - "$CADDY_CONFIG" "$TEMP_CONFIG" "$CADDY_IMPORT_PATH" "$RESTORE_TMP" <<'PY'
import pathlib
import sys

source_path, target_path, active_import, candidate_import = sys.argv[1:]
text = pathlib.Path(source_path).read_text(encoding="utf-8")
needle = f"import {active_import}"
if text.count(needle) != 1:
    raise SystemExit("rollback: Caddy config must contain exactly one active import")
pathlib.Path(target_path).write_text(
    text.replace(needle, f"import {candidate_import}", 1),
    encoding="utf-8",
)
PY
caddy validate --config "$TEMP_CONFIG" --adapter caddyfile >/dev/null

cp -p "$ACTIVE_FRAGMENT" "$CURRENT_FRAGMENT_TMP"
mv -f "$RESTORE_TMP" "$ACTIVE_FRAGMENT"
FRAGMENT_REPLACED=true
caddy reload --config "$CADDY_CONFIG" --adapter caddyfile >/dev/null
verify_health_url "$PUBLIC_BASE_URL" "$PUBLIC_HEALTH_TMP" \
    || die "public health verification failed after rollback"

cp -p "$CURRENT_FRAGMENT_TMP" "$PRIOR_PERSIST_TMP"
mv -f "$PRIOR_PERSIST_TMP" "$PRIOR_FRAGMENT"
{
    printf 'ACTIVE_SLOT=%s\n' "$PREVIOUS_SLOT"
    printf 'ACTIVE_RELEASE=%s\n' "$PREVIOUS_RELEASE"
    printf 'ACTIVE_PROJECT=%s\n' "$PREVIOUS_PROJECT"
    printf 'ACTIVE_FRONTEND_PORT=%s\n' "$PREVIOUS_FRONTEND_PORT"
    printf 'ACTIVE_RELEASE_ENV_FILE=%s\n' "$PREVIOUS_RELEASE_ENV_FILE"
    printf 'PREVIOUS_SLOT=%s\n' "$ACTIVE_SLOT"
    printf 'PREVIOUS_RELEASE=%s\n' "$ACTIVE_RELEASE"
    printf 'PREVIOUS_PROJECT=%s\n' "$ACTIVE_PROJECT"
    printf 'PREVIOUS_FRONTEND_PORT=%s\n' "$ACTIVE_FRONTEND_PORT"
    printf 'PREVIOUS_RELEASE_ENV_FILE=%s\n' "$ACTIVE_RELEASE_ENV_FILE"
    printf 'PRIOR_FRAGMENT=%s\n' "$PRIOR_FRAGMENT"
} >"$STATE_TMP"
chmod 600 "$STATE_TMP"
mv -f "$STATE_TMP" "$ACTIVE_STATE_FILE"
COMMITTED=true
FRAGMENT_REPLACED=false

if ! active_compose stop backend frontend; then
    printf 'rollback: warning: the replaced app slot could not be stopped\n' >&2
fi
printf 'rolled back to %s at %s\n' "$PREVIOUS_SLOT" "$PREVIOUS_RELEASE"
