#!/usr/bin/env bash
set -Eeuo pipefail

OPS_HELPER="${OPS_HELPER:-$SCRIPT_DIR/ops_helper.py}"
REPO_ROOT="${REPO_ROOT:-$(cd -- "$SCRIPT_DIR/../.." && pwd -P)}"
DEPLOY_ROOT="${DEPLOY_ROOT:-/srv/1999wiki}"
DEPLOY_STATE_ROOT="${DEPLOY_STATE_ROOT:-${STATE_DIR:-$DEPLOY_ROOT/deploy-state}}"
STATE_DIR="$DEPLOY_STATE_ROOT"
RELEASES_DIR="${RELEASES_DIR:-$DEPLOY_ROOT/releases}"
APP_COMPOSE_FILE="${APP_COMPOSE_FILE:-$REPO_ROOT/deploy/compose.app.yml}"
INFRA_COMPOSE_FILE="${INFRA_COMPOSE_FILE:-$REPO_ROOT/deploy/compose.infra.yml}"
CADDY_CONFIG="${CADDY_CONFIG:-/etc/caddy/Caddyfile}"
CADDY_ENV_FILE="${CADDY_ENV_FILE:-$DEPLOY_ROOT/protected/caddy.env}"
CADDY_IMPORT_PATH="${CADDY_IMPORT_PATH:-/etc/caddy/active-upstream.caddy}"
ACTIVE_FRAGMENT="${ACTIVE_FRAGMENT:-/etc/caddy/active-upstream.caddy}"
ACTIVE_STATE_FILE="${ACTIVE_STATE_FILE:-$DEPLOY_STATE_ROOT/active.env}"
OPS_JOURNAL_FILE="${OPS_JOURNAL_FILE:-$DEPLOY_STATE_ROOT/transaction.env}"
OPS_RETIREMENT_FILE="${OPS_RETIREMENT_FILE:-$DEPLOY_STATE_ROOT/retirement.env}"
OPS_LOCK_FILE="${OPS_LOCK_FILE:-$DEPLOY_STATE_ROOT/operations.lock}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-http://127.0.0.1}"
CADDY_SERVICE_UID="${CADDY_SERVICE_UID:-}"
CADDY_SERVICE_GIDS="${CADDY_SERVICE_GIDS:-}"
OPS_CONTEXT="${OPS_CONTEXT:-operations}"

ops_die() {
    printf '%s: %s\n' "$OPS_CONTEXT" "$*" >&2
    exit 1
}

ops_helper() {
    python3 "$OPS_HELPER" "$@"
}

ops_require_commands() {
    local command_name
    for command_name in "$@"; do
        command -v "$command_name" >/dev/null 2>&1 \
            || ops_die "required command is unavailable: $command_name"
    done
}

ops_validate_state_root() {
    ops_helper validate-state-root "$DEPLOY_STATE_ROOT"
    OPS_STATE_UID="$(stat -c '%u' "$DEPLOY_STATE_ROOT")"
    OPS_STATE_GID="$(stat -c '%g' "$DEPLOY_STATE_ROOT")"
    export OPS_STATE_UID OPS_STATE_GID
}

