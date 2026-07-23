#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
OPS_CONTEXT=cleanup
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

ops_acquire_lock
ops_reconcile_journal
ops_load_active_state
ops_validate_active_consistency

[[ "$SLOT" != "$ACTIVE_SLOT" && "$REQUESTED_RELEASE" != "$ACTIVE_RELEASE" ]] \
    || ops_die "refusing to remove the active project, slot, release, or images"
if [[ "$HAS_PREVIOUS" == "1" ]]; then
    [[ "$SLOT" != "$PREVIOUS_SLOT" && "$REQUESTED_RELEASE" != "$PREVIOUS_RELEASE" ]] \
        || ops_die "refusing to remove the recorded rollback target"
fi

TARGET_RELEASE_SNAPSHOT="${TARGET_RELEASE_SNAPSHOT:-$DEPLOY_STATE_ROOT/snapshots/$REQUESTED_RELEASE/$SLOT/release.env}"
ops_load_snapshot "$SLOT" "$TARGET_RELEASE_SNAPSHOT"
[[ "$RELEASE" == "$REQUESTED_RELEASE" ]] \
    || ops_die "cleanup snapshot does not match the requested release"
PROJECT="1999wiki-$SLOT"
[[ "$PROJECT" != "1999wiki-infra" ]] \
    || ops_die "infra project cleanup is forbidden"

for protected_image in "$ACTIVE_BACKEND_IMAGE" "$ACTIVE_FRONTEND_IMAGE"; do
    [[ "$BACKEND_IMAGE" != "$protected_image" && "$FRONTEND_IMAGE" != "$protected_image" ]] \
        || ops_die "refusing to remove an image used by the active deployment"
done
if [[ "$HAS_PREVIOUS" == "1" ]]; then
    for protected_image in "$PREVIOUS_BACKEND_IMAGE" "$PREVIOUS_FRONTEND_IMAGE"; do
        [[ "$BACKEND_IMAGE" != "$protected_image" && "$FRONTEND_IMAGE" != "$protected_image" ]] \
            || ops_die "refusing to remove an image used by the recorded rollback target"
    done
fi

running_containers="$(ops_compose "$PROJECT" ps --status running -q)"
[[ -z "$running_containers" ]] \
    || ops_die "target app project is not inactive"

ops_compose "$PROJECT" down --remove-orphans
docker image rm "$BACKEND_IMAGE" "$FRONTEND_IMAGE"
printf 'removed inactive %s project and exact %s images\n' "$SLOT" "$RELEASE"
