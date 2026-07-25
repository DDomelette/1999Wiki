#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
OPS_CONTEXT=preflight
export OPS_CONTEXT
# shellcheck disable=SC1091
source "$SCRIPT_DIR/ops-common.sh"

PROTECTED_ENV_DIR="${PROTECTED_ENV_DIR:-$DEPLOY_ROOT/protected}"
RAG_ROOT="${RAG_ROOT:-$DEPLOY_ROOT/rag-artifacts}"
APP_ENV_FILE="${APP_ENV_FILE:-$PROTECTED_ENV_DIR/app.env}"
INFRA_ENV_FILE="${INFRA_ENV_FILE:-$PROTECTED_ENV_DIR/infra.env}"
CADDY_ENV_FILE="${CADDY_ENV_FILE:-$PROTECTED_ENV_DIR/caddy.env}"
INFRA_NETWORK="${INFRA_NETWORK:-1999wiki-infra}"
INFRA_PROJECT="${INFRA_PROJECT:-1999wiki-infra}"
MIN_FREE_BYTES=8589934592

[[ "$#" -eq 2 ]] \
    || ops_die "usage: ${0##*/} sha-<7 lowercase hex> <blue|green>"
RELEASE="$1"
SLOT="$2"
[[ "$RELEASE" =~ ^sha-[0-9a-f]{7}$ ]] \
    || ops_die "release must match sha-[0-9a-f]{7}"
[[ "$SLOT" == "blue" || "$SLOT" == "green" ]] \
    || ops_die "slot must be blue or green"
RELEASE_ENV_FILE="${RELEASE_ENV_FILE:-$RELEASES_DIR/$RELEASE/$SLOT.env}"
PROJECT="1999wiki-$SLOT"

ops_require_commands docker caddy curl python3 flock stat
docker compose version >/dev/null 2>&1 \
    || ops_die "Docker Compose v2 is unavailable"
ops_validate_state_root
[[ ! -e "$OPS_RETIREMENT_FILE" ]] \
    || ops_die "a pending retirement journal must be reconciled under the operations lock"

for required_directory in \
    "$DEPLOY_ROOT" \
    "$PROTECTED_ENV_DIR" \
    "$RELEASES_DIR" \
    "$RAG_ROOT"; do
    [[ -d "$required_directory" ]] \
        || ops_die "required directory is missing: $required_directory"
done
for required_file in \
    "$APP_COMPOSE_FILE" \
    "$INFRA_COMPOSE_FILE" \
    "$CADDY_CONFIG" \
    "$ACTIVE_FRAGMENT" \
    "$RELEASE_ENV_FILE" \
    "$APP_ENV_FILE" \
    "$INFRA_ENV_FILE" \
    "$CADDY_ENV_FILE" \
    "$RAG_ROOT/active_build.v1.json"; do
    [[ -f "$required_file" ]] \
        || ops_die "required file is missing: $required_file"
done

for protected_file in \
    "$RELEASE_ENV_FILE" \
    "$APP_ENV_FILE" \
    "$INFRA_ENV_FILE" \
    "$CADDY_ENV_FILE"; do
    ops_helper validate-protected \
        "$protected_file" \
        --repo-root "$REPO_ROOT" \
        --outside-repo
done
ops_helper validate-env release "$RELEASE_ENV_FILE" --release "$RELEASE"
ops_helper validate-env app "$APP_ENV_FILE"
ops_helper validate-env infra "$INFRA_ENV_FILE"
ops_helper validate-env caddy "$CADDY_ENV_FILE"

mapfile -t release_values < <(
    ops_helper emit-release "$RELEASE_ENV_FILE" --release "$RELEASE"
)
[[ "${#release_values[@]}" -eq 4 ]] \
    || ops_die "release metadata is incomplete"
BACKEND_IMAGE="${release_values[0]}"
FRONTEND_IMAGE="${release_values[1]}"
BACKEND_PORT="${release_values[2]}"
FRONTEND_PORT="${release_values[3]}"
export BACKEND_IMAGE FRONTEND_IMAGE BACKEND_PORT FRONTEND_PORT APP_ENV_FILE