ops_acquire_lock() {
    local script_path="${1:-}"
    if (($#)); then
        shift
    fi
    ops_require_commands python3 stat
    ops_validate_state_root
    if [[ -n "${OPS_LOCK_FD:-}" ]]; then
        [[ "$OPS_LOCK_FD" == "9" ]] \
            || ops_die "inherited operations lock descriptor is invalid"
        ops_helper verify-lock \
            "$DEPLOY_STATE_ROOT" \
            "$OPS_LOCK_FILE" \
            "$OPS_LOCK_FD"
        OPS_LOCK_HELD=1
        export OPS_LOCK_HELD OPS_LOCK_FD OPS_LOCK_FILE
        return 0
    fi
    [[ -n "$script_path" ]] \
        || ops_die "secure lock acquisition requires the mutating script path"
    exec python3 "$OPS_HELPER" lock-exec \
        "$DEPLOY_STATE_ROOT" \
        "$OPS_LOCK_FILE" \
        9 \
        -- \
        /bin/bash \
        "$script_path" \
        "$@"
}

ops_load_caddy_env() {
    mapfile -t OPS_CADDY_VALUES < <(ops_helper emit-caddy "$CADDY_ENV_FILE")
    [[ "${#OPS_CADDY_VALUES[@]}" -eq 2 ]] \
        || ops_die "validated Caddy environment is incomplete"
    SITE_ADDRESS="${OPS_CADDY_VALUES[0]}"
    MINIO_PROXY_UPSTREAM="${OPS_CADDY_VALUES[1]}"
    export SITE_ADDRESS MINIO_PROXY_UPSTREAM
}

ops_resolve_caddy_identity() {
    if [[ -z "$CADDY_SERVICE_UID" ]]; then
        CADDY_SERVICE_UID="$(id -u caddy 2>/dev/null)" \
            || ops_die "Caddy service user is unavailable"
    fi
    if [[ -z "$CADDY_SERVICE_GIDS" ]]; then
        CADDY_SERVICE_GIDS="$(
            id -G caddy 2>/dev/null | tr ' ' ','
        )" || ops_die "Caddy service groups are unavailable"
    fi
    [[ "$CADDY_SERVICE_UID" =~ ^[0-9]+$ ]] \
        || ops_die "Caddy service uid is invalid"
    [[ "$CADDY_SERVICE_GIDS" =~ ^[0-9]+(,[0-9]+)*$ ]] \
        || ops_die "Caddy service gids are invalid"
    export CADDY_SERVICE_UID CADDY_SERVICE_GIDS
}

ops_capture_fragment_metadata() {
    ops_resolve_caddy_identity
    mapfile -t OPS_FRAGMENT_META < <(
        ops_helper fragment-metadata \
            "$ACTIVE_FRAGMENT" \
            "$CADDY_SERVICE_UID" \
            "$CADDY_SERVICE_GIDS"
    )
    [[ "${#OPS_FRAGMENT_META[@]}" -eq 3 ]] \
        || ops_die "active Caddy fragment metadata is incomplete"
    FRAGMENT_UID="${OPS_FRAGMENT_META[0]}"
    FRAGMENT_GID="${OPS_FRAGMENT_META[1]}"
    FRAGMENT_MODE="${OPS_FRAGMENT_META[2]}"
    export FRAGMENT_UID FRAGMENT_GID FRAGMENT_MODE
}

ops_install_fragment() {
    local source="$1"
    ops_helper atomic-copy \
        "$source" \
        "$ACTIVE_FRAGMENT" \
        --mode "$FRAGMENT_MODE" \
        --uid "$FRAGMENT_UID" \
        --gid "$FRAGMENT_GID"
}

ops_caddy_reload() {
    ops_load_caddy_env
    caddy reload --config "$CADDY_CONFIG" --adapter caddyfile >/dev/null
}

ops_snapshot_release() {
    local release="$1"
    local slot="$2"
    local release_source="$3"
    local app_source="$4"
    mapfile -t OPS_SNAPSHOT_VALUES < <(
        ops_helper snapshot \
            "$DEPLOY_STATE_ROOT" \
            "$release" \
            "$slot" \
            "$release_source" \
            "$app_source" \
            "$REPO_ROOT"
    )
    ops_assign_snapshot_values
}

ops_load_snapshot() {
    local slot="$1"
    local release_snapshot="$2"
    mapfile -t OPS_SNAPSHOT_VALUES < <(
        ops_helper load-snapshot \
            "$DEPLOY_STATE_ROOT" \
            "$slot" \
            "$release_snapshot"
    )
    ops_assign_snapshot_values
}

ops_assign_snapshot_values() {
    [[ "${#OPS_SNAPSHOT_VALUES[@]}" -eq 8 ]] \
        || ops_die "validated snapshot metadata is incomplete"
    RELEASE_SNAPSHOT="${OPS_SNAPSHOT_VALUES[0]}"
    APP_ENV_FILE="${OPS_SNAPSHOT_VALUES[1]}"
    RELEASE="${OPS_SNAPSHOT_VALUES[2]}"
    BACKEND_IMAGE="${OPS_SNAPSHOT_VALUES[3]}"
    FRONTEND_IMAGE="${OPS_SNAPSHOT_VALUES[4]}"
    BACKEND_PORT="${OPS_SNAPSHOT_VALUES[5]}"
    FRONTEND_PORT="${OPS_SNAPSHOT_VALUES[6]}"
    MEDIA_PUBLIC_BASE_URL="${OPS_SNAPSHOT_VALUES[7]}"
    export \
        RELEASE_SNAPSHOT \
        APP_ENV_FILE \
        RELEASE \
        BACKEND_IMAGE \
        FRONTEND_IMAGE \
        BACKEND_PORT \
        FRONTEND_PORT \
        MEDIA_PUBLIC_BASE_URL
}

ops_compose() {
    local project="$1"
    shift
    docker compose \
        -p "$project" \
        --env-file "$RELEASE_SNAPSHOT" \
        -f "$APP_COMPOSE_FILE" \
        "$@"
}

ops_verify_project_identity() {
    local project="$1"
    local candidate_base_url="$2"
    local attempts="${HEALTH_ATTEMPTS:-30}"
    local interval="${HEALTH_INTERVAL_SECONDS:-5}"
    local attempt
    local status_file
    local health_file
    status_file="$(mktemp "$DEPLOY_STATE_ROOT/.compose-status.XXXXXX")"
    health_file="$(mktemp "$DEPLOY_STATE_ROOT/.candidate-health.XXXXXX")"
    for ((attempt = 1; attempt <= attempts; attempt++)); do
        if ops_compose "$project" ps --format json backend frontend >"$status_file" 2>/dev/null \
            && ops_helper validate-compose-status \
                "$status_file" \
                "$BACKEND_IMAGE" \
                "$FRONTEND_IMAGE" \
            && curl \
                --silent \
                --show-error \
                --fail \
                --connect-timeout 3 \
                --max-time 10 \
                --output "$health_file" \
                "$candidate_base_url/health" \
            && ops_helper validate-health "$health_file"; then
            rm -f -- "$status_file" "$health_file"
            return 0
        fi
        if (( attempt < attempts )); then
            sleep "$interval"
        fi
    done
    rm -f -- "$status_file" "$health_file"
    return 1
}

ops_verify_public_health() {
    local attempts="${VERIFY_ATTEMPTS:-6}"
    local interval="${VERIFY_INTERVAL_SECONDS:-2}"
    local attempt
    local health_file
    health_file="$(mktemp "$DEPLOY_STATE_ROOT/.public-health.XXXXXX")"
    for ((attempt = 1; attempt <= attempts; attempt++)); do
        if curl \
            --silent \
            --show-error \
            --fail \
            --connect-timeout 3 \
            --max-time 10 \
            --output "$health_file" \
            "$PUBLIC_BASE_URL/health" \
            && ops_helper validate-health "$health_file"; then
            rm -f -- "$health_file"
            return 0
        fi
        if (( attempt < attempts )); then
            sleep "$interval"
        fi
    done
    rm -f -- "$health_file"
    return 1
}

ops_load_active_state() {
    [[ -f "$ACTIVE_STATE_FILE" ]] || ops_die "active deployment state is missing"
    mapfile -t OPS_STATE_VALUES < <(
        ops_helper validate-state \
            "$ACTIVE_STATE_FILE" \
            "$DEPLOY_STATE_ROOT" \
            --emit
    )
    [[ "${#OPS_STATE_VALUES[@]}" -eq 20 ]] \
        || ops_die "active deployment state is incomplete"
    STATE_VERSION="${OPS_STATE_VALUES[0]}"
    ACTIVE_GENERATION="${OPS_STATE_VALUES[1]}"
    ACTIVE_SLOT="${OPS_STATE_VALUES[2]}"
    ACTIVE_RELEASE="${OPS_STATE_VALUES[3]}"
    ACTIVE_PROJECT="${OPS_STATE_VALUES[4]}"
    ACTIVE_FRONTEND_PORT="${OPS_STATE_VALUES[5]}"
    ACTIVE_RELEASE_SNAPSHOT="${OPS_STATE_VALUES[6]}"
    ACTIVE_APP_SNAPSHOT="${OPS_STATE_VALUES[7]}"
    ACTIVE_BACKEND_IMAGE="${OPS_STATE_VALUES[8]}"
    ACTIVE_FRONTEND_IMAGE="${OPS_STATE_VALUES[9]}"
    PREVIOUS_AVAILABLE="${OPS_STATE_VALUES[10]}"
    PREVIOUS_SLOT="${OPS_STATE_VALUES[11]}"
    PREVIOUS_RELEASE="${OPS_STATE_VALUES[12]}"
    PREVIOUS_PROJECT="${OPS_STATE_VALUES[13]}"
    PREVIOUS_FRONTEND_PORT="${OPS_STATE_VALUES[14]}"
    PREVIOUS_RELEASE_SNAPSHOT="${OPS_STATE_VALUES[15]}"
    PREVIOUS_APP_SNAPSHOT="${OPS_STATE_VALUES[16]}"
    PREVIOUS_BACKEND_IMAGE="${OPS_STATE_VALUES[17]}"
    PREVIOUS_FRONTEND_IMAGE="${OPS_STATE_VALUES[18]}"
    PREVIOUS_FRAGMENT_BACKUP="${OPS_STATE_VALUES[19]}"
    export \
        STATE_VERSION \
        ACTIVE_GENERATION \
        ACTIVE_SLOT \
        ACTIVE_RELEASE \
        ACTIVE_PROJECT \
        ACTIVE_FRONTEND_PORT \
        ACTIVE_RELEASE_SNAPSHOT \
        ACTIVE_APP_SNAPSHOT \
        ACTIVE_BACKEND_IMAGE \
        ACTIVE_FRONTEND_IMAGE \
        PREVIOUS_AVAILABLE \
        PREVIOUS_SLOT \
        PREVIOUS_RELEASE \
        PREVIOUS_PROJECT \
        PREVIOUS_FRONTEND_PORT \
        PREVIOUS_RELEASE_SNAPSHOT \
        PREVIOUS_APP_SNAPSHOT \
        PREVIOUS_BACKEND_IMAGE \
        PREVIOUS_FRONTEND_IMAGE \
        PREVIOUS_FRAGMENT_BACKUP
}

ops_validate_active_consistency() {
    ops_helper validate-consistency \
        "$ACTIVE_STATE_FILE" \
        "$ACTIVE_FRAGMENT" \
        "$DEPLOY_STATE_ROOT"
}

ops_write_retirement() {
    local generation="$1"
    {
        printf 'RETIREMENT_VERSION=1\n'
        printf 'GENERATION=%s\n' "$generation"
        printf 'PHASE=prepared\n'
        printf 'ACTIVE_GENERATION=%s\n' "$ACTIVE_GENERATION"
        printf 'SLOT=%s\n' "$PREVIOUS_SLOT"
        printf 'RELEASE=%s\n' "$PREVIOUS_RELEASE"
        printf 'PROJECT=%s\n' "$PREVIOUS_PROJECT"
        printf 'RELEASE_SNAPSHOT=%s\n' "$PREVIOUS_RELEASE_SNAPSHOT"
        printf 'APP_SNAPSHOT=%s\n' "$PREVIOUS_APP_SNAPSHOT"
        printf 'BACKEND_IMAGE=%s\n' "$PREVIOUS_BACKEND_IMAGE"
        printf 'FRONTEND_IMAGE=%s\n' "$PREVIOUS_FRONTEND_IMAGE"
        printf 'FRAGMENT_BACKUP=%s\n' "$PREVIOUS_FRAGMENT_BACKUP"
    } | ops_helper atomic-stdin \
        "$OPS_RETIREMENT_FILE" \
        600 \
        "$OPS_STATE_UID" \
        "$OPS_STATE_GID"
    ops_helper validate-retirement \
        "$OPS_RETIREMENT_FILE" \
        "$DEPLOY_STATE_ROOT"
}

ops_load_retirement() {
    mapfile -t OPS_RETIREMENT_VALUES < <(
        ops_helper validate-retirement \
            "$OPS_RETIREMENT_FILE" \
            "$DEPLOY_STATE_ROOT" \
            --emit
    )
    [[ "${#OPS_RETIREMENT_VALUES[@]}" -eq 12 ]] \
        || ops_die "retirement journal is incomplete"
    RETIREMENT_GENERATION="${OPS_RETIREMENT_VALUES[1]}"
    RETIREMENT_PHASE="${OPS_RETIREMENT_VALUES[2]}"
    RETIREMENT_ACTIVE_GENERATION="${OPS_RETIREMENT_VALUES[3]}"
    RETIREMENT_SLOT="${OPS_RETIREMENT_VALUES[4]}"
    RETIREMENT_RELEASE="${OPS_RETIREMENT_VALUES[5]}"
    RETIREMENT_PROJECT="${OPS_RETIREMENT_VALUES[6]}"
    RETIREMENT_RELEASE_SNAPSHOT="${OPS_RETIREMENT_VALUES[7]}"
    RETIREMENT_APP_SNAPSHOT="${OPS_RETIREMENT_VALUES[8]}"
    RETIREMENT_BACKEND_IMAGE="${OPS_RETIREMENT_VALUES[9]}"
    RETIREMENT_FRONTEND_IMAGE="${OPS_RETIREMENT_VALUES[10]}"
    RETIREMENT_FRAGMENT_BACKUP="${OPS_RETIREMENT_VALUES[11]}"
}

ops_retirement_matches_previous() {
    [[ \
        "$PREVIOUS_AVAILABLE" == "1" \
        && "$ACTIVE_GENERATION" == "$RETIREMENT_ACTIVE_GENERATION" \
        && "$PREVIOUS_SLOT" == "$RETIREMENT_SLOT" \
        && "$PREVIOUS_RELEASE" == "$RETIREMENT_RELEASE" \
        && "$PREVIOUS_PROJECT" == "$RETIREMENT_PROJECT" \
        && "$PREVIOUS_RELEASE_SNAPSHOT" == "$RETIREMENT_RELEASE_SNAPSHOT" \
        && "$PREVIOUS_APP_SNAPSHOT" == "$RETIREMENT_APP_SNAPSHOT" \
        && "$PREVIOUS_BACKEND_IMAGE" == "$RETIREMENT_BACKEND_IMAGE" \
        && "$PREVIOUS_FRONTEND_IMAGE" == "$RETIREMENT_FRONTEND_IMAGE" \
        && "$PREVIOUS_FRAGMENT_BACKUP" == "$RETIREMENT_FRAGMENT_BACKUP" \
    ]]
}

ops_exact_image_present() {
    local image="$1"
    local output
    output="$(
        docker image ls \
            --format '{{.Repository}}:{{.Tag}}' \
            "$image"
    )" || return 2
    if [[ -z "$output" ]]; then
        return 1
    fi
    [[ "$output" == "$image" ]] \
        || ops_die "retirement image query returned an unexpected reference"
}

