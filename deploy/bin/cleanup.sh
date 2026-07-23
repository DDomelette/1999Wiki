#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
DEPLOY_ROOT="${DEPLOY_ROOT:-/srv/1999wiki}"
RELEASES_DIR="${RELEASES_DIR:-$DEPLOY_ROOT/releases}"
STATE_DIR="${STATE_DIR:-$DEPLOY_ROOT/deploy-state}"
APP_COMPOSE_FILE="${APP_COMPOSE_FILE:-$REPO_ROOT/deploy/compose.app.yml}"
APP_ENV_FILE="${APP_ENV_FILE:-$DEPLOY_ROOT/protected/app.env}"
ACTIVE_STATE_FILE="${ACTIVE_STATE_FILE:-$STATE_DIR/active.env}"

die() {
    printf 'cleanup: %s\n' "$*" >&2
    exit 1
}

[[ "$#" -eq 3 ]] \
    || die "usage: ${0##*/} sha-<7 lowercase hex> <blue|green> remove-<slot>-<release>"
RELEASE="$1"
SLOT="$2"
PROVIDED_CONFIRMATION="$3"
[[ "$RELEASE" =~ ^sha-[0-9a-f]{7}$ ]] || die "invalid release"
[[ "$SLOT" == "blue" || "$SLOT" == "green" ]] || die "invalid slot"
CONFIRMATION="remove-${SLOT}-${RELEASE}"
[[ "$PROVIDED_CONFIRMATION" == "$CONFIRMATION" ]] \
    || die "confirmation must be exactly: $CONFIRMATION"

PROJECT="1999wiki-$SLOT"
[[ "$PROJECT" != "1999wiki-infra" ]] || die "infra project cleanup is forbidden"
RELEASE_ENV_FILE="${RELEASE_ENV_FILE:-$RELEASES_DIR/$RELEASE/$SLOT.env}"
for required_file in "$RELEASE_ENV_FILE" "$APP_COMPOSE_FILE" "$APP_ENV_FILE"; do
    [[ -f "$required_file" ]] || die "required file is missing: $required_file"
done
[[ "$RELEASE_ENV_FILE" != *.example ]] \
    || die "release metadata must not be a checked example"

mapfile -t image_values < <(
    python3 - "$RELEASE_ENV_FILE" "$RELEASE" <<'PY'
import re
import sys

values = {}
with open(sys.argv[1], encoding="utf-8") as stream:
    for raw_line in stream:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if separator and key in {"BACKEND_IMAGE", "FRONTEND_IMAGE"}:
            if key in values:
                raise SystemExit("cleanup: duplicate image metadata")
            values[key] = value.strip()
expected = {
    "BACKEND_IMAGE": "ghcr.io/ddomelette/1999wiki-backend",
    "FRONTEND_IMAGE": "ghcr.io/ddomelette/1999wiki-frontend",
}
for key, repository in expected.items():
    image = values.get(key, "")
    match = re.fullmatch(re.escape(repository) + r":(sha-[0-9a-f]{7})", image)
    if match is None or match.group(1) != sys.argv[2]:
        raise SystemExit(f"cleanup: {key} is not the exact requested release")
    print(image)
PY
)
BACKEND_IMAGE="${image_values[0]}"
FRONTEND_IMAGE="${image_values[1]}"

if [[ -f "$ACTIVE_STATE_FILE" ]]; then
    python3 - "$ACTIVE_STATE_FILE" "$SLOT" "$RELEASE" <<'PY'
import sys

values = {}
with open(sys.argv[1], encoding="utf-8") as stream:
    for raw_line in stream:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
if values.get("ACTIVE_SLOT") == sys.argv[2]:
    raise SystemExit("cleanup: refusing to remove the active slot")
if values.get("ACTIVE_RELEASE") == sys.argv[3]:
    raise SystemExit("cleanup: refusing to remove images used by the active release")
PY
fi

export APP_ENV_FILE
running_containers="$(
    docker compose \
        -p "$PROJECT" \
        --env-file "$RELEASE_ENV_FILE" \
        -f "$APP_COMPOSE_FILE" \
        ps --status running -q
)"
[[ -z "$running_containers" ]] || die "target app project is not inactive"

docker compose -p "$PROJECT" \
    --env-file "$RELEASE_ENV_FILE" \
    -f "$APP_COMPOSE_FILE" \
    down --remove-orphans
docker image rm "$BACKEND_IMAGE" "$FRONTEND_IMAGE"
printf 'removed inactive %s project and exact %s images\n' "$SLOT" "$RELEASE"
