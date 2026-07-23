#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
DEPLOY_ROOT="${DEPLOY_ROOT:-/srv/1999wiki}"
STATE_DIR="${STATE_DIR:-$DEPLOY_ROOT/deploy-state}"
RELEASES_DIR="${RELEASES_DIR:-$DEPLOY_ROOT/releases}"
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
    printf 'switch: %s\n' "$*" >&2
    exit 1
}

[[ "$#" -eq 3 ]] || die "usage: ${0##*/} sha-<7 lowercase hex> <blue|green> FRONTEND_PORT"
RELEASE="$1"
SLOT="$2"
FRONTEND_PORT="$3"
[[ "$RELEASE" =~ ^sha-[0-9a-f]{7}$ ]] || die "invalid release"
[[ "$SLOT" == "blue" || "$SLOT" == "green" ]] || die "invalid slot"
[[ "$FRONTEND_PORT" =~ ^[0-9]+$ ]] || die "invalid Frontend port"
(( FRONTEND_PORT >= 1024 && FRONTEND_PORT <= 65535 )) \
    || die "invalid Frontend port"
PROJECT="1999wiki-$SLOT"
RELEASE_ENV_FILE="${RELEASE_ENV_FILE:-$RELEASES_DIR/$RELEASE/$SLOT.env}"

for required_file in \
    "$CADDY_CONFIG" \
    "$CADDY_ENV_FILE" \
    "$ACTIVE_FRAGMENT" \
    "$APP_COMPOSE_FILE" \
    "$APP_ENV_FILE" \
    "$RELEASE_ENV_FILE"; do
    [[ -f "$required_file" ]] || die "required file is missing: $required_file"
done
[[ -d "$STATE_DIR" ]] || die "deployment state directory is missing"

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
                raise SystemExit("switch: invalid Caddy environment")
            values[key] = value.strip()
if set(values) != set(wanted):
    raise SystemExit("switch: incomplete Caddy environment")
for key in wanted:
    print(values[key])
PY
)
SITE_ADDRESS="${caddy_values[0]}"
MINIO_PROXY_UPSTREAM="${caddy_values[1]}"
export SITE_ADDRESS MINIO_PROXY_UPSTREAM APP_ENV_FILE

OLD_SLOT=
OLD_RELEASE=
OLD_PROJECT=
OLD_FRONTEND_PORT=
OLD_RELEASE_ENV_FILE=
if [[ -f "$ACTIVE_STATE_FILE" ]]; then
    mapfile -t old_values < <(
        python3 - "$ACTIVE_STATE_FILE" <<'PY'
import re
import sys

wanted = (
    "ACTIVE_SLOT",
    "ACTIVE_RELEASE",
    "ACTIVE_PROJECT",
    "ACTIVE_FRONTEND_PORT",
    "ACTIVE_RELEASE_ENV_FILE",
)
values = {}
with open(sys.argv[1], encoding="utf-8") as stream:
    for raw_line in stream:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key in values:
            raise SystemExit("switch: malformed active state")
        values[key] = value
if not all(values.get(key) for key in wanted):
    raise SystemExit("switch: active state is incomplete")
if values["ACTIVE_SLOT"] not in {"blue", "green"}:
    raise SystemExit("switch: active state slot is invalid")
if not re.fullmatch(r"sha-[0-9a-f]{7}", values["ACTIVE_RELEASE"]):
    raise SystemExit("switch: active state release is invalid")
if values["ACTIVE_PROJECT"] != "1999wiki-" + values["ACTIVE_SLOT"]:
    raise SystemExit("switch: active state project is invalid")
if not values["ACTIVE_FRONTEND_PORT"].isdecimal():
    raise SystemExit("switch: active state port is invalid")
for key in wanted:
    print(values[key])
PY
    )
    OLD_SLOT="${old_values[0]}"
    OLD_RELEASE="${old_values[1]}"
    OLD_PROJECT="${old_values[2]}"
    OLD_FRONTEND_PORT="${old_values[3]}"
    OLD_RELEASE_ENV_FILE="${old_values[4]}"
    [[ "$OLD_SLOT" != "$SLOT" ]] || die "refusing to switch the already-active slot"
fi

CADDY_DIR="$(dirname -- "$ACTIVE_FRAGMENT")"
TEMP_FRAGMENT="$(mktemp "$CADDY_DIR/.active-upstream.candidate.XXXXXX")"
TEMP_CONFIG="$(mktemp "$CADDY_DIR/.Caddyfile.candidate.XXXXXX")"
PRIOR_FRAGMENT_TMP="$(mktemp "$STATE_DIR/.previous-upstream.XXXXXX")"
PRIOR_PERSIST_TMP="$(mktemp "$STATE_DIR/.previous-upstream.persist.XXXXXX")"
STATE_TMP="$(mktemp "$STATE_DIR/.active-state.XXXXXX")"
FRAGMENT_REPLACED=false
COMMITTED=false