ops_remove_retirement_resources() {
    ops_load_snapshot "$RETIREMENT_SLOT" "$RETIREMENT_RELEASE_SNAPSHOT"
    [[ \
        "$RELEASE" == "$RETIREMENT_RELEASE" \
        && "$APP_ENV_FILE" == "$RETIREMENT_APP_SNAPSHOT" \
        && "$BACKEND_IMAGE" == "$RETIREMENT_BACKEND_IMAGE" \
        && "$FRONTEND_IMAGE" == "$RETIREMENT_FRONTEND_IMAGE" \
    ]] || ops_die "retirement snapshot no longer matches the journal"
    ops_compose "$RETIREMENT_PROJECT" down --remove-orphans
    local image
    local present_status
    for image in "$RETIREMENT_BACKEND_IMAGE" "$RETIREMENT_FRONTEND_IMAGE"; do
        set +e
        ops_exact_image_present "$image"
        present_status=$?
        set -e
        if (( present_status == 0 )); then
            docker image rm "$image"
        elif (( present_status != 1 )); then
            ops_die "could not reconcile retirement image presence"
        fi
    done
}

ops_verify_retirement_resources_absent() {
    ops_load_snapshot "$RETIREMENT_SLOT" "$RETIREMENT_RELEASE_SNAPSHOT"
    [[ -z "$(ops_compose "$RETIREMENT_PROJECT" ps -a -q)" ]] \
        || ops_die "retirement project still has containers after removal phase"
    local image
    local present_status
    for image in "$RETIREMENT_BACKEND_IMAGE" "$RETIREMENT_FRONTEND_IMAGE"; do
        set +e
        ops_exact_image_present "$image"
        present_status=$?
        set -e
        if (( present_status == 0 )); then
            ops_die "retirement image reappeared after removal phase"
        elif (( present_status != 1 )); then
            ops_die "could not verify retired image absence"
        fi
    done
}

