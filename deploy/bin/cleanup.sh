#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
OPS_CONTEXT=cleanup
export OPS_CONTEXT
# shellcheck disable=SC1091
source "$SCRIPT_DIR/ops-common.sh"

[[ "$#" -eq 3 ]] \
    || ops_die "usage: ${0##*/} sha-<7 lowercase hex> <blue|green> remove-<slot>-<release>"
REQUESTED_RELEASE="$1"
SLOT="$2"
PROVIDED_CONFIRMATION="$3"
[[ "$REQUESTED_RELEASE" =~ ^sha-[0-9a-f]{7}$ ]] \
    || ops_die "invalid release"
[[ "$SLOT" == "blue" || "$SLOT" == "green" ]] \
    || ops_die "invalid slot"
CONFIRMATION="remove-${SLOT}-${REQUESTED_RELEASE}"
[[ "$PROVIDED_CONFIRMATION" == "$CONFIRMATION" ]] \
    || ops_die "confirmation must be exactly: $CONFIRMATION"

ops_acquire_lock "$0" "$@"
retirement_was_pending=false
if [[ -e "$OPS_RETIREMENT_FILE" ]]; then
    retirement_was_pending=true
fi
ops_reconcile_operations
ops_load_active_state
ops_validate_active_consistency

if [[ "$retirement_was_pending" == "true" && "$PREVIOUS_AVAILABLE" == "0" ]]; then
    [[ \
        "$SLOT" == "$RETIREMENT_SLOT" \
        && "$REQUESTED_RELEASE" == "$RETIREMENT_RELEASE" \
    ]] || ops_die "completed retirement does not match the requested cleanup target"
    printf 'retirement retry completed for %s at %s\n' "$SLOT" "$REQUESTED_RELEASE" \
        || true
    exit 0
fi

[[ "$PREVIOUS_AVAILABLE" == "1" ]] \
    || ops_die "no previous rollback target is available to retire"
[[ \
    "$SLOT" == "$PREVIOUS_SLOT" \
    && "$REQUESTED_RELEASE" == "$PREVIOUS_RELEASE" \
    && "1999wiki-$SLOT" == "$PREVIOUS_PROJECT" \
]] || ops_die "cleanup target must exactly match the recorded previous deployment"
[[ "$SLOT" != "$ACTIVE_SLOT" && "$REQUESTED_RELEASE" != "$ACTIVE_RELEASE" ]] \
    || ops_die "refusing to retire the active deployment"
for active_image in "$ACTIVE_BACKEND_IMAGE" "$ACTIVE_FRONTEND_IMAGE"; do
    [[ \
        "$PREVIOUS_BACKEND_IMAGE" != "$active_image" \
        && "$PREVIOUS_FRONTEND_IMAGE" != "$active_image" \
    ]] || ops_die "recorded previous images are still used by the active deployment"
done

ops_load_snapshot "$PREVIOUS_SLOT" "$PREVIOUS_RELEASE_SNAPSHOT"
[[ \
    "$RELEASE" == "$PREVIOUS_RELEASE" \
    && "$APP_ENV_FILE" == "$PREVIOUS_APP_SNAPSHOT" \
    && "$BACKEND_IMAGE" == "$PREVIOUS_BACKEND_IMAGE" \
    && "$FRONTEND_IMAGE" == "$PREVIOUS_FRONTEND_IMAGE" \
]] || ops_die "recorded previous deployment diverges from its snapshot"
[[ -z "$(ops_compose "$PREVIOUS_PROJECT" ps --status running -q)" ]] \
    || ops_die "recorded previous project must be stopped before retirement"

RETIREMENT_GENERATION="$(ops_helper generation)"
ops_write_retirement "$RETIREMENT_GENERATION"
if [[ "${OPS_TEST_RETIREMENT_CRASH_PHASE:-}" == "after-prepared" ]]; then
    kill -KILL "$$"
fi
ops_reconcile_retirement
printf 'retired previous %s deployment at %s\n' "$SLOT" "$REQUESTED_RELEASE" \
    || true