restore_previous_fragment() {
    local restore_tmp
    restore_tmp="$(mktemp "$CADDY_DIR/.active-upstream.restore.XXXXXX")"
    cp -p "$PRIOR_FRAGMENT_TMP" "$restore_tmp"
    mv -f "$restore_tmp" "$ACTIVE_FRAGMENT"
    caddy reload --config "$CADDY_CONFIG" --adapter caddyfile >/dev/null
}

cleanup() {
    local status=$?
    trap - EXIT
    if (( status != 0 )) && [[ "$FRAGMENT_REPLACED" == "true" && "$COMMITTED" == "false" ]]; then
        set +e
        restore_previous_fragment
        local restore_status=$?
        set -e
        if (( restore_status != 0 )); then
            printf 'switch: CRITICAL: failed to restore the prior Caddy fragment\n' >&2
        fi
    fi
    rm -f -- \
        "$TEMP_FRAGMENT" \
        "$TEMP_CONFIG" \
        "$PRIOR_FRAGMENT_TMP" \
        "$PRIOR_PERSIST_TMP" \
        "$STATE_TMP"
    exit "$status"
}
trap cleanup EXIT

verify_public_health() {
    local attempt
    local health_file="$STATE_DIR/.public-health.$$"
    trap 'rm -f -- "$health_file"' RETURN
    for ((attempt = 1; attempt <= VERIFY_ATTEMPTS; attempt++)); do
        if curl \
            --silent \
            --show-error \
            --fail \
            --connect-timeout 3 \
            --max-time 10 \
            --output "$health_file" \
            "$PUBLIC_BASE_URL/health" \
            && python3 - "$health_file" <<'PY'
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

stop_previous_slot() {
    [[ -n "$OLD_PROJECT" ]] || return 0
    [[ -f "$OLD_RELEASE_ENV_FILE" ]] || return 1
    docker compose \
        -p "$OLD_PROJECT" \
        --env-file "$OLD_RELEASE_ENV_FILE" \
        -f "$APP_COMPOSE_FILE" \
        stop backend frontend
}

printf 'reverse_proxy 127.0.0.1:%s\n' "$FRONTEND_PORT" >"$TEMP_FRAGMENT"
python3 \
    - "$CADDY_CONFIG" "$TEMP_CONFIG" "$CADDY_IMPORT_PATH" "$TEMP_FRAGMENT" <<'PY'
import pathlib
import sys

source_path, target_path, active_import, candidate_import = sys.argv[1:]
text = pathlib.Path(source_path).read_text(encoding="utf-8")
needle = f"import {active_import}"
if text.count(needle) != 1:
    raise SystemExit("switch: Caddy config must contain exactly one active import")
pathlib.Path(target_path).write_text(
    text.replace(needle, f"import {candidate_import}", 1),
    encoding="utf-8",
)
PY
caddy validate --config "$TEMP_CONFIG" --adapter caddyfile >/dev/null

cp -p "$ACTIVE_FRAGMENT" "$PRIOR_FRAGMENT_TMP"
mv -f "$TEMP_FRAGMENT" "$ACTIVE_FRAGMENT"
FRAGMENT_REPLACED=true
caddy reload --config "$CADDY_CONFIG" --adapter caddyfile >/dev/null
verify_public_health || die "public health verification failed after switch"

cp -p "$PRIOR_FRAGMENT_TMP" "$PRIOR_PERSIST_TMP"
mv -f "$PRIOR_PERSIST_TMP" "$PRIOR_FRAGMENT"
{
    printf 'ACTIVE_SLOT=%s\n' "$SLOT"
    printf 'ACTIVE_RELEASE=%s\n' "$RELEASE"
    printf 'ACTIVE_PROJECT=%s\n' "$PROJECT"
    printf 'ACTIVE_FRONTEND_PORT=%s\n' "$FRONTEND_PORT"
    printf 'ACTIVE_RELEASE_ENV_FILE=%s\n' "$RELEASE_ENV_FILE"
    printf 'PREVIOUS_SLOT=%s\n' "$OLD_SLOT"
    printf 'PREVIOUS_RELEASE=%s\n' "$OLD_RELEASE"
    printf 'PREVIOUS_PROJECT=%s\n' "$OLD_PROJECT"
    printf 'PREVIOUS_FRONTEND_PORT=%s\n' "$OLD_FRONTEND_PORT"
    printf 'PREVIOUS_RELEASE_ENV_FILE=%s\n' "$OLD_RELEASE_ENV_FILE"
    printf 'PRIOR_FRAGMENT=%s\n' "$PRIOR_FRAGMENT"
} >"$STATE_TMP"
chmod 600 "$STATE_TMP"
mv -f "$STATE_TMP" "$ACTIVE_STATE_FILE"
COMMITTED=true
FRAGMENT_REPLACED=false

if ! stop_previous_slot; then
    printf 'switch: warning: the previous app slot could not be stopped\n' >&2
fi
printf 'active slot is now %s at %s\n' "$SLOT" "$RELEASE"