ops_commit_retired_state() {
    local state_candidate
    state_candidate="$(mktemp "$DEPLOY_STATE_ROOT/.retired-state.XXXXXX")"
    {
        printf 'STATE_VERSION=3\n'
        printf 'GENERATION=%s\n' "$RETIREMENT_GENERATION"
        printf 'ACTIVE_SLOT=%s\n' "$ACTIVE_SLOT"
        printf 'ACTIVE_RELEASE=%s\n' "$ACTIVE_RELEASE"
        printf 'ACTIVE_PROJECT=%s\n' "$ACTIVE_PROJECT"
        printf 'ACTIVE_FRONTEND_PORT=%s\n' "$ACTIVE_FRONTEND_PORT"
        printf 'ACTIVE_RELEASE_SNAPSHOT=%s\n' "$ACTIVE_RELEASE_SNAPSHOT"
        printf 'ACTIVE_APP_SNAPSHOT=%s\n' "$ACTIVE_APP_SNAPSHOT"
        printf 'ACTIVE_BACKEND_IMAGE=%s\n' "$ACTIVE_BACKEND_IMAGE"
        printf 'ACTIVE_FRONTEND_IMAGE=%s\n' "$ACTIVE_FRONTEND_IMAGE"
        printf 'PREVIOUS_AVAILABLE=0\n'
        printf 'PREVIOUS_SLOT=\n'
        printf 'PREVIOUS_RELEASE=\n'
        printf 'PREVIOUS_PROJECT=\n'
        printf 'PREVIOUS_FRONTEND_PORT=\n'
        printf 'PREVIOUS_RELEASE_SNAPSHOT=\n'
        printf 'PREVIOUS_APP_SNAPSHOT=\n'
        printf 'PREVIOUS_BACKEND_IMAGE=\n'
        printf 'PREVIOUS_FRONTEND_IMAGE=\n'
        printf 'PREVIOUS_FRAGMENT_BACKUP=\n'
    } | ops_helper atomic-stdin \
        "$state_candidate" \
        600 \
        "$OPS_STATE_UID" \
        "$OPS_STATE_GID"
    ops_helper validate-state "$state_candidate" "$DEPLOY_STATE_ROOT"
    ops_helper atomic-copy \
        "$state_candidate" \
        "$ACTIVE_STATE_FILE" \
        --mode 600 \
        --uid "$OPS_STATE_UID" \
        --gid "$OPS_STATE_GID"
    rm -f -- "$state_candidate"
}

