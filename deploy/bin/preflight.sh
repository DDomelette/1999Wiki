#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
DEPLOY_ROOT="${DEPLOY_ROOT:-/srv/1999wiki}"
PROTECTED_ENV_DIR="${PROTECTED_ENV_DIR:-$DEPLOY_ROOT/protected}"
RELEASES_DIR="${RELEASES_DIR:-$DEPLOY_ROOT/releases}"
STATE_DIR="${STATE_DIR:-$DEPLOY_ROOT/deploy-state}"
RAG_ROOT="${RAG_ROOT:-$DEPLOY_ROOT/rag-artifacts}"
APP_COMPOSE_FILE="${APP_COMPOSE_FILE:-$REPO_ROOT/deploy/compose.app.yml}"
INFRA_COMPOSE_FILE="${INFRA_COMPOSE_FILE:-$REPO_ROOT/deploy/compose.infra.yml}"
CADDY_CONFIG="${CADDY_CONFIG:-/etc/caddy/Caddyfile}"
ACTIVE_FRAGMENT="${ACTIVE_FRAGMENT:-/etc/caddy/active-upstream.caddy}"
CADDY_ENV_FILE="${CADDY_ENV_FILE:-$PROTECTED_ENV_DIR/caddy.env}"
APP_ENV_FILE="${APP_ENV_FILE:-$PROTECTED_ENV_DIR/app.env}"
INFRA_ENV_FILE="${INFRA_ENV_FILE:-$PROTECTED_ENV_DIR/infra.env}"
ACTIVE_STATE_FILE="${ACTIVE_STATE_FILE:-$STATE_DIR/active.env}"
INFRA_NETWORK="${INFRA_NETWORK:-1999wiki-infra}"
INFRA_PROJECT="${INFRA_PROJECT:-1999wiki-infra}"
MIN_FREE_BYTES=8589934592

die() {
    printf 'preflight: %s\n' "$*" >&2
    exit 1
}

usage() {
    printf 'Usage: %s sha-<7 lowercase hex> <blue|green>\n' "${0##*/}" >&2
    exit 64
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "required command is unavailable: $1"
}

resolve_existing_file() {
    local path="$1"
    local label="$2"
    [[ -f "$path" ]] || die "$label is not a regular file: $path"
    python3 - "$path" <<'PY'
import pathlib
import sys

print(pathlib.Path(sys.argv[1]).resolve(strict=True))
PY
}

require_existing_directory() {
    local path="$1"
    local label="$2"
    [[ -d "$path" ]] || die "$label is not an existing directory: $path"
}

