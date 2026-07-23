#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
OPS_CONTEXT=deploy
source "$SCRIPT_DIR/ops-common.sh"

[[ "$#" -eq 2 ]] \
    || ops_die "usage: ${0##*/} sha-<7 lowercase hex> <blue|green>"
REQUESTED_RELEASE="$1"
SLOT="$2"
[[ "$REQUESTED_RELEASE" =~ ^sha-[0-9a-f]{7}$ ]] \
    || ops_die "invalid release"
[[ "$SLOT" == "blue" || "$SLOT" == "green" ]] \
    || ops_die "invalid slot"

SOURCE_RELEASE_ENV_FILE="${SOURCE_RELEASE_ENV_FILE:-${RELEASE_ENV_FILE:-$RELEASES_DIR/$REQUESTED_RELEASE/$SLOT.env}}"
SOURCE_APP_ENV_FILE="${SOURCE_APP_ENV_FILE:-${APP_ENV_FILE:-$DEPLOY_ROOT/protected/app.env}}"
PROJECT="1999wiki-$SLOT"

ops_acquire_lock
ops_reconcile_journal
ops_snapshot_release \
    "$REQUESTED_RELEASE" \
    "$SLOT" \
    "$SOURCE_RELEASE_ENV_FILE" \
    "$SOURCE_APP_ENV_FILE"
RELEASE_ENV_FILE="$RELEASE_SNAPSHOT"
export RELEASE_ENV_FILE APP_ENV_FILE

"$SCRIPT_DIR/preflight.sh" "$REQUESTED_RELEASE" "$SLOT"

candidate_cleanup_required=false
switched=false
cleanup() {
    local status=$?
    trap - EXIT
    if (( status != 0 )) \
        && [[ "$candidate_cleanup_required" == "true" && "$switched" == "false" ]]; then
        ops_compose "$PROJECT" stop backend frontend >/dev/null 2>&1 || true
    fi
    exit "$status"
}
trap cleanup EXIT

docker pull "$BACKEND_IMAGE"
docker pull "$FRONTEND_IMAGE"

# Responsibility is established before Compose can create even one service.
candidate_cleanup_required=true
ops_compose "$PROJECT" up -d --no-build --pull never backend frontend

CANDIDATE_BASE_URL="http://127.0.0.1:$FRONTEND_PORT"
ops_verify_project_identity "$PROJECT" "$CANDIDATE_BASE_URL" \
    || ops_die "candidate did not become healthy with the validated images"
"$SCRIPT_DIR/smoke-test.sh" \
    "$CANDIDATE_BASE_URL" \
    "$PUBLIC_BASE_URL" \
    "$APP_ENV_FILE"

"$SCRIPT_DIR/switch.sh" "$SLOT" "$RELEASE_SNAPSHOT"
switched=true
candidate_cleanup_required=false
printf 'deployed %s to %s\n' "$RELEASE" "$SLOT"