ops_reconcile_retirement() {
    [[ -e "$OPS_RETIREMENT_FILE" ]] || return 0
    ops_load_retirement
    ops_load_active_state
    ops_validate_active_consistency

    if [[ "$RETIREMENT_PHASE" == "state_committed" ]] \
        || [[ \
            "$ACTIVE_GENERATION" == "$RETIREMENT_GENERATION" \
            && "$PREVIOUS_AVAILABLE" == "0" \
        ]]; then
        [[ \
            "$ACTIVE_GENERATION" == "$RETIREMENT_GENERATION" \
            && "$PREVIOUS_AVAILABLE" == "0" \
        ]] || ops_die "retirement committed phase diverges from active state"
        if ! ops_helper durable-unlink "$OPS_RETIREMENT_FILE"; then
            return 1
        fi
        ops_helper durable-unlink "$RETIREMENT_FRAGMENT_BACKUP" \
            || printf '%s: warning: retired fragment backup remains\n' "$OPS_CONTEXT" >&2
        return 0
    fi

    ops_retirement_matches_previous \
        || ops_die "retirement journal diverges from the recorded previous target"
    if [[ "$RETIREMENT_PHASE" == "prepared" ]]; then
        ops_remove_retirement_resources
        ops_helper mark-retirement \
            "$OPS_RETIREMENT_FILE" \
            "$DEPLOY_STATE_ROOT" \
            resources_removed
        RETIREMENT_PHASE=resources_removed
        if [[ "${OPS_TEST_RETIREMENT_CRASH_PHASE:-}" == "after-resources-removed" ]]; then
            kill -KILL "$$"
        fi
    fi
    if [[ "$RETIREMENT_PHASE" == "resources_removed" ]]; then
        ops_verify_retirement_resources_absent
        ops_commit_retired_state
        ops_helper mark-retirement \
            "$OPS_RETIREMENT_FILE" \
            "$DEPLOY_STATE_ROOT" \
            state_committed
        if [[ "${OPS_TEST_RETIREMENT_CRASH_PHASE:-}" == "after-state-commit" ]]; then
            kill -KILL "$$"
        fi
        if ! ops_helper durable-unlink "$OPS_RETIREMENT_FILE"; then
            return 1
        fi
        ops_helper durable-unlink "$RETIREMENT_FRAGMENT_BACKUP" \
            || printf '%s: warning: retired fragment backup remains\n' "$OPS_CONTEXT" >&2
    fi
}