ops_load_caddy_env
ops_capture_fragment_metadata
if [[ -f "$ACTIVE_STATE_FILE" ]]; then
    ops_load_active_state
    ops_validate_active_consistency
    [[ "$ACTIVE_SLOT" != "$SLOT" ]] \
        || ops_die "target slot is currently active"
    if [[ "$PREVIOUS_AVAILABLE" == "1" ]]; then
        [[ "$PREVIOUS_SLOT" != "$SLOT" ]] \
            || ops_die "target slot is still protected as the rollback target"
    fi
fi

if grep -Eiq \
    '(^|[^A-Za-z0-9_-])backend([^A-Za-z0-9_-]|$)' \
    "$INFRA_COMPOSE_FILE"; then
    ops_die "shared infra configuration must not reference or consume backend"
fi
if [[ -n "${INFRA_CONFIG_PATHS:-}" ]]; then
    IFS=':' read -r -a infra_config_paths <<<"$INFRA_CONFIG_PATHS"
    for config_path in "${infra_config_paths[@]}"; do
        [[ -f "$config_path" ]] \
            || ops_die "infra configuration is missing: $config_path"
        if grep -Eiq \
            '(^|[^A-Za-z0-9_-])backend([^A-Za-z0-9_-]|$)' \
            "$config_path"; then
            ops_die "shared infra configuration must not reference or consume backend"
        fi
    done
fi

available_kib="$(df -Pk "$DEPLOY_ROOT" | awk 'NR == 2 { print $4 }')"
[[ "$available_kib" =~ ^[0-9]+$ ]] \
    || ops_die "could not read available disk space"
(( available_kib * 1024 >= MIN_FREE_BYTES )) \
    || ops_die "at least 8 GiB free disk is required"
[[ -r /proc/meminfo ]] \
    || ops_die "system memory information is unreadable"
grep -Eq '^MemTotal:[[:space:]]+[0-9]+[[:space:]]+kB$' /proc/meminfo \
    || ops_die "system memory information is invalid"

network_name="$(docker network inspect "$INFRA_NETWORK" --format '{{.Name}}')"
[[ "$network_name" == "$INFRA_NETWORK" ]] \
    || ops_die "external infra network is unavailable"
docker compose \
    -p "$INFRA_PROJECT" \
    --env-file "$INFRA_ENV_FILE" \
    -f "$INFRA_COMPOSE_FILE" \
    config --quiet

for service in mysql minio etcd standalone; do
    infra_status="$(
        docker compose \
            -p "$INFRA_PROJECT" \
            --env-file "$INFRA_ENV_FILE" \
            -f "$INFRA_COMPOSE_FILE" \
            ps --format json "$service"
    )"
    python3 - "$service" "$infra_status" <<'PY'
import json
import sys

service, raw = sys.argv[1:]
payload = json.loads(raw)
rows = payload if isinstance(payload, list) else [payload]
if len(rows) != 1:
    raise SystemExit(f"preflight: {service} must have exactly one container")
row = rows[0]
if row.get("State") != "running" or row.get("Health") != "healthy":
    raise SystemExit(f"preflight: {service} is not running and healthy")
PY
done

docker compose \
    -p "$PROJECT" \
    --env-file "$RELEASE_ENV_FILE" \
    -f "$APP_COMPOSE_FILE" \
    config --quiet
target_containers="$(
    docker compose \
        -p "$PROJECT" \
        --env-file "$RELEASE_ENV_FILE" \
        -f "$APP_COMPOSE_FILE" \
        ps -a -q
)"
[[ -z "$target_containers" ]] \
    || ops_die "target slot already has application containers"

caddy validate --config "$CADDY_CONFIG" --adapter caddyfile >/dev/null
printf 'preflight passed for %s in %s\n' "$RELEASE" "$SLOT"