validate_protected_env_file() {
    local path="$1"
    local label="$2"
    local reject_repo="$3"
    local resolved

    resolved="$(resolve_existing_file "$path" "$label")"
    [[ "$resolved" != *.example ]] || die "$label must not be a checked example"
    if [[ "$reject_repo" == "yes" ]]; then
        case "$resolved" in
            "$REPO_ROOT"|"$REPO_ROOT"/*)
                die "$label must resolve outside the Git repository"
                ;;
        esac
    fi

    if [[ "$(uname -s)" == "Linux" ]]; then
        python3 - "$resolved" "$label" <<'PY'
import os
import stat
import sys

path, label = sys.argv[1:]
info = os.stat(path, follow_symlinks=True)
mode = stat.S_IMODE(info.st_mode)
if mode != 0o600:
    raise SystemExit(f"preflight: {label} must have mode 0600 on Linux")
if info.st_uid not in {0, os.geteuid()}:
    raise SystemExit(f"preflight: {label} must be owned by root or the current user")
PY
    fi
}

validate_env_keys() {
    local path="$1"
    local label="$2"
    shift 2
    python3 - "$path" "$label" "$@" <<'PY'
import re
import sys

path, label, *required = sys.argv[1:]
values = {}
with open(path, encoding="utf-8") as stream:
    for line_number, raw_line in enumerate(stream, 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export ") or "=" not in line:
            raise SystemExit(
                f"preflight: {label} has unsupported syntax on line {line_number}"
            )
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in values:
            raise SystemExit(
                f"preflight: {label} has an invalid or duplicate key on line {line_number}"
            )
        values[key] = value.strip()

def is_nonempty(value):
    stripped = value.strip()
    return (
        bool(stripped)
        and stripped not in {'""', "''"}
        and re.fullmatch(r"\$\{[^}]+\}", stripped) is None
    )


missing = [key for key in required if not is_nonempty(values.get(key, ""))]
if missing:
    raise SystemExit(
        f"preflight: {label} has empty required variables: {','.join(missing)}"
    )
PY
}

read_caddy_metadata() {
    python3 - "$CADDY_ENV_FILE" <<'PY'
import re
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
            if key in values:
                raise SystemExit("preflight: duplicate Caddy environment variable")
            values[key] = value.strip()
if set(values) != set(wanted):
    raise SystemExit("preflight: incomplete Caddy environment")
if re.fullmatch(r"127\.0\.0\.1:[0-9]{2,5}", values["MINIO_PROXY_UPSTREAM"]) is None:
    raise SystemExit("preflight: MINIO_PROXY_UPSTREAM must use IPv4 loopback")
for key in wanted:
    print(values[key])
PY
}

read_release_metadata() {
    python3 - "$RELEASE_ENV_FILE" <<'PY'
import re
import sys

values = {}
with open(sys.argv[1], encoding="utf-8") as stream:
    for line_number, raw_line in enumerate(stream, 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export ") or "=" not in line:
            raise SystemExit(
                f"preflight: release environment has unsupported syntax on line {line_number}"
            )
        key, value = line.split("=", 1)
        key = key.strip()
        if key in values:
            raise SystemExit(
                f"preflight: release environment has duplicate key {key}"
            )
        values[key] = value.strip()

required = ("BACKEND_IMAGE", "FRONTEND_IMAGE", "BACKEND_PORT", "FRONTEND_PORT")
missing = [key for key in required if not values.get(key)]
if missing:
    raise SystemExit(
        "preflight: release environment has empty required variables: "
        + ",".join(missing)
    )

expected = {
    "BACKEND_IMAGE": "ghcr.io/ddomelette/1999wiki-backend",
    "FRONTEND_IMAGE": "ghcr.io/ddomelette/1999wiki-frontend",
}
tags = {}
for key, repository in expected.items():
    match = re.fullmatch(re.escape(repository) + r":(sha-[0-9a-f]{7})", values[key])
    if match is None:
        raise SystemExit(f"preflight: {key} is not an approved immutable image")
    tags[key] = match.group(1)
if len(set(tags.values())) != 1:
    raise SystemExit("preflight: Backend and Frontend image tags must be identical")

for key in ("BACKEND_PORT", "FRONTEND_PORT"):
    value = values[key]
    if not value.isascii() or not value.isdecimal() or not 1024 <= int(value) <= 65535:
        raise SystemExit(f"preflight: {key} is not a safe unprivileged port")
if values["BACKEND_PORT"] == values["FRONTEND_PORT"]:
    raise SystemExit("preflight: Backend and Frontend ports must differ")

print(tags["BACKEND_IMAGE"])
PY
}

validate_infra_isolation() {
    local config_path
    local paths=("$INFRA_COMPOSE_FILE")
    if [[ -n "${INFRA_CONFIG_PATHS:-}" ]]; then
        IFS=':' read -r -a paths <<<"$INFRA_CONFIG_PATHS"
        paths=("$INFRA_COMPOSE_FILE" "${paths[@]}")
    fi
    for config_path in "${paths[@]}"; do
        [[ -f "$config_path" ]] || die "infra configuration is missing: $config_path"
        if grep -Eiq '(^|[^A-Za-z0-9_-])backend([^A-Za-z0-9_-]|$)' "$config_path"; then
            die "shared infra configuration must not reference or consume backend"
        fi
    done
}

validate_compose_health() {
    local compose_file="$1"
    local env_file="$2"
    local project="$3"
    shift 3
    local service
    local payload

    for service in "$@"; do
        payload="$(
            docker compose \
                -p "$project" \
                --env-file "$env_file" \
                -f "$compose_file" \
                ps --format json "$service"
        )"
        python3 - "$service" "$payload" <<'PY'
import json
import sys

service, raw = sys.argv[1:]
try:
    payload = json.loads(raw)
except json.JSONDecodeError as exc:
    raise SystemExit(f"preflight: invalid Compose status for {service}") from exc
rows = payload if isinstance(payload, list) else [payload]
if len(rows) != 1:
    raise SystemExit(f"preflight: {service} must have exactly one container")
row = rows[0]
if row.get("State") != "running" or row.get("Health") != "healthy":
    raise SystemExit(f"preflight: {service} is not running and healthy")
PY
    done
}

validate_active_state() {
    [[ -e "$ACTIVE_STATE_FILE" ]] || return 0
    [[ -f "$ACTIVE_STATE_FILE" ]] || die "active deployment state is not a file"
    python3 - "$ACTIVE_STATE_FILE" "$SLOT" <<'PY'
import sys

path, target_slot = sys.argv[1:]
values = {}
with open(path, encoding="utf-8") as stream:
    for raw_line in stream:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise SystemExit("preflight: active deployment state is malformed")
        key, value = line.split("=", 1)
        values[key] = value
if values.get("ACTIVE_SLOT") == target_slot:
    raise SystemExit("preflight: target slot is currently active")
PY
}

[[ "$#" -eq 2 ]] || usage
RELEASE="$1"
SLOT="$2"
[[ "$RELEASE" =~ ^sha-[0-9a-f]{7}$ ]] || die "release must match sha-[0-9a-f]{7}"
[[ "$SLOT" == "blue" || "$SLOT" == "green" ]] || die "slot must be blue or green"
RELEASE_ENV_FILE="${RELEASE_ENV_FILE:-$RELEASES_DIR/$RELEASE/$SLOT.env}"
PROJECT="1999wiki-$SLOT"

for command_name in docker caddy curl python3; do
    require_command "$command_name"
done
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is unavailable"

require_existing_directory "$DEPLOY_ROOT" "deployment root"
require_existing_directory "$PROTECTED_ENV_DIR" "protected environment directory"
require_existing_directory "$RELEASES_DIR" "release directory"
require_existing_directory "$STATE_DIR" "deployment state directory"
require_existing_directory "$RAG_ROOT" "RAG closure root"
[[ -f "$RAG_ROOT/active_build.v1.json" ]] \
    || die "active RAG pointer is missing from the RAG closure root"

for required_file in \
    "$APP_COMPOSE_FILE" \
    "$INFRA_COMPOSE_FILE" \
    "$CADDY_CONFIG" \
    "$ACTIVE_FRAGMENT" \
    "$RELEASE_ENV_FILE"; do
    [[ -f "$required_file" ]] || die "required file is missing: $required_file"
done
[[ "$RELEASE_ENV_FILE" != *.example ]] || die "release metadata must not be a checked example"

validate_protected_env_file "$APP_ENV_FILE" "APP_ENV_FILE" yes
validate_protected_env_file "$INFRA_ENV_FILE" "INFRA_ENV_FILE" no
validate_protected_env_file "$CADDY_ENV_FILE" "CADDY_ENV_FILE" no
validate_env_keys \
    "$APP_ENV_FILE" \
    "APP_ENV_FILE" \
    APP_ENV MILVUS_URI MILVUS_DB_NAME MILVUS_COLLECTION_NAME \
    MINIO_ENDPOINT MINIO_ACCESS_KEY MINIO_SECRET_KEY MINIO_BUCKET \
    MEDIA_PUBLIC_BASE_URL MYSQL_HOST MYSQL_PORT MYSQL_DATABASE MYSQL_USER \
    MYSQL_PASSWORD DEEPSEEK_API_KEY SILICONFLOW_API_KEY HUIJI_PROCESSED_ROOT
validate_env_keys \
    "$INFRA_ENV_FILE" \
    "INFRA_ENV_FILE" \
    MYSQL_ROOT_PASSWORD MYSQL_USER MYSQL_PASSWORD MINIO_ROOT_USER MINIO_ROOT_PASSWORD
validate_env_keys \
    "$CADDY_ENV_FILE" \
    "CADDY_ENV_FILE" \
    SITE_ADDRESS MINIO_PROXY_UPSTREAM
mapfile -t caddy_values < <(read_caddy_metadata)
SITE_ADDRESS="${caddy_values[0]}"
MINIO_PROXY_UPSTREAM="${caddy_values[1]}"
export SITE_ADDRESS MINIO_PROXY_UPSTREAM

validated_tag="$(read_release_metadata)"
[[ "$validated_tag" == "$RELEASE" ]] || die "release argument does not match paired image tags"
validate_infra_isolation
validate_active_state

available_kib="$(df -Pk "$DEPLOY_ROOT" | awk 'NR == 2 { print $4 }')"
[[ "$available_kib" =~ ^[0-9]+$ ]] || die "could not read available disk space"
(( available_kib * 1024 >= MIN_FREE_BYTES )) || die "at least 8 GiB free disk is required"
[[ -r /proc/meminfo ]] || die "system memory information is unreadable"
grep -Eq '^MemTotal:[[:space:]]+[0-9]+[[:space:]]+kB$' /proc/meminfo \
    || die "system memory information is invalid"

network_name="$(docker network inspect "$INFRA_NETWORK" --format '{{.Name}}')"
[[ "$network_name" == "$INFRA_NETWORK" ]] || die "external infra network is unavailable"

docker compose \
    -p "$INFRA_PROJECT" \
    --env-file "$INFRA_ENV_FILE" \
    -f "$INFRA_COMPOSE_FILE" \
    config --quiet
validate_compose_health \
    "$INFRA_COMPOSE_FILE" \
    "$INFRA_ENV_FILE" \
    "$INFRA_PROJECT" \
    mysql minio etcd standalone

export APP_ENV_FILE
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
[[ -z "$target_containers" ]] || die "target slot already has application containers"

caddy validate --config "$CADDY_CONFIG" --adapter caddyfile >/dev/null
printf 'preflight passed for %s in %s\n' "$RELEASE" "$SLOT"