ops_reconcile_operations() {
    ops_reconcile_journal
    ops_reconcile_retirement
}

ops_write_journal() {
    local generation="$1"
    local operation="$2"
    local phase="$3"
    local old_fragment="$4"
    local old_state_present="$5"
    local old_state="$6"
    {
        printf 'JOURNAL_VERSION=1\n'
        printf 'GENERATION=%s\n' "$generation"
        printf 'OPERATION=%s\n' "$operation"
        printf 'PHASE=%s\n' "$phase"
        printf 'OLD_FRAGMENT_BACKUP=%s\n' "$old_fragment"
        printf 'OLD_FRAGMENT_UID=%s\n' "$FRAGMENT_UID"
        printf 'OLD_FRAGMENT_GID=%s\n' "$FRAGMENT_GID"
        printf 'OLD_FRAGMENT_MODE=%s\n' "$FRAGMENT_MODE"
        printf 'OLD_STATE_PRESENT=%s\n' "$old_state_present"
        printf 'OLD_STATE_BACKUP=%s\n' "$old_state"
        printf 'NEW_STATE_GENERATION=%s\n' "$generation"
    } | ops_helper atomic-stdin \
        "$OPS_JOURNAL_FILE" \
        600 \
        "$OPS_STATE_UID" \
        "$OPS_STATE_GID"
    ops_helper validate-journal "$OPS_JOURNAL_FILE" "$DEPLOY_STATE_ROOT"
}

