#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
OPS_CONTEXT=rollback
export OPS_CONTEXT
# shellcheck disable=SC1091
source "$SCRIPT_DIR/ops-common.sh"

[[ "$#" -eq 0 ]] || ops_die "usage: ${0##*/}"
ops_acquire_lock "$0" "$@"
ops_reconcile_operations
ops_load_active_state
ops_validate_active_consistency
[[ "$PREVIOUS_AVAILABLE" == "1" ]] \
    || ops_die "no complete previous deployment is recorded"

CURRENT_SLOT="$ACTIVE_SLOT"
CURRENT_RELEASE="$ACTIVE_RELEASE"
CURRENT_PROJECT="$ACTIVE_PROJECT"
CURRENT_FRONTEND_PORT="$ACTIVE_FRONTEND_PORT"
CURRENT_RELEASE_SNAPSHOT="$ACTIVE_RELEASE_SNAPSHOT"
CURRENT_APP_SNAPSHOT="$ACTIVE_APP_SNAPSHOT"
CURRENT_BACKEND_IMAGE="$ACTIVE_BACKEND_IMAGE"
CURRENT_FRONTEND_IMAGE="$ACTIVE_FRONTEND_IMAGE"

ROLLBACK_SLOT="$PREVIOUS_SLOT"
ROLLBACK_RELEASE="$PREVIOUS_RELEASE"
ROLLBACK_PROJECT="$PREVIOUS_PROJECT"
ROLLBACK_RELEASE_SNAPSHOT="$PREVIOUS_RELEASE_SNAPSHOT"
ops_load_snapshot "$ROLLBACK_SLOT" "$ROLLBACK_RELEASE_SNAPSHOT"
[[ "$RELEASE" == "$ROLLBACK_RELEASE" ]] \
    || ops_die "recorded rollback release diverges from its snapshot"
CANDIDATE_BASE_URL="http://127.0.0.1:$FRONTEND_PORT"

ROLLBACK_FRAGMENT=
TEMP_CONFIG=
STATE_CANDIDATE=
transaction_started=false
rollback_cleanup_required=false
cleanup() {
    local status=$?
    trap - EXIT
    if (( status != 0 )); then
        set +e
        if [[ "$transaction_started" == "true" ]]; then
            ops_recover_failed_transaction "$status" || true
        fi
        if [[ "$rollback_cleanup_required" == "true" ]] \
            && ! ops_candidate_is_committed \
                "$ROLLBACK_SLOT" \
                "$ROLLBACK_PROJECT" \
                "$ROLLBACK_RELEASE_SNAPSHOT"; then
            (
                ops_load_snapshot "$ROLLBACK_SLOT" "$ROLLBACK_RELEASE_SNAPSHOT"
                ops_compose "$ROLLBACK_PROJECT" stop backend frontend
            ) >/dev/null 2>&1 || true
        fi
        set -e
    fi
    rm -f -- "$ROLLBACK_FRAGMENT" "$TEMP_CONFIG" "$STATE_CANDIDATE"
    exit "$status"
}
trap cleanup EXIT

# Responsibility is established before Compose can partially restart a service.
rollback_cleanup_required=true
ops_compose "$ROLLBACK_PROJECT" start backend frontend
ops_verify_project_identity "$ROLLBACK_PROJECT" "$CANDIDATE_BASE_URL" \
    || ops_die "recorded previous project did not become healthy with validated images"
"$SCRIPT_DIR/smoke-test.sh" \
    "$CANDIDATE_BASE_URL" \
    "$PUBLIC_BASE_URL" \
    "$APP_ENV_FILE"

umask 077
ROLLBACK_FRAGMENT="$(mktemp "$DEPLOY_STATE_ROOT/.rollback-fragment.XXXXXX")"
TEMP_CONFIG="$(mktemp "$DEPLOY_STATE_ROOT/.rollback-Caddyfile.XXXXXX")"
STATE_CANDIDATE="$(mktemp "$DEPLOY_STATE_ROOT/.rollback-state.XXXXXX")"

