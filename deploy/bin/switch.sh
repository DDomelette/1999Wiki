#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
OPS_CONTEXT=switch
export OPS_CONTEXT
# shellcheck disable=SC1091
source "$SCRIPT_DIR/ops-common.sh"

[[ "$#" -eq 2 ]] \
    || ops_die "usage: ${0##*/} SLOT RELEASE_SNAPSHOT"
SLOT="$1"
REQUESTED_RELEASE_SNAPSHOT="$2"
[[ "$SLOT" == "blue" || "$SLOT" == "green" ]] \
    || ops_die "invalid slot"

ops_acquire_lock "$0" "$@"
ops_reconcile_operations
ops_load_snapshot "$SLOT" "$REQUESTED_RELEASE_SNAPSHOT"
PROJECT="1999wiki-$SLOT"
CANDIDATE_BASE_URL="http://127.0.0.1:$FRONTEND_PORT"

OLD_STATE_PRESENT=0
OLD_SLOT=
OLD_RELEASE=
OLD_PROJECT=
OLD_FRONTEND_PORT=
OLD_RELEASE_SNAPSHOT=
OLD_APP_SNAPSHOT=
OLD_BACKEND_IMAGE=
OLD_FRONTEND_IMAGE=
if [[ -f "$ACTIVE_STATE_FILE" ]]; then
    ops_load_active_state
    ops_validate_active_consistency
    [[ "$ACTIVE_SLOT" != "$SLOT" ]] \
        || ops_die "refusing to switch the already-active slot"
    OLD_STATE_PRESENT=1
    OLD_SLOT="$ACTIVE_SLOT"
    OLD_RELEASE="$ACTIVE_RELEASE"
    OLD_PROJECT="$ACTIVE_PROJECT"
    OLD_FRONTEND_PORT="$ACTIVE_FRONTEND_PORT"
    OLD_RELEASE_SNAPSHOT="$ACTIVE_RELEASE_SNAPSHOT"
    OLD_APP_SNAPSHOT="$ACTIVE_APP_SNAPSHOT"
    OLD_BACKEND_IMAGE="$ACTIVE_BACKEND_IMAGE"
    OLD_FRONTEND_IMAGE="$ACTIVE_FRONTEND_IMAGE"
fi

# Standalone switch repeats identity, readiness, and smoke checks under the lock.
ops_verify_project_identity "$PROJECT" "$CANDIDATE_BASE_URL" \
    || ops_die "candidate project identity/readiness does not match its snapshot"
"$SCRIPT_DIR/smoke-test.sh" \
    "$CANDIDATE_BASE_URL" \
    "$PUBLIC_BASE_URL" \
    "$APP_ENV_FILE"

umask 077
CANDIDATE_FRAGMENT="$(mktemp "$DEPLOY_STATE_ROOT/.candidate-fragment.XXXXXX")"
TEMP_CONFIG="$(mktemp "$DEPLOY_STATE_ROOT/.candidate-Caddyfile.XXXXXX")"
STATE_CANDIDATE="$(mktemp "$DEPLOY_STATE_ROOT/.candidate-state.XXXXXX")"
transaction_started=false
cleanup() {
    local status=$?
    trap - EXIT
    if (( status != 0 )) && [[ "$transaction_started" == "true" ]]; then
        ops_recover_failed_transaction "$status" || true
    fi
    rm -f -- "$CANDIDATE_FRAGMENT" "$TEMP_CONFIG" "$STATE_CANDIDATE"
    exit "$status"
}
trap cleanup EXIT

printf 'reverse_proxy 127.0.0.1:%s\n' "$FRONTEND_PORT" >"$CANDIDATE_FRAGMENT"
python3 \
    - "$CADDY_CONFIG" "$TEMP_CONFIG" "$CADDY_IMPORT_PATH" "$CANDIDATE_FRAGMENT" <<'PY'
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
ops_load_caddy_env
caddy validate --config "$TEMP_CONFIG" --adapter caddyfile >/dev/null

ops_begin_transaction switch
transaction_started=true
{
    printf 'STATE_VERSION=3\n'
    printf 'GENERATION=%s\n' "$TRANSACTION_GENERATION"
    printf 'ACTIVE_SLOT=%s\n' "$SLOT"
    printf 'ACTIVE_RELEASE=%s\n' "$RELEASE"
    printf 'ACTIVE_PROJECT=%s\n' "$PROJECT"
    printf 'ACTIVE_FRONTEND_PORT=%s\n' "$FRONTEND_PORT"
    printf 'ACTIVE_RELEASE_SNAPSHOT=%s\n' "$RELEASE_SNAPSHOT"
    printf 'ACTIVE_APP_SNAPSHOT=%s\n' "$APP_ENV_FILE"
    printf 'ACTIVE_BACKEND_IMAGE=%s\n' "$BACKEND_IMAGE"
    printf 'ACTIVE_FRONTEND_IMAGE=%s\n' "$FRONTEND_IMAGE"
    printf 'PREVIOUS_AVAILABLE=%s\n' "$OLD_STATE_PRESENT"
    printf 'PREVIOUS_SLOT=%s\n' "$OLD_SLOT"
    printf 'PREVIOUS_RELEASE=%s\n' "$OLD_RELEASE"
    printf 'PREVIOUS_PROJECT=%s\n' "$OLD_PROJECT"
    printf 'PREVIOUS_FRONTEND_PORT=%s\n' "$OLD_FRONTEND_PORT"
    printf 'PREVIOUS_RELEASE_SNAPSHOT=%s\n' "$OLD_RELEASE_SNAPSHOT"
    printf 'PREVIOUS_APP_SNAPSHOT=%s\n' "$OLD_APP_SNAPSHOT"
    printf 'PREVIOUS_BACKEND_IMAGE=%s\n' "$OLD_BACKEND_IMAGE"
    printf 'PREVIOUS_FRONTEND_IMAGE=%s\n' "$OLD_FRONTEND_IMAGE"
    if [[ "$OLD_STATE_PRESENT" == "1" ]]; then
        printf 'PREVIOUS_FRAGMENT_BACKUP=%s\n' "$TRANSACTION_OLD_FRAGMENT"
    else
        printf 'PREVIOUS_FRAGMENT_BACKUP=\n'
    fi
} | ops_helper atomic-stdin \
    "$STATE_CANDIDATE" \
    600 \
    "$OPS_STATE_UID" \
    "$OPS_STATE_GID"
ops_helper validate-state "$STATE_CANDIDATE" "$DEPLOY_STATE_ROOT"

ops_install_transaction_traffic "$CANDIDATE_FRAGMENT"
ops_verify_public_health \
    || ops_die "public health verification failed after switch"
ops_test_crash_before_state_commit
ops_commit_transaction_state "$STATE_CANDIDATE"
transaction_started=false
ops_finalize_committed_transaction || true
ops_remove_orphan_transaction_backups || \
    printf 'switch: warning: obsolete transaction backups remain\n' >&2

if [[ "$OLD_STATE_PRESENT" == "1" ]]; then
    if ! (
        ops_load_snapshot "$OLD_SLOT" "$OLD_RELEASE_SNAPSHOT"
        ops_compose "$OLD_PROJECT" stop backend frontend
    ); then
        printf 'switch: warning: the previous app slot could not be stopped\n' >&2
    fi
fi
printf 'active slot is now %s at %s\n' "$SLOT" "$RELEASE" || true