ops_begin_transaction() {
    local operation="$1"
    [[ ! -e "$OPS_JOURNAL_FILE" ]] \
        || ops_die "an unreconciled transaction journal already exists"
    TRANSACTION_GENERATION="$(ops_helper generation)"
    TRANSACTION_OLD_FRAGMENT="$DEPLOY_STATE_ROOT/tx-$TRANSACTION_GENERATION-old-fragment.caddy"
    TRANSACTION_OLD_STATE=
    TRANSACTION_OLD_STATE_PRESENT=0
    ops_capture_fragment_metadata
    ops_helper atomic-copy \
        "$ACTIVE_FRAGMENT" \
        "$TRANSACTION_OLD_FRAGMENT" \
        --preserve
    if [[ -f "$ACTIVE_STATE_FILE" ]]; then
        TRANSACTION_OLD_STATE="$DEPLOY_STATE_ROOT/tx-$TRANSACTION_GENERATION-old-state.env"
        ops_helper atomic-copy \
            "$ACTIVE_STATE_FILE" \
            "$TRANSACTION_OLD_STATE" \
            --preserve
        TRANSACTION_OLD_STATE_PRESENT=1
    fi
    ops_write_journal \
        "$TRANSACTION_GENERATION" \
        "$operation" \
        prepared \
        "$TRANSACTION_OLD_FRAGMENT" \
        "$TRANSACTION_OLD_STATE_PRESENT" \
        "$TRANSACTION_OLD_STATE"
    export \
        TRANSACTION_GENERATION \
        TRANSACTION_OLD_FRAGMENT \
        TRANSACTION_OLD_STATE \
        TRANSACTION_OLD_STATE_PRESENT
}

ops_mark_transaction_phase() {
    local phase="$1"
    ops_helper mark-journal \
        "$OPS_JOURNAL_FILE" \
        "$DEPLOY_STATE_ROOT" \
        "$phase"
}

ops_load_journal() {
    mapfile -t OPS_JOURNAL_VALUES < <(
        ops_helper validate-journal \
            "$OPS_JOURNAL_FILE" \
            "$DEPLOY_STATE_ROOT" \
            --emit
    )
    [[ "${#OPS_JOURNAL_VALUES[@]}" -eq 11 ]] \
        || ops_die "transaction journal is incomplete"
    JOURNAL_GENERATION="${OPS_JOURNAL_VALUES[1]}"
    JOURNAL_PHASE="${OPS_JOURNAL_VALUES[3]}"
    JOURNAL_OLD_FRAGMENT="${OPS_JOURNAL_VALUES[4]}"
    JOURNAL_OLD_STATE_PRESENT="${OPS_JOURNAL_VALUES[8]}"
    JOURNAL_OLD_STATE="${OPS_JOURNAL_VALUES[9]}"
}

ops_reconcile_journal() {
    [[ -e "$OPS_JOURNAL_FILE" ]] || return 0
    ops_load_journal
    ops_load_caddy_env
    if [[ "$JOURNAL_PHASE" == "state_committed" ]]; then
        ops_load_active_state
        [[ "$ACTIVE_GENERATION" == "$JOURNAL_GENERATION" ]] \
            || ops_die "committed journal diverges from active state generation"
        ops_validate_active_consistency
        if [[ "$PREVIOUS_AVAILABLE" == "1" ]]; then
            [[ "$PREVIOUS_FRAGMENT_BACKUP" == "$JOURNAL_OLD_FRAGMENT" ]] \
                || ops_die "committed journal fragment is not the rollback backup"
        fi
        if ! ops_helper durable-unlink "$OPS_JOURNAL_FILE"; then
            return 1
        fi
        local cleanup_pending=0
        if [[ -n "$JOURNAL_OLD_STATE" ]] \
            && ! ops_helper durable-unlink "$JOURNAL_OLD_STATE"; then
            cleanup_pending=1
        fi
        if [[ "$PREVIOUS_AVAILABLE" == "0" ]]; then
            if ! ops_helper durable-unlink "$JOURNAL_OLD_FRAGMENT"; then
                cleanup_pending=1
            fi
        fi
        return "$cleanup_pending"
    fi

    ops_helper atomic-copy \
        "$JOURNAL_OLD_FRAGMENT" \
        "$ACTIVE_FRAGMENT" \
        --preserve
    if [[ "$JOURNAL_OLD_STATE_PRESENT" == "1" ]]; then
        ops_helper atomic-copy \
            "$JOURNAL_OLD_STATE" \
            "$ACTIVE_STATE_FILE" \
            --preserve
    else
        ops_helper durable-unlink "$ACTIVE_STATE_FILE"
    fi
    ops_caddy_reload
    if [[ "$JOURNAL_OLD_STATE_PRESENT" == "1" ]]; then
        ops_validate_active_consistency
    fi
    if ! ops_helper durable-unlink "$OPS_JOURNAL_FILE"; then
        return 1
    fi
    local cleanup_pending=0
    if [[ "$JOURNAL_OLD_STATE_PRESENT" == "1" ]] \
        && ! ops_helper durable-unlink "$JOURNAL_OLD_STATE"; then
        cleanup_pending=1
    fi
    if ! ops_helper durable-unlink "$JOURNAL_OLD_FRAGMENT"; then
        cleanup_pending=1
    fi
    return "$cleanup_pending"
}

