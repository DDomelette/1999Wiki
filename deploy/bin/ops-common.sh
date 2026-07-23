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
    ops_require_commands flock python3 stat
    ops_validate_state_root
    if [[ "${OPS_LOCK_HELD:-0}" == "1" ]]; then
        [[ "${OPS_LOCK_FD:-}" == "9" ]] \
            || ops_die "inherited operations lock descriptor is invalid"
        [[ -e "/proc/$$/fd/9" ]] \
            || ops_die "inherited operations lock descriptor is closed"
        local inherited_target
        inherited_target="$(readlink -f "/proc/$$/fd/9")"
        [[ "$inherited_target" == "$(readlink -f "$OPS_LOCK_FILE")" ]] \
            || ops_die "inherited operations lock does not match state root"
        return 0
    fi
    exec 9>"$OPS_LOCK_FILE"
    flock -n 9 || ops_die "another production operation holds the global lock"
    OPS_LOCK_HELD=1
    OPS_LOCK_FD=9
    export OPS_LOCK_HELD OPS_LOCK_FD OPS_LOCK_FILE
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
    HAS_PREVIOUS="${OPS_STATE_VALUES[10]}"
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
        HAS_PREVIOUS \
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
    [[ "${#OPS_JOURNAL_VALUES[@]}" -eq 8 ]] \
        || ops_die "transaction journal is incomplete"
    JOURNAL_GENERATION="${OPS_JOURNAL_VALUES[1]}"
    JOURNAL_PHASE="${OPS_JOURNAL_VALUES[3]}"
    JOURNAL_OLD_FRAGMENT="${OPS_JOURNAL_VALUES[4]}"
    JOURNAL_OLD_STATE_PRESENT="${OPS_JOURNAL_VALUES[5]}"
    JOURNAL_OLD_STATE="${OPS_JOURNAL_VALUES[6]}"
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
        if [[ "$HAS_PREVIOUS" == "1" ]]; then
            [[ "$PREVIOUS_FRAGMENT_BACKUP" == "$JOURNAL_OLD_FRAGMENT" ]] \
                || ops_die "committed journal fragment is not the rollback backup"
        else
            ops_helper durable-unlink "$JOURNAL_OLD_FRAGMENT"
        fi
        ops_helper durable-unlink "$OPS_JOURNAL_FILE"
        [[ -z "$JOURNAL_OLD_STATE" ]] \
            || ops_helper durable-unlink "$JOURNAL_OLD_STATE"
        return 0
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
        ops_helper durable-unlink "$JOURNAL_OLD_STATE"
    fi
    ops_helper durable-unlink "$OPS_JOURNAL_FILE"
    ops_helper durable-unlink "$JOURNAL_OLD_FRAGMENT"
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
    ops_helper durable-unlink "$OPS_JOURNAL_FILE"
    [[ -z "$TRANSACTION_OLD_STATE" ]] \
        || ops_helper durable-unlink "$TRANSACTION_OLD_STATE"
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