# Regenerate from strictly validated previous metadata; never trust stale text.
printf 'reverse_proxy 127.0.0.1:%s\n' "$FRONTEND_PORT" >"$ROLLBACK_FRAGMENT"
python3 \
    - "$CADDY_CONFIG" "$TEMP_CONFIG" "$CADDY_IMPORT_PATH" "$ROLLBACK_FRAGMENT" <<'PY'
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
ops_load_caddy_env
caddy validate --config "$TEMP_CONFIG" --adapter caddyfile >/dev/null

ops_begin_transaction rollback
transaction_started=true
{
    printf 'STATE_VERSION=3\n'
    printf 'GENERATION=%s\n' "$TRANSACTION_GENERATION"
    printf 'ACTIVE_SLOT=%s\n' "$ROLLBACK_SLOT"
    printf 'ACTIVE_RELEASE=%s\n' "$ROLLBACK_RELEASE"
    printf 'ACTIVE_PROJECT=%s\n' "$ROLLBACK_PROJECT"
    printf 'ACTIVE_FRONTEND_PORT=%s\n' "$FRONTEND_PORT"
    printf 'ACTIVE_RELEASE_SNAPSHOT=%s\n' "$RELEASE_SNAPSHOT"
    printf 'ACTIVE_APP_SNAPSHOT=%s\n' "$APP_ENV_FILE"
    printf 'ACTIVE_BACKEND_IMAGE=%s\n' "$BACKEND_IMAGE"
    printf 'ACTIVE_FRONTEND_IMAGE=%s\n' "$FRONTEND_IMAGE"
    printf 'PREVIOUS_AVAILABLE=1\n'
    printf 'PREVIOUS_SLOT=%s\n' "$CURRENT_SLOT"
    printf 'PREVIOUS_RELEASE=%s\n' "$CURRENT_RELEASE"
    printf 'PREVIOUS_PROJECT=%s\n' "$CURRENT_PROJECT"
    printf 'PREVIOUS_FRONTEND_PORT=%s\n' "$CURRENT_FRONTEND_PORT"
    printf 'PREVIOUS_RELEASE_SNAPSHOT=%s\n' "$CURRENT_RELEASE_SNAPSHOT"
    printf 'PREVIOUS_APP_SNAPSHOT=%s\n' "$CURRENT_APP_SNAPSHOT"
    printf 'PREVIOUS_BACKEND_IMAGE=%s\n' "$CURRENT_BACKEND_IMAGE"
    printf 'PREVIOUS_FRONTEND_IMAGE=%s\n' "$CURRENT_FRONTEND_IMAGE"
    printf 'PREVIOUS_FRAGMENT_BACKUP=%s\n' "$TRANSACTION_OLD_FRAGMENT"
} | ops_helper atomic-stdin \
    "$STATE_CANDIDATE" \
    600 \
    "$OPS_STATE_UID" \
    "$OPS_STATE_GID"
ops_helper validate-state "$STATE_CANDIDATE" "$DEPLOY_STATE_ROOT"

ops_install_transaction_traffic "$ROLLBACK_FRAGMENT"
ops_verify_public_health \
    || ops_die "public health verification failed after rollback"
ops_test_crash_before_state_commit
ops_commit_transaction_state "$STATE_CANDIDATE"
transaction_started=false
rollback_cleanup_required=false
ops_finalize_committed_transaction || true
ops_remove_orphan_transaction_backups || \
    printf 'rollback: warning: obsolete transaction backups remain\n' >&2

if ! (
    ops_load_snapshot "$CURRENT_SLOT" "$CURRENT_RELEASE_SNAPSHOT"
    ops_compose "$CURRENT_PROJECT" stop backend frontend
); then
    printf 'rollback: warning: the replaced app slot could not be stopped\n' >&2
fi
printf 'rolled back to %s at %s\n' "$ROLLBACK_SLOT" "$ROLLBACK_RELEASE" || true