ops_install_transaction_traffic() {
    local candidate_fragment="$1"
    ops_install_fragment "$candidate_fragment"
    ops_caddy_reload
    ops_mark_transaction_phase traffic_installed
}

ops_commit_transaction_state() {
    local state_candidate="$1"
    ops_helper validate-state \
        "$state_candidate" \
        "$DEPLOY_STATE_ROOT"
    ops_helper atomic-copy \
        "$state_candidate" \
        "$ACTIVE_STATE_FILE" \
        --mode 600 \
        --uid "$OPS_STATE_UID" \
        --gid "$OPS_STATE_GID"
    ops_mark_transaction_phase state_committed
    if [[ "${OPS_TEST_CRASH_PHASE:-}" == "after-state-commit" ]]; then
        kill -KILL "$$"
    fi
}

ops_finalize_committed_transaction() {
    if ! ops_reconcile_journal; then
        printf '%s: warning: committed transaction housekeeping remains pending\n' \
            "$OPS_CONTEXT" >&2
        return 1
    fi
    return 0
}

ops_candidate_is_committed() (
    local expected_slot="$1"
    local expected_project="$2"
    local expected_release_snapshot="$3"
    [[ -f "$ACTIVE_STATE_FILE" ]] || return 1
    ops_load_active_state
    ops_validate_active_consistency
    [[ \
        "$ACTIVE_SLOT" == "$expected_slot" \
        && "$ACTIVE_PROJECT" == "$expected_project" \
        && "$ACTIVE_RELEASE_SNAPSHOT" == "$expected_release_snapshot" \
    ]]
)

ops_remove_orphan_transaction_backups() {
    local candidate
    local referenced_previous=
    local referenced_journal_fragment=
    local referenced_journal_state=
    if [[ -f "$ACTIVE_STATE_FILE" ]]; then
        ops_load_active_state
        if [[ "$PREVIOUS_AVAILABLE" == "1" ]]; then
            referenced_previous="$PREVIOUS_FRAGMENT_BACKUP"
        fi
    fi
    if [[ -f "$OPS_JOURNAL_FILE" ]]; then
        ops_load_journal
        referenced_journal_fragment="$JOURNAL_OLD_FRAGMENT"
        referenced_journal_state="$JOURNAL_OLD_STATE"
    fi
    while IFS= read -r candidate; do
        [[ -n "$candidate" ]] || continue
        if [[ \
            "$candidate" != "$referenced_previous" \
            && "$candidate" != "$referenced_journal_fragment" \
            && "$candidate" != "$referenced_journal_state" \
        ]]; then
            ops_helper durable-unlink "$candidate"
        fi
    done < <(
        find "$DEPLOY_STATE_ROOT" \
            -maxdepth 1 \
            -type f \
            \( \
                -name 'tx-gen-*-old-fragment.caddy' \
                -o -name 'tx-gen-*-old-state.env' \
            \) \
            -print
    )
}

ops_test_crash_before_state_commit() {
    if [[ "${OPS_TEST_CRASH_PHASE:-}" == "before-state-commit" ]]; then
        kill -KILL "$$"
    fi
}

ops_recover_failed_transaction() {
    local status="$1"
    if (( status != 0 )) && [[ -f "$OPS_JOURNAL_FILE" ]]; then
        set +e
        ops_reconcile_journal
        local reconcile_status=$?
        set -e
        if (( reconcile_status != 0 )); then
            printf '%s: CRITICAL: transaction reconciliation failed\n' "$OPS_CONTEXT" >&2
        fi
    fi
    return "$status"
}
