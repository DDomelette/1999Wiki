from __future__ import annotations

import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy"
BIN = DEPLOY / "bin"
SCRIPTS = (
    "preflight.sh",
    "deploy.sh",
    "switch.sh",
    "rollback.sh",
    "smoke-test.sh",
    "cleanup.sh",
)
OPS_COMMON = BIN / "ops-common.sh"
OPS_HELPER = BIN / "ops_helper.py"
REQUIRED_FILES = (
    DEPLOY / "Caddyfile",
    DEPLOY / "caddy" / "active-upstream.caddy.example",
    DEPLOY / "env" / "caddy.env.example",
    OPS_COMMON,
    OPS_HELPER,
    *(BIN / name for name in SCRIPTS),
)
FORBIDDEN_OPERATIONS = (
    "docker compose down -v",
    "docker system prune",
    "docker volume prune",
    "docker inspect",
)
SCRIPT_TEST_IMAGE = "python:3.11.15-slim-bookworm"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing required deployment control: {path.relative_to(ROOT)}"
    return path.read_text(encoding="utf-8")


def _run_linux_harness(tmp_path: Path, body: str) -> subprocess.CompletedProcess[str]:
    docker = shutil.which("docker")
    assert docker, "Docker CLI is required for deployment script behavior tests"
    harness = tmp_path / "harness.sh"
    harness.write_text(
        textwrap.dedent(body).replace("\r\n", "\n"),
        encoding="utf-8",
        newline="\n",
    )
    return subprocess.run(
        [
            docker,
            "run",
            "--rm",
            "-v",
            f"{ROOT}:/repo:ro",
            "-v",
            f"{tmp_path}:/host-case:ro",
            "--entrypoint",
            "/bin/bash",
            SCRIPT_TEST_IMAGE,
            "/host-case/harness.sh",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _preflight_harness(customize: str = "") -> str:
    return f"""\
        set -Eeuo pipefail
        root=/tmp/1999wiki
        stub=/tmp/stub
        calls=/tmp/calls
        mkdir -p "$root/protected" "$root/releases/sha-abcdef0" \
            "$root/deploy-state" "$root/rag-artifacts" "$stub"
        printf '%s\\n' '{{"schema_version":"evb.active-build/v1"}}' \
            >"$root/rag-artifacts/active_build.v1.json"
        cp /repo/deploy/Caddyfile "$root/Caddyfile"
        cp /repo/deploy/caddy/active-upstream.caddy.example "$root/active.caddy"
        chmod 644 "$root/active.caddy"
        : >"$calls"
        cat >"$root/protected/app.env" <<'EOF'
        APP_ENV=production
        MILVUS_URI=http://standalone:19530
        MILVUS_DB_NAME=wiki
        MILVUS_COLLECTION_NAME=collection
        MINIO_ENDPOINT=minio:9000
        MINIO_ACCESS_KEY=minio-user-sentinel
        MINIO_SECRET_KEY=minio-secret-sentinel
        MINIO_BUCKET=assets
        MEDIA_PUBLIC_BASE_URL=/media
        MYSQL_HOST=mysql
        MYSQL_PORT=3306
        MYSQL_DATABASE=wiki
        MYSQL_USER=mysql-user-sentinel
        MYSQL_PASSWORD=mysql-secret-sentinel
        DEEPSEEK_API_KEY=deepseek-sentinel
        SILICONFLOW_API_KEY=siliconflow-sentinel
        HUIJI_PROCESSED_ROOT=/runtime/rag/huiji
        EOF
        cat >"$root/protected/infra.env" <<'EOF'
        MYSQL_ROOT_PASSWORD=root-sentinel
        MYSQL_USER=mysql-user-sentinel
        MYSQL_PASSWORD=mysql-secret-sentinel
        MINIO_ROOT_USER=minio-user-sentinel
        MINIO_ROOT_PASSWORD=minio-secret-sentinel
        EOF
        cat >"$root/protected/caddy.env" <<'EOF'
        SITE_ADDRESS=:80
        MINIO_PROXY_UPSTREAM=127.0.0.1:19000
        EOF
        cat >"$root/releases/sha-abcdef0/blue.env" <<'EOF'
        BACKEND_IMAGE=ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0
        FRONTEND_IMAGE=ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0
        BACKEND_PORT=18000
        FRONTEND_PORT=18080
        EOF
        chmod 600 "$root/protected/app.env" "$root/protected/infra.env" \
            "$root/protected/caddy.env" \
            "$root/releases/sha-abcdef0/blue.env"
        chmod 700 "$root/deploy-state"
        cat >"$stub/docker" <<'EOF'
        #!/usr/bin/env bash
        set -Eeuo pipefail
        printf '%s\\n' "$*" >>/tmp/calls
        if [[ "$1" == "compose" && "$2" == "version" ]]; then
            exit 0
        fi
        if [[ "$1" == "network" && "$2" == "inspect" ]]; then
            printf '1999wiki-infra\\n'
            exit 0
        fi
        if [[ " $* " == *" ps --format json "* ]]; then
            printf '[{{"State":"running","Health":"healthy"}}]\\n'
            exit 0
        fi
        if [[ " $* " == *" ps -a -q "* ]]; then
            exit 0
        fi
        exit 0
        EOF
        cat >"$stub/caddy" <<'EOF'
        #!/usr/bin/env bash
        set -Eeuo pipefail
        printf 'caddy %s\\n' "$*" >>/tmp/calls
        [[ "${{SITE_ADDRESS:-}}" == ":80" ]]
        [[ "${{MINIO_PROXY_UPSTREAM:-}}" == "127.0.0.1:19000" ]]
        exit 0
        EOF
        cat >"$stub/curl" <<'EOF'
        #!/usr/bin/env bash
        exit 0
        EOF
        cat >"$stub/df" <<'EOF'
        #!/usr/bin/env bash
        printf 'Filesystem 1024-blocks Used Available Capacity Mounted on\\n'
        printf 'stub 20000000 1 10000000 1%% /tmp\\n'
        EOF
        chmod +x "$stub/docker" "$stub/caddy" "$stub/curl" "$stub/df"
        {textwrap.dedent(customize)}
        set +e
        output="$(
            PATH="$stub:$PATH" \
            DEPLOY_ROOT="$root" \
            PROTECTED_ENV_DIR="$root/protected" \
            RELEASES_DIR="$root/releases" \
            STATE_DIR="$root/deploy-state" \
            RAG_ROOT="$root/rag-artifacts" \
            APP_COMPOSE_FILE=/repo/deploy/compose.app.yml \
            INFRA_COMPOSE_FILE=/repo/deploy/compose.infra.yml \
            CADDY_CONFIG="$root/Caddyfile" \
            ACTIVE_FRAGMENT="$root/active.caddy" \
            APP_ENV_FILE="${{APP_ENV_FILE_OVERRIDE:-$root/protected/app.env}}" \
            INFRA_ENV_FILE="$root/protected/infra.env" \
            CADDY_ENV_FILE="$root/protected/caddy.env" \
            CADDY_SERVICE_UID=0 \
            CADDY_SERVICE_GIDS=0 \
            RELEASE_ENV_FILE="$root/releases/sha-abcdef0/blue.env" \
            /bin/bash /repo/deploy/bin/preflight.sh sha-abcdef0 blue 2>&1
        )"
        status=$?
        set -e
        printf '%s\\n__STATUS=%s\\n' "$output" "$status"
        printf '%s\\n' '__CALLS__'
        sed -n '1,200p' "$calls"
    """


def _smoke_harness() -> str:
    return """\
        set -Eeuo pipefail
        stub=/tmp/stub
        calls=/tmp/calls
        mkdir -p "$stub"
        : >"$calls"
        cat >/tmp/app.env <<'EOF'
        APP_ENV=production
        MILVUS_URI=http://standalone:19530
        MILVUS_DB_NAME=wiki
        MILVUS_COLLECTION_NAME=collection
        MINIO_ENDPOINT=minio:9000
        MINIO_ACCESS_KEY=x
        MINIO_SECRET_KEY=x
        MINIO_BUCKET=assets
        MEDIA_PUBLIC_BASE_URL=/media
        MYSQL_HOST=mysql
        MYSQL_PORT=3306
        MYSQL_DATABASE=wiki
        MYSQL_USER=x
        MYSQL_PASSWORD=x
        DEEPSEEK_API_KEY=x
        SILICONFLOW_API_KEY=x
        HUIJI_PROCESSED_ROOT=/runtime/rag/huiji
        EOF
        cat >"$stub/curl" <<'EOF'
        #!/usr/bin/env bash
        set -Eeuo pipefail
        output=/dev/stdout
        headers=
        write_out=
        location=false
        url=
        while (($#)); do
            case "$1" in
                -o|--output)
                    output="$2"
                    shift 2
                    ;;
                --dump-header)
                    headers="$2"
                    shift 2
                    ;;
                --write-out)
                    write_out="$2"
                    shift 2
                    ;;
                --location)
                    location=true
                    shift
                    ;;
                http://*|https://*)
                    url="$1"
                    shift
                    ;;
                *)
                    shift
                    ;;
            esac
        done
        [[ "$location" == "true" ]] || exit 88
        printf '%s\\n' "$url" >>/tmp/calls
        content_type=application/json
        case "$url" in
            http://127.0.0.1:18080/)
                content_type=text/html
                printf '<!doctype html><div id="root"></div><script src="/assets/app-ABCDEF12.js"></script>' >"$output"
                ;;
            http://127.0.0.1:18080/assets/app-ABCDEF12.js)
                content_type=application/javascript
                printf 'console.log("formal build");' >"$output"
                ;;
            http://127.0.0.1:18080/health)
                printf '%s' '{"status":"ok","vectorstore_loaded":true,"provenance_status":"pass","llm_ready":true}' >"$output"
                ;;
            http://127.0.0.1:18080/api/wiki/health)
                printf '%s' '{"ready":true,"pageCount":1,"mediaLinkCount":1}' >"$output"
                ;;
            'http://127.0.0.1:18080/api/wiki/pages?limit=1')
                printf '%s' '{"items":[{"pageId":"fixture-page","title":"Fixture"}]}' >"$output"
                ;;
            http://127.0.0.1:18080/api/wiki/pages/fixture-page)
                printf '%s' '{"pageId":"fixture-page","mediaLinks":[]}' >"$output"
                ;;
            http://127.0.0.1:18080/api/ask)
                printf '%s' '{"answer":"ok","media":[{"url":"/media/reverse1999-assets/fixture.webp"}]}' >"$output"
                ;;
            http://127.0.0.1:18080/api/ask/stream)
                printf 'event: sources\\ndata: {"sources":[]}\\n\\nevent: done\\ndata: {"answer":"ok"}\\n\\n' >"$output"
                ;;
            http://127.0.0.1/media/reverse1999-assets/fixture.webp)
                content_type=image/webp
                printf 'fixture-media' >"$output"
                ;;
            *)
                printf 'unexpected URL: %s\\n' "$url" >&2
                exit 22
                ;;
        esac
        [[ -z "$headers" ]] || printf 'HTTP/1.1 200 OK\\r\\nContent-Type: %s\\r\\n\\r\\n' "$content_type" >"$headers"
        [[ -z "$write_out" ]] || printf '200\\n%s\\n' "$content_type"
        EOF
        chmod +x "$stub/curl"
        PATH="$stub:$PATH" \
            SMOKE_RAG_QUESTION='fixture question' \
            /bin/bash /repo/deploy/bin/smoke-test.sh \
            http://127.0.0.1:18080 http://127.0.0.1 /tmp/app.env
        printf '%s\\n' '__CALLS__'
        sed -n '1,200p' "$calls"
    """


def _deploy_failure_harness() -> str:
    setup, marker, _remainder = _preflight_harness().partition("        set +e\n")
    assert marker
    return setup + """\
        cat >"$stub/docker" <<'EOF'
        #!/usr/bin/env bash
        set -Eeuo pipefail
        printf 'docker %s\\n' "$*" >>/tmp/calls
        if [[ "$1" == "compose" && "$2" == "version" ]]; then
            exit 0
        fi
        if [[ "$1" == "network" && "$2" == "inspect" ]]; then
            printf '1999wiki-infra\\n'
            exit 0
        fi
        if [[ " $* " == *" up -d --no-build --pull never backend frontend "* ]]; then
            exit 12
        fi
        if [[ " $* " == *" ps --format json backend frontend "* ]]; then
            printf '%s\\n' '[{"Service":"backend","State":"running","Health":"healthy","Image":"ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0"},{"Service":"frontend","State":"running","Health":"healthy","Image":"ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0"}]'
            exit 0
        fi
        if [[ " $* " == *" ps --format json "* ]]; then
            printf '%s\\n' '[{"State":"running","Health":"healthy"}]'
            exit 0
        fi
        if [[ " $* " == *" ps -a -q "* ]]; then
            exit 0
        fi
        exit 0
        EOF
        cat >"$stub/curl" <<'EOF'
        #!/usr/bin/env bash
        set -Eeuo pipefail
        output=/dev/stdout
        url=
        while (($#)); do
            case "$1" in
                -o|--output)
                    output="$2"
                    shift 2
                    ;;
                http://*|https://*)
                    url="$1"
                    shift
                    ;;
                *)
                    shift
                    ;;
            esac
        done
        printf 'curl %s\\n' "$url" >>/tmp/calls
        if [[ "$url" == "http://127.0.0.1:18080/health" ]]; then
            printf '%s' '{"status":"ok","vectorstore_loaded":true,"provenance_status":"pass","llm_ready":true}' >"$output"
            exit 0
        fi
        exit 22
        EOF
        chmod +x "$stub/docker" "$stub/curl"
        set +e
        output="$(
            PATH="$stub:$PATH" \
            DEPLOY_ROOT="$root" \
            PROTECTED_ENV_DIR="$root/protected" \
            RELEASES_DIR="$root/releases" \
            STATE_DIR="$root/deploy-state" \
            RAG_ROOT="$root/rag-artifacts" \
            APP_COMPOSE_FILE=/repo/deploy/compose.app.yml \
            INFRA_COMPOSE_FILE=/repo/deploy/compose.infra.yml \
            CADDY_CONFIG="$root/Caddyfile" \
            ACTIVE_FRAGMENT="$root/active.caddy" \
            APP_ENV_FILE="$root/protected/app.env" \
            INFRA_ENV_FILE="$root/protected/infra.env" \
            CADDY_ENV_FILE="$root/protected/caddy.env" \
            CADDY_SERVICE_UID=0 \
            CADDY_SERVICE_GIDS=0 \
            RELEASE_ENV_FILE="$root/releases/sha-abcdef0/blue.env" \
            HEALTH_ATTEMPTS=1 \
            HEALTH_INTERVAL_SECONDS=0 \
            SMOKE_RAG_QUESTION='fixture question' \
            /bin/bash /repo/deploy/bin/deploy.sh sha-abcdef0 blue 2>&1
        )"
        status=$?
        set -e
        printf '%s\\n__STATUS=%s\\n' "$output" "$status"
        printf '%s\\n' '__CALLS__'
        sed -n '1,240p' "$calls"
    """


def _switch_restore_harness(corrupt_backup: bool = False) -> str:
    corrupt_line = (
        "printf 'corrupt-backup\\n' >\"$TRANSACTION_OLD_FRAGMENT\""
        if corrupt_backup
        else ":"
    )
    return f"""\
        set -Eeuo pipefail
        root=/tmp/1999wiki
        stub=/tmp/stub
        calls=/tmp/calls
        mkdir -p "$root/protected" "$root/deploy-state" "$root/caddy" "$stub"
        chmod 700 "$root/deploy-state"
        : >"$calls"
        printf 'reverse_proxy 127.0.0.1:18080\\n' >"$root/caddy/active.caddy"
        printf 'reverse_proxy 127.0.0.1:18180\\n' >"$root/candidate.caddy"
        chown 0:1234 "$root/caddy/active.caddy"
        chmod 640 "$root/caddy/active.caddy"
        cat >"$root/protected/caddy.env" <<'EOF'
        SITE_ADDRESS=:80
        MINIO_PROXY_UPSTREAM=127.0.0.1:19000
        EOF
        chmod 600 "$root/protected/caddy.env"
        cat >"$stub/caddy" <<'EOF'
        #!/usr/bin/env bash
        set -Eeuo pipefail
        printf 'caddy %s\\n' "$*" >>/tmp/calls
        if [[ "$1" == "reload" ]]; then
            count_file=/tmp/reload-count
            count=0
            [[ ! -f "$count_file" ]] || count="$(<"$count_file")"
            count=$((count + 1))
            printf '%s\\n' "$count" >"$count_file"
            if (( count == 1 )); then
                exit 1
            fi
        fi
        exit 0
        EOF
        chmod +x "$stub/caddy"
        set +e
        output="$(
            PATH="$stub:$PATH" \
            DEPLOY_ROOT="$root" \
            STATE_DIR="$root/deploy-state" \
            CADDY_CONFIG="$root/Caddyfile" \
            CADDY_ENV_FILE="$root/protected/caddy.env" \
            ACTIVE_FRAGMENT="$root/caddy/active.caddy" \
            CADDY_SERVICE_UID=65534 \
            CADDY_SERVICE_GIDS=1234 \
            python3 /repo/deploy/bin/ops_helper.py lock-exec \
            "$root/deploy-state" "$root/deploy-state/operations.lock" 9 -- \
            /bin/bash -c '
                SCRIPT_DIR=/repo/deploy/bin
                OPS_CONTEXT=test-transaction
                source /repo/deploy/bin/ops-common.sh
                ops_acquire_lock
                ops_begin_transaction switch
                set +e
                ops_install_fragment /tmp/1999wiki/candidate.caddy
                ops_caddy_reload
                status=$?
                set -e
                [[ "$status" -ne 0 ]]
                {corrupt_line}
                ops_reconcile_journal
            ' 2>&1
        )"
        status=$?
        set -e
        printf '%s\\n__STATUS=%s\\n' "$output" "$status"
        printf '%s\\n' '__FRAGMENT__'
        sed -n '1,20p' "$root/caddy/active.caddy"
        stat -c '__FRAGMENT_META__=%u:%g:%a' "$root/caddy/active.caddy"
        printf '%s\\n' '__CALLS__'
        sed -n '1,200p' "$calls"
        if [[ -e "$root/deploy-state/active.env" ]]; then
            printf '%s\\n' '__STATE_WAS_WRITTEN__'
        fi
        printf '__JOURNAL=%s\\n' "$([[ -e "$root/deploy-state/transaction.env" ]] && printf present || printf absent)"
    """


def _cleanup_harness(
    confirmation: str,
    customize: str = "",
    release: str = "sha-abcdef0",
    slot: str = "green",
    crash_phase: str = "",
    retry_after_failure: bool = False,
) -> str:
    crash_assignment = (
        f"OPS_TEST_RETIREMENT_CRASH_PHASE={crash_phase} \\" if crash_phase else ""
    )
    retry_block = ""
    if retry_after_failure:
        retry_block = f"""\
        set +e
        retry_output="$(
            PATH="$stub:$PATH" \
            DEPLOY_ROOT="$root" \
            RELEASES_DIR="$root/releases" \
            STATE_DIR="$root/deploy-state" \
            APP_COMPOSE_FILE=/repo/deploy/compose.app.yml \
            APP_ENV_FILE="$root/protected/app.env" \
            ACTIVE_FRAGMENT="$root/active.caddy" \
            RELEASE_ENV_FILE="$root/releases/sha-abcdef0/green.env" \
            /bin/bash /repo/deploy/bin/cleanup.sh \
            {release} {slot} {confirmation!r} 2>&1
        )"
        retry_status=$?
        set -e
        output="$output
        __RETRY__
        $retry_output"
        status="$retry_status"
        """
    return f"""\
        set -Eeuo pipefail
        root=/tmp/1999wiki
        stub=/tmp/stub
        calls=/tmp/calls
        mkdir -p "$root/protected" "$root/releases/sha-abcdef0" \
            "$root/releases/sha-1234567" "$root/deploy-state" "$stub"
        chmod 700 "$root/deploy-state"
        : >"$calls"
        cat >"$root/protected/app.env" <<'EOF'
        APP_ENV=production
        MILVUS_URI=http://standalone:19530
        MILVUS_DB_NAME=wiki
        MILVUS_COLLECTION_NAME=collection
        MINIO_ENDPOINT=minio:9000
        MINIO_ACCESS_KEY=x
        MINIO_SECRET_KEY=x
        MINIO_BUCKET=assets
        MEDIA_PUBLIC_BASE_URL=/media
        MYSQL_HOST=mysql
        MYSQL_PORT=3306
        MYSQL_DATABASE=wiki
        MYSQL_USER=x
        MYSQL_PASSWORD=x
        DEEPSEEK_API_KEY=x
        SILICONFLOW_API_KEY=x
        HUIJI_PROCESSED_ROOT=/runtime/rag/huiji
        EOF
        cat >"$root/releases/sha-abcdef0/green.env" <<'EOF'
        BACKEND_IMAGE=ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0
        FRONTEND_IMAGE=ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0
        BACKEND_PORT=18100
        FRONTEND_PORT=18180
        EOF
        cat >"$root/releases/sha-1234567/blue.env" <<'EOF'
        BACKEND_IMAGE=ghcr.io/ddomelette/1999wiki-backend:sha-1234567
        FRONTEND_IMAGE=ghcr.io/ddomelette/1999wiki-frontend:sha-1234567
        BACKEND_PORT=18000
        FRONTEND_PORT=18080
        EOF
        chmod 600 "$root/protected/app.env" \
            "$root/releases/sha-abcdef0/green.env" \
            "$root/releases/sha-1234567/blue.env"
        python3 /repo/deploy/bin/ops_helper.py snapshot \
            "$root/deploy-state" sha-abcdef0 green \
            "$root/releases/sha-abcdef0/green.env" "$root/protected/app.env" /repo \
            >/dev/null
        python3 /repo/deploy/bin/ops_helper.py snapshot \
            "$root/deploy-state" sha-1234567 blue \
            "$root/releases/sha-1234567/blue.env" "$root/protected/app.env" /repo \
            >/dev/null
        printf 'reverse_proxy 127.0.0.1:18080\\n' >"$root/active.caddy"
        printf 'reverse_proxy 127.0.0.1:18180\\n' \
            >"$root/deploy-state/previous-green.caddy"
        chmod 640 "$root/deploy-state/previous-green.caddy"
        cat >"$root/deploy-state/active.env" <<'EOF'
        STATE_VERSION=3
        GENERATION=gen-0123456789abcdef01234567
        ACTIVE_SLOT=blue
        ACTIVE_RELEASE=sha-1234567
        ACTIVE_PROJECT=1999wiki-blue
        ACTIVE_FRONTEND_PORT=18080
        ACTIVE_RELEASE_SNAPSHOT=/tmp/1999wiki/deploy-state/snapshots/sha-1234567/blue/release.env
        ACTIVE_APP_SNAPSHOT=/tmp/1999wiki/deploy-state/snapshots/sha-1234567/blue/app.env
        ACTIVE_BACKEND_IMAGE=ghcr.io/ddomelette/1999wiki-backend:sha-1234567
        ACTIVE_FRONTEND_IMAGE=ghcr.io/ddomelette/1999wiki-frontend:sha-1234567
        PREVIOUS_AVAILABLE=1
        PREVIOUS_SLOT=green
        PREVIOUS_RELEASE=sha-abcdef0
        PREVIOUS_PROJECT=1999wiki-green
        PREVIOUS_FRONTEND_PORT=18180
        PREVIOUS_RELEASE_SNAPSHOT=/tmp/1999wiki/deploy-state/snapshots/sha-abcdef0/green/release.env
        PREVIOUS_APP_SNAPSHOT=/tmp/1999wiki/deploy-state/snapshots/sha-abcdef0/green/app.env
        PREVIOUS_BACKEND_IMAGE=ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0
        PREVIOUS_FRONTEND_IMAGE=ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0
        PREVIOUS_FRAGMENT_BACKUP=/tmp/1999wiki/deploy-state/previous-green.caddy
        EOF
        chmod 600 "$root/deploy-state/active.env"
        {textwrap.dedent(customize)}
        cat >"$stub/docker" <<'EOF'
        #!/usr/bin/env bash
        set -Eeuo pipefail
        printf 'docker %s\\n' "$*" >>/tmp/calls
        if [[ "$1" == "image" && "$2" == "ls" ]]; then
            image="${{@: -1}}"
            if [[ ! -f /tmp/removed-images ]] \
                || ! grep -Fxq "$image" /tmp/removed-images; then
                printf '%s\\n' "$image"
            fi
        elif [[ "$1" == "image" && "$2" == "rm" ]]; then
            shift 2
            printf '%s\\n' "$@" >>/tmp/removed-images
        fi
        exit 0
        EOF
        chmod +x "$stub/docker"
        set +e
        output="$(
            {crash_assignment}
            PATH="$stub:$PATH" \
            DEPLOY_ROOT="$root" \
            RELEASES_DIR="$root/releases" \
            STATE_DIR="$root/deploy-state" \
            APP_COMPOSE_FILE=/repo/deploy/compose.app.yml \
            APP_ENV_FILE="$root/protected/app.env" \
            ACTIVE_FRAGMENT="$root/active.caddy" \
            RELEASE_ENV_FILE="$root/releases/sha-abcdef0/green.env" \
            /bin/bash /repo/deploy/bin/cleanup.sh \
            {release} {slot} {confirmation!r} 2>&1
        )"
        status=$?
        set -e
        {retry_block}
        printf '%s\\n__STATUS=%s\\n' "$output" "$status"
        printf '%s\\n' '__CALLS__'
        sed -n '1,120p' "$calls"
        printf '%s\\n' '__STATE__'
        if [[ -e "$root/deploy-state/active.env" ]]; then
            sed -n '1,30p' "$root/deploy-state/active.env"
        fi
        printf '__RETIREMENT=%s\\n' "$([[ -e "$root/deploy-state/retirement.env" ]] && printf present || printf absent)"
    """


def _lifecycle_harness(*, fail_child_after_commit: bool = False) -> str:
    child_failure_flag = "1" if fail_child_after_commit else "0"
    return f"""\
        set -Eeuo pipefail
        root=/tmp/lifecycle
        stub=/tmp/stub
        calls=/tmp/calls
        mkdir -p "$root/bin" "$root/protected" "$root/releases/sha-1234567" \
            "$root/releases/sha-abcdef0" "$root/state" "$root/rag" "$stub"
        chmod 700 "$root/state"
        : >"$calls"
        cp /repo/deploy/bin/*.sh /repo/deploy/bin/ops_helper.py "$root/bin/"
        cat >"$root/bin/smoke-test.sh" <<'EOF'
        #!/usr/bin/env bash
        printf 'smoke %s\\n' "$*" >>/tmp/calls
        exit 0
        EOF
        if [[ "{child_failure_flag}" == "1" ]]; then
            mv "$root/bin/switch.sh" "$root/bin/switch.real.sh"
            cat >"$root/bin/switch.sh" <<'EOF'
        #!/usr/bin/env bash
        /bin/bash /tmp/lifecycle/bin/switch.real.sh "$@"
        exit 42
        EOF
            mv "$root/bin/ops_helper.py" "$root/bin/ops_helper.real.py"
            cat >"$root/bin/ops_helper.py" <<'PY'
        import os
        import sys

        if (
            len(sys.argv) >= 3
            and sys.argv[1] == "durable-unlink"
            and sys.argv[2].endswith("/transaction.env")
        ):
            raise SystemExit(23)
        os.execv(
            sys.executable,
            [sys.executable, "/tmp/lifecycle/bin/ops_helper.real.py", *sys.argv[1:]],
        )
        PY
        fi
        chmod +x "$root/bin/"*.sh "$root/bin/ops_helper.py"
        cat >"$root/protected/app.env" <<'EOF'
        APP_ENV=production
        MILVUS_URI=http://standalone:19530
        MILVUS_DB_NAME=wiki
        MILVUS_COLLECTION_NAME=collection
        MINIO_ENDPOINT=minio:9000
        MINIO_ACCESS_KEY=x
        MINIO_SECRET_KEY=x
        MINIO_BUCKET=assets
        MEDIA_PUBLIC_BASE_URL=/media
        MYSQL_HOST=mysql
        MYSQL_PORT=3306
        MYSQL_DATABASE=wiki
        MYSQL_USER=x
        MYSQL_PASSWORD=x
        DEEPSEEK_API_KEY=x
        SILICONFLOW_API_KEY=x
        HUIJI_PROCESSED_ROOT=/runtime/rag/huiji
        EOF
        cat >"$root/protected/infra.env" <<'EOF'
        MYSQL_ROOT_PASSWORD=root
        MYSQL_USER=x
        MYSQL_PASSWORD=x
        MINIO_ROOT_USER=x
        MINIO_ROOT_PASSWORD=x
        EOF
        cat >"$root/protected/caddy.env" <<'EOF'
        SITE_ADDRESS=:80
        MINIO_PROXY_UPSTREAM=127.0.0.1:19000
        EOF
        cat >"$root/releases/sha-1234567/blue.env" <<'EOF'
        BACKEND_IMAGE=ghcr.io/ddomelette/1999wiki-backend:sha-1234567
        FRONTEND_IMAGE=ghcr.io/ddomelette/1999wiki-frontend:sha-1234567
        BACKEND_PORT=18000
        FRONTEND_PORT=18080
        EOF
        cat >"$root/releases/sha-abcdef0/green.env" <<'EOF'
        BACKEND_IMAGE=ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0
        FRONTEND_IMAGE=ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0
        BACKEND_PORT=18100
        FRONTEND_PORT=18180
        EOF
        chmod 600 "$root/protected/"*.env "$root/releases/"*/*.env
        printf '%s\\n' '{{"schema_version":"evb.active-build/v1"}}' \
            >"$root/rag/active_build.v1.json"
        helper="$root/bin/ops_helper.py"
        if [[ "{child_failure_flag}" == "1" ]]; then
            helper="$root/bin/ops_helper.real.py"
        fi
        python3 "$helper" snapshot "$root/state" sha-1234567 blue \
            "$root/releases/sha-1234567/blue.env" "$root/protected/app.env" /repo \
            >/dev/null
        python3 "$helper" snapshot "$root/state" sha-abcdef0 green \
            "$root/releases/sha-abcdef0/green.env" "$root/protected/app.env" /repo \
            >/dev/null
        printf 'reverse_proxy 127.0.0.1:18080\\n' >"$root/active.caddy"
        chmod 640 "$root/active.caddy"
        cat >"$root/state/active.env" <<'EOF'
        STATE_VERSION=3
        GENERATION=gen-0123456789abcdef01234567
        ACTIVE_SLOT=blue
        ACTIVE_RELEASE=sha-1234567
        ACTIVE_PROJECT=1999wiki-blue
        ACTIVE_FRONTEND_PORT=18080
        ACTIVE_RELEASE_SNAPSHOT=/tmp/lifecycle/state/snapshots/sha-1234567/blue/release.env
        ACTIVE_APP_SNAPSHOT=/tmp/lifecycle/state/snapshots/sha-1234567/blue/app.env
        ACTIVE_BACKEND_IMAGE=ghcr.io/ddomelette/1999wiki-backend:sha-1234567
        ACTIVE_FRONTEND_IMAGE=ghcr.io/ddomelette/1999wiki-frontend:sha-1234567
        PREVIOUS_AVAILABLE=0
        PREVIOUS_SLOT=
        PREVIOUS_RELEASE=
        PREVIOUS_PROJECT=
        PREVIOUS_FRONTEND_PORT=
        PREVIOUS_RELEASE_SNAPSHOT=
        PREVIOUS_APP_SNAPSHOT=
        PREVIOUS_BACKEND_IMAGE=
        PREVIOUS_FRONTEND_IMAGE=
        PREVIOUS_FRAGMENT_BACKUP=
        EOF
        chmod 600 "$root/state/active.env"
        cat >"$root/Caddyfile" <<EOF
        :80 {{
            import $root/active.caddy
        }}
        EOF
        cat >"$stub/docker" <<'EOF'
        #!/usr/bin/env bash
        set -Eeuo pipefail
        printf 'docker %s\\n' "$*" >>/tmp/calls
        if [[ "$1" == "compose" && "$2" == "version" ]]; then
            exit 0
        fi
        if [[ "$1" == "network" && "$2" == "inspect" ]]; then
            printf '1999wiki-infra\\n'
            exit 0
        fi
        if [[ " $* " == *" ps --format json backend frontend "* ]]; then
            printf '%s\\n' '[{{"Service":"backend","State":"running","Health":"healthy","Image":"ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0"}},{{"Service":"frontend","State":"running","Health":"healthy","Image":"ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0"}}]'
            exit 0
        fi
        if [[ " $* " == *" ps --format json "* ]]; then
            printf '%s\\n' '[{{"State":"running","Health":"healthy"}}]'
            exit 0
        fi
        if [[ "$1" == "image" && "$2" == "ls" ]]; then
            image="${{@: -1}}"
            if [[ ! -f /tmp/removed-images ]] \
                || ! grep -Fxq "$image" /tmp/removed-images; then
                printf '%s\\n' "$image"
            fi
            exit 0
        fi
        if [[ "$1" == "image" && "$2" == "rm" ]]; then
            shift 2
            printf '%s\\n' "$@" >>/tmp/removed-images
            exit 0
        fi
        exit 0
        EOF
        cat >"$stub/curl" <<'EOF'
        #!/usr/bin/env bash
        set -Eeuo pipefail
        output=/dev/stdout
        while (($#)); do
            case "$1" in
                -o|--output) output="$2"; shift 2 ;;
                *) shift ;;
            esac
        done
        printf '%s' '{{"status":"ok","vectorstore_loaded":true,"provenance_status":"pass","llm_ready":true}}' >"$output"
        EOF
        cat >"$stub/caddy" <<'EOF'
        #!/usr/bin/env bash
        printf 'caddy %s\\n' "$*" >>/tmp/calls
        exit 0
        EOF
        cat >"$stub/df" <<'EOF'
        #!/usr/bin/env bash
        printf 'Filesystem 1024-blocks Used Available Capacity Mounted on\\n'
        printf '/dev/test 100000000 1 99999999 1%% /tmp\\n'
        EOF
        chmod +x "$stub/"*
        common_env=(
            PATH="$stub:$PATH"
            REPO_ROOT=/repo
            DEPLOY_ROOT="$root"
            RELEASES_DIR="$root/releases"
            DEPLOY_STATE_ROOT="$root/state"
            ACTIVE_FRAGMENT="$root/active.caddy"
            CADDY_IMPORT_PATH="$root/active.caddy"
            CADDY_CONFIG="$root/Caddyfile"
            CADDY_ENV_FILE="$root/protected/caddy.env"
            CADDY_SERVICE_UID=0
            CADDY_SERVICE_GIDS=0
            APP_COMPOSE_FILE=/repo/deploy/compose.app.yml
            INFRA_COMPOSE_FILE=/repo/deploy/compose.infra.yml
            APP_ENV_FILE="$root/protected/app.env"
            INFRA_ENV_FILE="$root/protected/infra.env"
            RAG_ROOT="$root/rag"
            PUBLIC_BASE_URL=http://127.0.0.1
            HEALTH_ATTEMPTS=1
            HEALTH_INTERVAL_SECONDS=0
            VERIFY_ATTEMPTS=1
            VERIFY_INTERVAL_SECONDS=0
            SMOKE_RAG_QUESTION=fixture
        )
        if [[ "{child_failure_flag}" == "1" ]]; then
            set +e
            output="$(
                env "${{common_env[@]}}" \
                    SOURCE_RELEASE_ENV_FILE="$root/releases/sha-abcdef0/green.env" \
                    SOURCE_APP_ENV_FILE="$root/protected/app.env" \
                    /bin/bash "$root/bin/deploy.sh" sha-abcdef0 green 2>&1
            )"
            deploy_status=$?
            set -e
            printf '%s\\n__DEPLOY_STATUS=%s\\n' "$output" "$deploy_status"
        else
            env "${{common_env[@]}}" \
                /bin/bash "$root/bin/switch.sh" green \
                "$root/state/snapshots/sha-abcdef0/green/release.env"
            env "${{common_env[@]}}" \
                /bin/bash "$root/bin/cleanup.sh" \
                sha-1234567 blue remove-blue-sha-1234567
            env "${{common_env[@]}}" \
                RELEASE_ENV_FILE="$root/releases/sha-1234567/blue.env" \
                /bin/bash "$root/bin/preflight.sh" sha-1234567 blue
        fi
        printf '__STATE__\\n'
        sed -n '1,30p' "$root/state/active.env"
        printf '__FRAGMENT__\\n'
        sed -n '1,10p' "$root/active.caddy"
        printf '__JOURNAL=%s\\n' "$([[ -e "$root/state/transaction.env" ]] && printf present || printf absent)"
        printf '__RETIREMENT=%s\\n' "$([[ -e "$root/state/retirement.env" ]] && printf present || printf absent)"
        printf '__CALLS__\\n'
        sed -n '1,240p' "$calls"
    """


def _journal_recovery_harness(phase: str) -> str:
    assert phase in {"before-state-commit", "after-state-commit"}
    if phase == "before-state-commit":
        commit_block = (
            "OPS_TEST_CRASH_PHASE=before-state-commit; "
            "export OPS_TEST_CRASH_PHASE; "
            "ops_test_crash_before_state_commit"
        )
    else:
        commit_block = (
            'sed "s/GENERATION_PLACEHOLDER/$TRANSACTION_GENERATION/" '
            "/tmp/ops/state-template.env >/tmp/ops/state/new-state.env; "
            "chmod 600 /tmp/ops/state/new-state.env; "
            "OPS_TEST_CRASH_PHASE=after-state-commit; "
            "export OPS_TEST_CRASH_PHASE; "
            "ops_commit_transaction_state /tmp/ops/state/new-state.env"
        )
    return f"""\
        set -Eeuo pipefail
        root=/tmp/ops
        stub=/tmp/stub
        calls=/tmp/calls
        mkdir -p "$root/state" "$root/source" "$stub"
        chmod 700 "$root/state"
        : >"$calls"
        cat >"$root/source/release.env" <<'EOF'
        BACKEND_IMAGE=ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0
        FRONTEND_IMAGE=ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0
        BACKEND_PORT=18100
        FRONTEND_PORT=18180
        EOF
        cat >"$root/source/app.env" <<'EOF'
        APP_ENV=production
        MILVUS_URI=http://standalone:19530
        MILVUS_DB_NAME=wiki
        MILVUS_COLLECTION_NAME=collection
        MINIO_ENDPOINT=minio:9000
        MINIO_ACCESS_KEY=x
        MINIO_SECRET_KEY=x
        MINIO_BUCKET=assets
        MEDIA_PUBLIC_BASE_URL=/media
        MYSQL_HOST=mysql
        MYSQL_PORT=3306
        MYSQL_DATABASE=wiki
        MYSQL_USER=x
        MYSQL_PASSWORD=x
        DEEPSEEK_API_KEY=x
        SILICONFLOW_API_KEY=x
        HUIJI_PROCESSED_ROOT=/runtime/rag/huiji
        EOF
        chmod 600 "$root/source/release.env" "$root/source/app.env"
        python3 /repo/deploy/bin/ops_helper.py snapshot \
            "$root/state" sha-abcdef0 green \
            "$root/source/release.env" "$root/source/app.env" /repo >/dev/null
        cat >"$root/state-template.env" <<'EOF'
        STATE_VERSION=3
        GENERATION=GENERATION_PLACEHOLDER
        ACTIVE_SLOT=green
        ACTIVE_RELEASE=sha-abcdef0
        ACTIVE_PROJECT=1999wiki-green
        ACTIVE_FRONTEND_PORT=18180
        ACTIVE_RELEASE_SNAPSHOT=/tmp/ops/state/snapshots/sha-abcdef0/green/release.env
        ACTIVE_APP_SNAPSHOT=/tmp/ops/state/snapshots/sha-abcdef0/green/app.env
        ACTIVE_BACKEND_IMAGE=ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0
        ACTIVE_FRONTEND_IMAGE=ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0
        PREVIOUS_AVAILABLE=0
        PREVIOUS_SLOT=
        PREVIOUS_RELEASE=
        PREVIOUS_PROJECT=
        PREVIOUS_FRONTEND_PORT=
        PREVIOUS_RELEASE_SNAPSHOT=
        PREVIOUS_APP_SNAPSHOT=
        PREVIOUS_BACKEND_IMAGE=
        PREVIOUS_FRONTEND_IMAGE=
        PREVIOUS_FRAGMENT_BACKUP=
        EOF
        printf 'reverse_proxy 127.0.0.1:18080\\n' >"$root/active.caddy"
        printf 'reverse_proxy 127.0.0.1:18180\\n' >"$root/candidate.caddy"
        chmod 640 "$root/active.caddy"
        cat >"$root/caddy.env" <<'EOF'
        SITE_ADDRESS=:80
        MINIO_PROXY_UPSTREAM=127.0.0.1:19000
        EOF
        chmod 600 "$root/caddy.env"
        cat >"$stub/caddy" <<'EOF'
        #!/usr/bin/env bash
        printf 'caddy %s\\n' "$*" >>/tmp/calls
        exit 0
        EOF
        chmod +x "$stub/caddy"
        common_env=(
            PATH="$stub:$PATH"
            DEPLOY_STATE_ROOT="$root/state"
            ACTIVE_FRAGMENT="$root/active.caddy"
            CADDY_CONFIG="$root/Caddyfile"
            CADDY_ENV_FILE="$root/caddy.env"
            CADDY_SERVICE_UID=0
            CADDY_SERVICE_GIDS=0
        )
        set +e
        env "${{common_env[@]}}" python3 /repo/deploy/bin/ops_helper.py \
            lock-exec "$root/state" "$root/state/operations.lock" 9 -- \
            /bin/bash -c '
            SCRIPT_DIR=/repo/deploy/bin
            OPS_CONTEXT=crash-producer
            source /repo/deploy/bin/ops-common.sh
            ops_acquire_lock
            ops_begin_transaction switch
            ops_install_transaction_traffic /tmp/ops/candidate.caddy
            {commit_block}
        '
        producer_status=$?
        set -e
        [[ "$producer_status" -ne 0 ]]
        [[ -e "$root/state/transaction.env" ]]
        env "${{common_env[@]}}" python3 /repo/deploy/bin/ops_helper.py \
            lock-exec "$root/state" "$root/state/operations.lock" 9 -- \
            /bin/bash -c '
            SCRIPT_DIR=/repo/deploy/bin
            OPS_CONTEXT=crash-reconciler
            source /repo/deploy/bin/ops-common.sh
            ops_acquire_lock
            ops_reconcile_journal
        '
        printf '__FRAGMENT__\\n'
        sed -n '1,10p' "$root/active.caddy"
        printf '__STATE__\\n'
        if [[ -e "$root/state/active.env" ]]; then
            sed -n '1,30p' "$root/state/active.env"
        else
            printf 'absent\\n'
        fi
        printf '__JOURNAL=%s\\n' "$([[ -e "$root/state/transaction.env" ]] && printf present || printf absent)"
        printf '__TX_BACKUPS=%s\\n' "$(find "$root/state" -maxdepth 1 -name 'tx-*-old-fragment.caddy' | wc -l)"
        printf '__CALLS__\\n'
        sed -n '1,40p' "$calls"
    """


def _rollback_harness(
    reload_failure: bool,
    *,
    durable_unlink_failure: bool = False,
    stop_failure: bool = False,
) -> str:
    reload_failure_flag = "1" if reload_failure else "0"
    durable_unlink_failure_flag = "1" if durable_unlink_failure else "0"
    stop_failure_flag = "1" if stop_failure else "0"
    return f"""\
        set -Eeuo pipefail
        root=/tmp/rollback
        stub=/tmp/stub
        calls=/tmp/calls
        mkdir -p "$root/state" "$root/source/blue" "$root/source/green" \
            "$root/bin" "$stub"
        chmod 700 "$root/state"
        : >"$calls"
        cp /repo/deploy/bin/*.sh /repo/deploy/bin/ops_helper.py "$root/bin/"
        if [[ "{durable_unlink_failure_flag}" == "1" ]]; then
            mv "$root/bin/ops_helper.py" "$root/bin/ops_helper.real.py"
            cat >"$root/bin/ops_helper.py" <<'PY'
        import os
        import sys

        if (
            len(sys.argv) >= 3
            and sys.argv[1] == "durable-unlink"
            and sys.argv[2].endswith("/transaction.env")
        ):
            raise SystemExit(23)
        os.execv(
            sys.executable,
            [sys.executable, "/tmp/rollback/bin/ops_helper.real.py", *sys.argv[1:]],
        )
        PY
        fi
        cat >"$root/bin/smoke-test.sh" <<'EOF'
        #!/usr/bin/env bash
        printf 'smoke %s\\n' "$*" >>/tmp/calls
        exit 0
        EOF
        chmod +x "$root/bin/"*.sh "$root/bin/ops_helper.py"
        cat >"$root/source/app.env" <<'EOF'
        APP_ENV=production
        MILVUS_URI=http://standalone:19530
        MILVUS_DB_NAME=wiki
        MILVUS_COLLECTION_NAME=collection
        MINIO_ENDPOINT=minio:9000
        MINIO_ACCESS_KEY=x
        MINIO_SECRET_KEY=x
        MINIO_BUCKET=assets
        MEDIA_PUBLIC_BASE_URL=/media
        MYSQL_HOST=mysql
        MYSQL_PORT=3306
        MYSQL_DATABASE=wiki
        MYSQL_USER=x
        MYSQL_PASSWORD=x
        DEEPSEEK_API_KEY=x
        SILICONFLOW_API_KEY=x
        HUIJI_PROCESSED_ROOT=/runtime/rag/huiji
        EOF
        cat >"$root/source/blue/release.env" <<'EOF'
        BACKEND_IMAGE=ghcr.io/ddomelette/1999wiki-backend:sha-1234567
        FRONTEND_IMAGE=ghcr.io/ddomelette/1999wiki-frontend:sha-1234567
        BACKEND_PORT=18000
        FRONTEND_PORT=18080
        EOF
        cat >"$root/source/green/release.env" <<'EOF'
        BACKEND_IMAGE=ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0
        FRONTEND_IMAGE=ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0
        BACKEND_PORT=18100
        FRONTEND_PORT=18180
        EOF
        chmod 600 "$root/source/app.env" \
            "$root/source/blue/release.env" "$root/source/green/release.env"
        python3 "$root/bin/ops_helper.py" snapshot \
            "$root/state" sha-1234567 blue \
            "$root/source/blue/release.env" "$root/source/app.env" /repo >/dev/null
        python3 "$root/bin/ops_helper.py" snapshot \
            "$root/state" sha-abcdef0 green \
            "$root/source/green/release.env" "$root/source/app.env" /repo >/dev/null
        printf 'reverse_proxy 127.0.0.1:18080\\n' >"$root/active.caddy"
        printf 'reverse_proxy 127.0.0.1:18180\\n' >"$root/state/previous.caddy"
        chmod 640 "$root/active.caddy" "$root/state/previous.caddy"
        cat >"$root/state/active.env" <<'EOF'
        STATE_VERSION=3
        GENERATION=gen-0123456789abcdef01234567
        ACTIVE_SLOT=blue
        ACTIVE_RELEASE=sha-1234567
        ACTIVE_PROJECT=1999wiki-blue
        ACTIVE_FRONTEND_PORT=18080
        ACTIVE_RELEASE_SNAPSHOT=/tmp/rollback/state/snapshots/sha-1234567/blue/release.env
        ACTIVE_APP_SNAPSHOT=/tmp/rollback/state/snapshots/sha-1234567/blue/app.env
        ACTIVE_BACKEND_IMAGE=ghcr.io/ddomelette/1999wiki-backend:sha-1234567
        ACTIVE_FRONTEND_IMAGE=ghcr.io/ddomelette/1999wiki-frontend:sha-1234567
        PREVIOUS_AVAILABLE=1
        PREVIOUS_SLOT=green
        PREVIOUS_RELEASE=sha-abcdef0
        PREVIOUS_PROJECT=1999wiki-green
        PREVIOUS_FRONTEND_PORT=18180
        PREVIOUS_RELEASE_SNAPSHOT=/tmp/rollback/state/snapshots/sha-abcdef0/green/release.env
        PREVIOUS_APP_SNAPSHOT=/tmp/rollback/state/snapshots/sha-abcdef0/green/app.env
        PREVIOUS_BACKEND_IMAGE=ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0
        PREVIOUS_FRONTEND_IMAGE=ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0
        PREVIOUS_FRAGMENT_BACKUP=/tmp/rollback/state/previous.caddy
        EOF
        chmod 600 "$root/state/active.env"
        cat >"$root/Caddyfile" <<EOF
        :80 {{
            import $root/active.caddy
        }}
        EOF
        cat >"$root/caddy.env" <<'EOF'
        SITE_ADDRESS=:80
        MINIO_PROXY_UPSTREAM=127.0.0.1:19000
        EOF
        chmod 600 "$root/caddy.env"
        cat >"$stub/docker" <<'EOF'
        #!/usr/bin/env bash
        set -Eeuo pipefail
        printf 'docker %s\\n' "$*" >>/tmp/calls
        if [[ "{stop_failure_flag}" == "1" && " $* " == *" stop backend frontend "* ]]; then
            exit 29
        fi
        if [[ " $* " == *" ps --format json backend frontend "* ]]; then
            printf '%s\\n' '[{{"Service":"backend","State":"running","Health":"healthy","Image":"ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0"}},{{"Service":"frontend","State":"running","Health":"healthy","Image":"ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0"}}]'
        fi
        exit 0
        EOF
        cat >"$stub/curl" <<'EOF'
        #!/usr/bin/env bash
        set -Eeuo pipefail
        output=/dev/stdout
        while (($#)); do
            case "$1" in
                -o|--output) output="$2"; shift 2 ;;
                *) shift ;;
            esac
        done
        printf '%s' '{{"status":"ok","vectorstore_loaded":true,"provenance_status":"pass","llm_ready":true}}' >"$output"
        exit 0
        EOF
        cat >"$stub/caddy" <<'EOF'
        #!/usr/bin/env bash
        set -Eeuo pipefail
        printf 'caddy %s\\n' "$*" >>/tmp/calls
        if [[ "$1" == "reload" ]]; then
            count=0
            [[ ! -f /tmp/reload-count ]] || count="$(</tmp/reload-count)"
            count=$((count + 1))
            printf '%s\\n' "$count" >/tmp/reload-count
            if [[ "{reload_failure_flag}" == "1" && "$count" == "1" ]]; then
                exit 17
            fi
        fi
        exit 0
        EOF
        chmod +x "$stub/docker" "$stub/curl" "$stub/caddy"
        set +e
        output="$(
            PATH="$stub:$PATH" \
            DEPLOY_STATE_ROOT="$root/state" \
            ACTIVE_FRAGMENT="$root/active.caddy" \
            CADDY_IMPORT_PATH="$root/active.caddy" \
            CADDY_CONFIG="$root/Caddyfile" \
            CADDY_ENV_FILE="$root/caddy.env" \
            CADDY_SERVICE_UID=0 \
            CADDY_SERVICE_GIDS=0 \
            APP_COMPOSE_FILE=/repo/deploy/compose.app.yml \
            PUBLIC_BASE_URL=http://127.0.0.1 \
            HEALTH_ATTEMPTS=1 \
            HEALTH_INTERVAL_SECONDS=0 \
            VERIFY_ATTEMPTS=1 \
            VERIFY_INTERVAL_SECONDS=0 \
            SMOKE_RAG_QUESTION=fixture \
            /bin/bash "$root/bin/rollback.sh" 2>&1
        )"
        status=$?
        set -e
        printf '%s\\n__STATUS=%s\\n' "$output" "$status"
        printf '__FRAGMENT__\\n'
        sed -n '1,10p' "$root/active.caddy"
        printf '__STATE__\\n'
        sed -n '1,30p' "$root/state/active.env"
        printf '__JOURNAL=%s\\n' "$([[ -e "$root/state/transaction.env" ]] && printf present || printf absent)"
        printf '__CALLS__\\n'
        sed -n '1,100p' "$calls"
    """


@pytest.mark.parametrize("path", REQUIRED_FILES)
def test_required_blue_green_controls_exist(path: Path) -> None:
    assert path.is_file(), f"missing {path.relative_to(ROOT)}"


def test_mutating_operations_share_lock_snapshot_and_journal_controls() -> None:
    common = _read(OPS_COMMON)
    helper = _read(OPS_HELPER)
    for contract in (
        "DEPLOY_STATE_ROOT",
        "operations.lock",
        "OPS_LOCK_HELD",
        "ops_reconcile_operations",
        "transaction.env",
        "prepared",
        "traffic_installed",
        "state_committed",
        "ops_snapshot_release",
        "ops_install_fragment",
    ):
        assert contract in common
    for contract in (
        "strict_env",
        "atomic_replace",
        "fsync",
        "lock_exec",
        "validate_lock_descriptor",
        "LOCK_NB",
        "O_NOFOLLOW",
        "validate_state",
        "validate_journal",
        "fragment_metadata",
        "snapshot",
    ):
        assert contract in helper

    for script_name in ("deploy.sh", "switch.sh", "rollback.sh", "cleanup.sh"):
        text = _read(BIN / script_name)
        assert 'source "$SCRIPT_DIR/ops-common.sh"' in text
        assert "ops_acquire_lock" in text
        assert "ops_reconcile_operations" in text


def test_deploy_owns_partial_candidate_cleanup_before_compose_up() -> None:
    text = _read(BIN / "deploy.sh")
    responsibility = text.index("candidate_cleanup_required=true")
    compose_up = text.index(" up ")
    assert responsibility < compose_up
    assert "ops_acquire_lock" in text
    assert "ops_snapshot_release" in text
    assert '"$SCRIPT_DIR/switch.sh" "$SLOT" "$RELEASE_SNAPSHOT"' in text


def test_switch_derives_identity_from_snapshot_and_never_accepts_a_port() -> None:
    text = _read(BIN / "switch.sh")
    assert "usage:" in text
    assert "SLOT RELEASE_SNAPSHOT" in text
    assert "FRONTEND_PORT=\"$3\"" not in text
    assert "ops_load_snapshot" in text
    assert "ops_verify_project_identity" in text
    assert "ops_begin_transaction" in text
    common = _read(OPS_COMMON)
    assert "ops_mark_transaction_phase traffic_installed" in common
    assert "ops_mark_transaction_phase state_committed" in common


def test_cleanup_requires_strict_reconciled_state_and_protects_previous() -> None:
    text = _read(BIN / "cleanup.sh")
    assert "ops_load_active_state" in text
    assert "ops_validate_active_consistency" in text
    assert "PREVIOUS_SLOT" in text
    assert "PREVIOUS_RELEASE" in text
    assert "recorded previous deployment" in text


def test_smoke_hardens_assets_redirects_media_base_and_terminal_sse() -> None:
    text = _read(BIN / "smoke-test.sh")
    assert "Content-Type" in text
    assert "--location" in text
    assert "MEDIA_PUBLIC_BASE_URL" in text
    assert "APP_ENV_FILE" in text
    assert "terminal event is not done" in text
    assert "text/html" in text


@pytest.mark.parametrize("script_name", SCRIPTS)
def test_scripts_fail_fast_and_avoid_broad_or_secret_dumping_operations(
    script_name: str,
) -> None:
    text = _read(BIN / script_name)
    assert text.startswith("#!/usr/bin/env bash\nset -Eeuo pipefail\n")
    lowered = text.lower()
    for operation in FORBIDDEN_OPERATIONS:
        assert operation not in lowered
    assert not re.search(r"\bcat\s+[^\n]*\.env(?:\s|$)", lowered)
    assert "env |" not in lowered
    assert "printenv" not in lowered


def test_host_caddy_strips_media_prefix_before_minio_and_imports_active_app() -> None:
    text = _read(DEPLOY / "Caddyfile")
    assert "{$SITE_ADDRESS}" in text
    assert "handle_path /media/*" in text
    assert "reverse_proxy {$MINIO_PROXY_UPSTREAM}" in text
    assert "import /etc/caddy/active-upstream.caddy" in text
    assert text.index("handle_path /media/*") < text.index(
        "import /etc/caddy/active-upstream.caddy"
    )

    assert _read(DEPLOY / "caddy" / "active-upstream.caddy.example").strip() == (
        "reverse_proxy 127.0.0.1:18080"
    )
    assert _read(DEPLOY / "env" / "caddy.env.example").splitlines() == [
        "SITE_ADDRESS=:80",
        "MINIO_PROXY_UPSTREAM=127.0.0.1:19000",
    ]


def test_preflight_contains_fail_closed_security_and_readiness_gates() -> None:
    text = _read(BIN / "preflight.sh")
    contracts_text = text + _read(OPS_HELPER)
    for command in ("docker", "caddy", "curl", "python3"):
        assert command in text
    for contract in (
        "8589934592",
        "1999wiki-infra",
        "APP_ENV_FILE",
        ".example",
        "MINIO_ACCESS_KEY",
        "MINIO_SECRET_KEY",
        "MYSQL_USER",
        "MYSQL_PASSWORD",
        "DEEPSEEK_API_KEY",
        "SILICONFLOW_API_KEY",
        "ghcr.io/ddomelette/1999wiki-backend",
        "ghcr.io/ddomelette/1999wiki-frontend",
        "sha-[0-9a-f]{7}",
        "rag-artifacts",
    ):
        assert contract in contracts_text
    assert "mkdir" not in text
    assert " up " not in text
    assert "create" not in text.lower()


def test_preflight_success_is_read_only_and_does_not_disclose_credentials(
    tmp_path: Path,
) -> None:
    result = _run_linux_harness(tmp_path, _preflight_harness())
    assert result.returncode == 0, result.stderr
    assert "__STATUS=0" in result.stdout
    for sentinel in (
        "minio-secret-sentinel",
        "mysql-secret-sentinel",
        "deepseek-sentinel",
        "siliconflow-sentinel",
    ):
        assert sentinel not in result.stdout + result.stderr
    calls = result.stdout.partition("__CALLS__")[2]
    assert not re.search(r"\b(up|start|create|reload)\b", calls)


@pytest.mark.parametrize(
    ("customize", "diagnostic"),
    [
        (
            "APP_ENV_FILE_OVERRIDE=/repo/deploy/env/app.env.example",
            "checked example",
        ),
        (
            'chmod 644 "$root/protected/app.env"',
            "mode 0600",
        ),
        (
            """\
            sed -i \
                's#ghcr.io/ddomelette/1999wiki-backend#ghcr.io/attacker/backend#' \
                "$root/releases/sha-abcdef0/blue.env"
            """,
            "approved immutable image",
        ),
        (
            """\
                sed -i 's/^MINIO_SECRET_KEY=.*/MINIO_SECRET_KEY=/' \
                "$root/protected/app.env"
            """,
            "MINIO_SECRET_KEY",
        ),
        (
            'rm -f "$root/rag-artifacts/active_build.v1.json"',
            "active_build.v1.json",
        ),
    ],
)
def test_preflight_rejects_unsafe_paths_modes_images_and_empty_secrets_without_leaks(
    tmp_path: Path,
    customize: str,
    diagnostic: str,
) -> None:
    result = _run_linux_harness(tmp_path, _preflight_harness(customize))
    assert result.returncode == 0, result.stderr
    assert "__STATUS=0" not in result.stdout
    assert diagnostic in result.stdout
    for sentinel in (
        "minio-secret-sentinel",
        "mysql-secret-sentinel",
        "deepseek-sentinel",
        "siliconflow-sentinel",
    ):
        assert sentinel not in result.stdout + result.stderr
    calls = result.stdout.partition("__CALLS__")[2]
    assert not re.search(r"\b(up|start|create|reload)\b", calls)


def test_deploy_runs_preflight_and_smoke_before_switching() -> None:
    text = _read(BIN / "deploy.sh")
    preflight = text.index('"$SCRIPT_DIR/preflight.sh"')
    pull_backend = text.index('docker pull "$BACKEND_IMAGE"')
    pull_frontend = text.index('docker pull "$FRONTEND_IMAGE"')
    compose_up = text.index(" up ")
    smoke = text.index('"$SCRIPT_DIR/smoke-test.sh"')
    switch = text.index('"$SCRIPT_DIR/switch.sh"')
    assert preflight < pull_backend < compose_up
    assert preflight < pull_frontend < compose_up
    assert compose_up < smoke < switch
    assert "--pull never" in text
    assert " stop" in text


def test_deploy_stops_failed_candidate_without_switching_or_leaking_secrets(
    tmp_path: Path,
) -> None:
    result = _run_linux_harness(tmp_path, _deploy_failure_harness())
    assert result.returncode == 0, result.stderr
    assert "__STATUS=0" not in result.stdout
    calls = result.stdout.partition("__CALLS__")[2]
    backend_pull = calls.index(
        "docker pull ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0"
    )
    frontend_pull = calls.index(
        "docker pull ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0"
    )
    compose_up = calls.index(" up -d --no-build --pull never backend frontend")
    candidate_stop = calls.index(" stop backend frontend")
    assert backend_pull < frontend_pull < compose_up < candidate_stop
    assert "curl http://127.0.0.1:18080/" not in calls
    assert "caddy reload" not in calls
    for sentinel in (
        "minio-secret-sentinel",
        "mysql-secret-sentinel",
        "deepseek-sentinel",
        "siliconflow-sentinel",
    ):
        assert sentinel not in result.stdout + result.stderr


def test_switch_validates_complete_temp_config_before_atomic_replace() -> None:
    text = _read(BIN / "switch.sh")
    common = _read(OPS_COMMON)
    temp_config = text.index("TEMP_CONFIG")
    validate = text.index('caddy validate --config "$TEMP_CONFIG"')
    begin = text.index("ops_begin_transaction")
    replace = text.index("ops_install_transaction_traffic")
    public_verify = text.index("ops_verify_public_health", replace)
    record_state = text.index("ops_commit_transaction_state", public_verify)
    stop_old = text.index('ops_compose "$OLD_PROJECT" stop', record_state)
    assert temp_config < validate < begin < replace
    assert replace < public_verify < record_state < stop_old
    assert "ops_reconcile_journal" in common
    assert "atomic-copy" in common


def test_transaction_reload_failure_atomically_restores_fragment_and_omits_state(
    tmp_path: Path,
) -> None:
    result = _run_linux_harness(tmp_path, _switch_restore_harness())
    assert result.returncode == 0, result.stderr
    assert "__STATUS=0" in result.stdout
    fragment = result.stdout.partition("__FRAGMENT__")[2].partition(
        "__FRAGMENT_META__"
    )[0]
    assert fragment.strip() == "reverse_proxy 127.0.0.1:18080"
    assert "__FRAGMENT_META__=0:1234:640" in result.stdout
    calls = result.stdout.partition("__CALLS__")[2]
    assert calls.count("caddy reload") == 2
    assert "__STATE_WAS_WRITTEN__" not in result.stdout
    assert "__JOURNAL=absent" in result.stdout


def test_corrupt_recovery_backup_fails_before_fragment_install_or_reload(
    tmp_path: Path,
) -> None:
    result = _run_linux_harness(tmp_path, _switch_restore_harness(True))
    assert result.returncode == 0, result.stderr
    assert "__STATUS=0" not in result.stdout
    fragment = result.stdout.partition("__FRAGMENT__")[2].partition(
        "__FRAGMENT_META__"
    )[0]
    assert fragment.strip() == "reverse_proxy 127.0.0.1:18180"
    calls = result.stdout.partition("__CALLS__")[2]
    assert calls.count("caddy reload") == 1
    assert "__JOURNAL=present" in result.stdout


def test_rollback_only_restores_the_recorded_application_and_fragment() -> None:
    text = _read(BIN / "rollback.sh")
    common = _read(OPS_COMMON)
    assert "compose.infra" not in text
    assert "1999wiki-infra" not in text
    assert 'ops_compose "$ROLLBACK_PROJECT" start backend frontend' in text
    assert "ops_install_transaction_traffic" in text
    assert 'caddy validate --config "$TEMP_CONFIG"' in text
    assert 'caddy reload --config "$CADDY_CONFIG"' in common
    assert "ops_verify_public_health" in text


def test_smoke_test_requires_live_rag_fixture_and_covers_candidate_and_public_bases() -> None:
    text = _read(BIN / "smoke-test.sh")
    for contract in (
        "CANDIDATE_BASE_URL",
        "PUBLIC_BASE_URL",
        "SMOKE_RAG_QUESTION",
        "/health",
        "/api/wiki/health",
        "/api/wiki/pages?limit=1",
        "/api/ask",
        "/api/ask/stream",
        "/media/",
        'events[-1] != "done"',
    ):
        assert contract in text
    assert "skip" not in text.lower()


def test_smoke_test_uses_candidate_for_app_checks_and_public_host_for_media(
    tmp_path: Path,
) -> None:
    result = _run_linux_harness(tmp_path, _smoke_harness())
    assert result.returncode == 0, result.stdout + result.stderr
    calls = result.stdout.partition("__CALLS__")[2].splitlines()
    assert "http://127.0.0.1:18080/" in calls
    assert "http://127.0.0.1:18080/health" in calls
    assert "http://127.0.0.1:18080/api/wiki/health" in calls
    assert "http://127.0.0.1:18080/api/ask" in calls
    assert "http://127.0.0.1:18080/api/ask/stream" in calls
    assert "http://127.0.0.1/media/reverse1999-assets/fixture.webp" in calls
    assert "http://127.0.0.1/media/health" not in calls


@pytest.mark.parametrize(
    ("mutation", "diagnostic"),
    [
        (
            lambda body: body.replace(
                "content_type=application/javascript",
                "content_type=text/html",
            ),
            "html fallback",
        ),
        (
            lambda body: body.replace(
                "event: done\\ndata: {\"answer\":\"ok\"}\\n\\n",
                (
                    "event: done\\ndata: {\"answer\":\"ok\"}\\n\\n"
                    "event: sources\\ndata: {}\\n\\n"
                ),
            ),
            "terminal event is not done",
        ),
        (
            lambda body: body.replace(
                '{"answer":"ok","media":[{"url":"/media/reverse1999-assets/fixture.webp"}]}',
                '{"answer":"ok","media":[{"url":"https://unrelated.invalid/fixture.webp"}]}',
            ),
            "MEDIA_PUBLIC_BASE_URL",
        ),
    ],
)
def test_smoke_fails_closed_on_asset_sse_and_media_projection_errors(
    tmp_path: Path,
    mutation,
    diagnostic: str,
) -> None:
    result = _run_linux_harness(tmp_path, mutation(_smoke_harness()))
    assert result.returncode != 0
    assert diagnostic.lower() in (result.stdout + result.stderr).lower()


def test_cleanup_is_exactly_scoped_and_requires_release_confirmation() -> None:
    text = _read(BIN / "cleanup.sh")
    common = _read(OPS_COMMON)
    assert 'CONFIRMATION="remove-${SLOT}-${REQUESTED_RELEASE}"' in text
    assert 'docker compose \\' in common
    assert " down " in common
    assert "--volumes" not in text


def test_cleanup_stub_removes_only_named_inactive_project_and_exact_images(
    tmp_path: Path,
) -> None:
    result = _run_linux_harness(
        tmp_path,
        _cleanup_harness("remove-green-sha-abcdef0"),
    )
    assert result.returncode == 0, result.stderr
    assert "__STATUS=0" in result.stdout
    calls = result.stdout.partition("__CALLS__")[2]
    assert "docker compose -p 1999wiki-green" in calls
    assert " down --remove-orphans" in calls
    assert "1999wiki-infra" not in calls
    assert "--volumes" not in calls
    assert (
        "docker image rm ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0"
    ) in calls
    assert (
        "docker image rm ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0"
    ) in calls
    assert "--volumes" not in calls
    assert "prune" not in calls
    assert "1999wiki-infra" not in calls
    state = result.stdout.partition("__STATE__")[2].partition("__RETIREMENT")[0]
    assert "PREVIOUS_AVAILABLE=0" in state
    assert "PREVIOUS_SLOT=\n" in state
    assert "__RETIREMENT=absent" in result.stdout


def test_cleanup_wrong_confirmation_issues_no_docker_command(tmp_path: Path) -> None:
    result = _run_linux_harness(tmp_path, _cleanup_harness("wrong"))
    assert result.returncode == 0, result.stderr
    assert "__STATUS=0" not in result.stdout
    calls = result.stdout.partition("__CALLS__")[2].partition("__STATE__")[0]
    assert calls.strip() == ""


@pytest.mark.parametrize(
    "crash_phase",
    ("after-prepared", "after-resources-removed", "after-state-commit"),
)
def test_cleanup_retirement_crash_retry_finishes_idempotently(
    tmp_path: Path,
    crash_phase: str,
) -> None:
    result = _run_linux_harness(
        tmp_path,
        _cleanup_harness(
            "remove-green-sha-abcdef0",
            crash_phase=crash_phase,
            retry_after_failure=True,
        ),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "__RETRY__" in result.stdout
    assert "__STATUS=0" in result.stdout
    state = result.stdout.partition("__STATE__")[2].partition("__RETIREMENT")[0]
    assert "ACTIVE_SLOT=blue" in state
    assert "PREVIOUS_AVAILABLE=0" in state
    assert "__RETIREMENT=absent" in result.stdout


def test_strict_env_parser_rejects_placeholders_without_evaluating_them(
    tmp_path: Path,
) -> None:
    result = _run_linux_harness(
        tmp_path,
        """\
        set -Eeuo pipefail
        printf '%s\\n' \
            'BACKEND_IMAGE=ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0' \
            'FRONTEND_IMAGE=ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0' \
            'BACKEND_PORT=18000' \
            'FRONTEND_PORT=${AMBIENT_PORT}' >/tmp/release.env
        set +e
        AMBIENT_PORT=18080 python3 /repo/deploy/bin/ops_helper.py \
            validate-env release /tmp/release.env --release sha-abcdef0 \
            >/tmp/output 2>&1
        status=$?
        set -e
        printf '__STATUS=%s\\n' "$status"
        sed -n '1,20p' /tmp/output
        """,
    )
    assert result.returncode == 0, result.stderr
    assert "__STATUS=0" not in result.stdout
    assert "unresolved placeholder" in result.stdout
    assert "18080" not in result.stdout


def test_operations_lock_rejects_a_concurrent_mutator(tmp_path: Path) -> None:
    result = _run_linux_harness(
        tmp_path,
        """\
        set -Eeuo pipefail
        root=/tmp/state
        mkdir "$root"
        chmod 700 "$root"
        python3 /repo/deploy/bin/ops_helper.py \
            lock-exec "$root" "$root/operations.lock" 9 -- \
            /bin/bash -c '
            touch /tmp/lock-ready
            sleep 2
        ' &
        holder=$!
        for _ in 1 2 3 4 5 6 7 8 9 10; do
            [[ ! -e /tmp/lock-ready ]] || break
            sleep 0.1
        done
        set +e
        output="$(
            python3 /repo/deploy/bin/ops_helper.py \
                lock-exec "$root" "$root/operations.lock" 9 -- \
                /bin/true 2>&1
        )"
        status=$?
        set -e
        wait "$holder"
        printf '%s\\n__STATUS=%s\\n' "$output" "$status"
        """,
    )
    assert result.returncode == 0, result.stderr
    assert "__STATUS=0" not in result.stdout
    assert "another production operation holds the global lock" in result.stdout


def test_snapshot_freezes_identity_and_rejects_wrong_slot_or_ambient_port(
    tmp_path: Path,
) -> None:
    result = _run_linux_harness(
        tmp_path,
        """\
        set -Eeuo pipefail
        root=/tmp/ops
        mkdir -p "$root/state" "$root/source"
        chmod 700 "$root/state"
        cat >"$root/source/release.env" <<'EOF'
        BACKEND_IMAGE=ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0
        FRONTEND_IMAGE=ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0
        BACKEND_PORT=18000
        FRONTEND_PORT=18080
        EOF
        cat >"$root/source/app.env" <<'EOF'
        APP_ENV=production
        MILVUS_URI=http://standalone:19530
        MILVUS_DB_NAME=wiki
        MILVUS_COLLECTION_NAME=collection
        MINIO_ENDPOINT=minio:9000
        MINIO_ACCESS_KEY=x
        MINIO_SECRET_KEY=x
        MINIO_BUCKET=assets
        MEDIA_PUBLIC_BASE_URL=/media
        MYSQL_HOST=mysql
        MYSQL_PORT=3306
        MYSQL_DATABASE=wiki
        MYSQL_USER=x
        MYSQL_PASSWORD=x
        DEEPSEEK_API_KEY=x
        SILICONFLOW_API_KEY=x
        HUIJI_PROCESSED_ROOT=/runtime/rag/huiji
        EOF
        chmod 600 "$root/source/release.env" "$root/source/app.env"
        python3 /repo/deploy/bin/ops_helper.py snapshot \
            "$root/state" sha-abcdef0 blue \
            "$root/source/release.env" "$root/source/app.env" /repo \
            >/tmp/snapshot
        sed -i 's/FRONTEND_PORT=18080/FRONTEND_PORT=19999/' \
            "$root/source/release.env"
        BACKEND_PORT=29999 FRONTEND_PORT=29998 \
            python3 /repo/deploy/bin/ops_helper.py load-snapshot \
            "$root/state" blue \
            "$root/state/snapshots/sha-abcdef0/blue/release.env" \
            >/tmp/loaded
        set +e
        python3 /repo/deploy/bin/ops_helper.py load-snapshot \
            "$root/state" green \
            "$root/state/snapshots/sha-abcdef0/blue/release.env" \
            >/tmp/wrong 2>&1
        wrong_status=$?
        set -e
        printf '__LOADED__\\n'
        sed -n '1,20p' /tmp/loaded
        printf '__WRONG_STATUS=%s\\n' "$wrong_status"
        sed -n '1,20p' /tmp/wrong
        """,
    )
    assert result.returncode == 0, result.stderr
    loaded = result.stdout.partition("__LOADED__")[2].partition("__WRONG_STATUS")[0]
    assert "18000" in loaded
    assert "18080" in loaded
    assert "19999" not in loaded
    assert "29998" not in loaded
    assert "__WRONG_STATUS=0" not in result.stdout
    assert "does not match" in result.stdout


@pytest.mark.parametrize(
    ("customize", "release", "slot", "diagnostic"),
    [
        ('rm -f "$root/deploy-state/active.env"', "sha-abcdef0", "green", "missing"),
        (
            'sed -i "/^ACTIVE_PROJECT=/d" "$root/deploy-state/active.env"',
            "sha-abcdef0",
            "green",
            "missing or unexpected keys",
        ),
        (
            'printf "reverse_proxy 127.0.0.1:18180\\n" >"$root/active.caddy"',
            "sha-abcdef0",
            "green",
            "diverges",
        ),
        ("", "sha-1234567", "blue", "recorded previous"),
    ],
)
def test_cleanup_fails_closed_on_unreconciled_or_active_targets(
    tmp_path: Path,
    customize: str,
    release: str,
    slot: str,
    diagnostic: str,
) -> None:
    result = _run_linux_harness(
        tmp_path,
        _cleanup_harness(
            f"remove-{slot}-{release}",
            customize=customize,
            release=release,
            slot=slot,
        ),
    )
    assert result.returncode == 0, result.stderr
    assert "__STATUS=0" not in result.stdout
    assert diagnostic in result.stdout.lower()
    calls = result.stdout.partition("__CALLS__")[2].partition("__STATE__")[0]
    assert calls.strip() == ""


@pytest.mark.parametrize(
    ("phase", "expected_port", "state_marker"),
    [
        ("before-state-commit", "18080", "absent"),
        ("after-state-commit", "18180", "ACTIVE_SLOT=green"),
    ],
)
def test_journal_recovers_crashes_on_both_sides_of_state_commit(
    tmp_path: Path,
    phase: str,
    expected_port: str,
    state_marker: str,
) -> None:
    result = _run_linux_harness(tmp_path, _journal_recovery_harness(phase))
    assert result.returncode == 0, result.stdout + result.stderr
    fragment = result.stdout.partition("__FRAGMENT__")[2].partition("__STATE__")[0]
    state = result.stdout.partition("__STATE__")[2].partition("__JOURNAL")[0]
    assert f"127.0.0.1:{expected_port}" in fragment
    assert state_marker in state
    assert "__JOURNAL=absent" in result.stdout
    assert "__TX_BACKUPS=0" in result.stdout
    reloads = result.stdout.partition("__CALLS__")[2].count("caddy reload")
    assert reloads == (2 if phase == "before-state-commit" else 1)


def test_rollback_successfully_swaps_active_and_previous_state(
    tmp_path: Path,
) -> None:
    result = _run_linux_harness(tmp_path, _rollback_harness(False))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "__STATUS=0" in result.stdout
    fragment = result.stdout.partition("__FRAGMENT__")[2].partition("__STATE__")[0]
    state = result.stdout.partition("__STATE__")[2].partition("__JOURNAL")[0]
    assert "127.0.0.1:18180" in fragment
    assert "ACTIVE_SLOT=green" in state
    assert "ACTIVE_RELEASE=sha-abcdef0" in state
    assert "PREVIOUS_SLOT=blue" in state
    assert "PREVIOUS_RELEASE=sha-1234567" in state
    assert "__JOURNAL=absent" in result.stdout
    calls = result.stdout.partition("__CALLS__")[2]
    assert " start backend frontend" in calls
    assert " stop backend frontend" in calls
    assert calls.count("caddy reload") == 1


def test_rollback_reload_failure_restores_fragment_and_state(
    tmp_path: Path,
) -> None:
    result = _run_linux_harness(tmp_path, _rollback_harness(True))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "__STATUS=0" not in result.stdout
    fragment = result.stdout.partition("__FRAGMENT__")[2].partition("__STATE__")[0]
    state = result.stdout.partition("__STATE__")[2].partition("__JOURNAL")[0]
    assert "127.0.0.1:18080" in fragment
    assert "ACTIVE_SLOT=blue" in state
    assert "ACTIVE_RELEASE=sha-1234567" in state
    assert "PREVIOUS_SLOT=green" in state
    assert "__JOURNAL=absent" in result.stdout
    calls = result.stdout.partition("__CALLS__")[2]
    assert calls.count("caddy reload") == 2
    assert " stop backend frontend" not in calls


def test_committed_rollback_survives_post_commit_journal_unlink_failure(
    tmp_path: Path,
) -> None:
    result = _run_linux_harness(
        tmp_path,
        _rollback_harness(False, durable_unlink_failure=True),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "__STATUS=0" in result.stdout
    assert "housekeeping remains pending" in result.stdout
    fragment = result.stdout.partition("__FRAGMENT__")[2].partition("__STATE__")[0]
    state = result.stdout.partition("__STATE__")[2].partition("__JOURNAL")[0]
    assert "127.0.0.1:18180" in fragment
    assert "ACTIVE_SLOT=green" in state
    assert "__JOURNAL=present" in result.stdout


def test_committed_rollback_treats_old_project_stop_failure_as_warning(
    tmp_path: Path,
) -> None:
    result = _run_linux_harness(
        tmp_path,
        _rollback_harness(False, stop_failure=True),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "__STATUS=0" in result.stdout
    assert "could not be stopped" in result.stdout
    state = result.stdout.partition("__STATE__")[2].partition("__JOURNAL")[0]
    assert "ACTIVE_SLOT=green" in state
    assert "__JOURNAL=absent" in result.stdout


def test_full_retirement_lifecycle_makes_old_slot_preflight_reusable(
    tmp_path: Path,
) -> None:
    result = _run_linux_harness(tmp_path, _lifecycle_harness())
    assert result.returncode == 0, result.stdout + result.stderr
    assert "preflight passed for sha-1234567 in blue" in result.stdout
    state = result.stdout.partition("__STATE__")[2].partition("__FRAGMENT__")[0]
    assert "ACTIVE_SLOT=green" in state
    assert "ACTIVE_RELEASE=sha-abcdef0" in state
    assert "PREVIOUS_AVAILABLE=0" in state
    assert "PREVIOUS_SLOT=\n" in state
    assert "__JOURNAL=absent" in result.stdout
    assert "__RETIREMENT=absent" in result.stdout
    calls = result.stdout.partition("__CALLS__")[2]
    assert "1999wiki-blue" in calls
    assert " down --remove-orphans" in calls
    assert "image rm ghcr.io/ddomelette/1999wiki-backend:sha-1234567" in calls
    assert "image rm ghcr.io/ddomelette/1999wiki-frontend:sha-1234567" in calls


def test_deploy_does_not_stop_candidate_when_child_committed_then_failed(
    tmp_path: Path,
) -> None:
    result = _run_linux_harness(
        tmp_path,
        _lifecycle_harness(fail_child_after_commit=True),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "__DEPLOY_STATUS=0" not in result.stdout
    state = result.stdout.partition("__STATE__")[2].partition("__FRAGMENT__")[0]
    fragment = result.stdout.partition("__FRAGMENT__")[2].partition("__JOURNAL")[0]
    assert "ACTIVE_SLOT=green" in state
    assert "127.0.0.1:18180" in fragment
    assert "__JOURNAL=present" in result.stdout
    calls = result.stdout.partition("__CALLS__")[2]
    green_lines = [line for line in calls.splitlines() if "1999wiki-green" in line]
    assert not any(" stop backend frontend" in line for line in green_lines)


def test_secure_lock_exec_accepts_real_inheritance_and_rejects_symlink(
    tmp_path: Path,
) -> None:
    result = _run_linux_harness(
        tmp_path,
        """\
        set -Eeuo pipefail
        mkdir /tmp/state
        chmod 700 /tmp/state
        python3 /repo/deploy/bin/ops_helper.py lock-exec \
            /tmp/state /tmp/state/operations.lock 9 -- \
            /bin/bash -c '
                python3 /repo/deploy/bin/ops_helper.py verify-lock \
                    /tmp/state /tmp/state/operations.lock 9
                printf real-inherited-lock-ok
            '
        printf '\\n'
        rm -f /tmp/state/operations.lock
        printf untouched >/tmp/outside-lock
        ln -s /tmp/outside-lock /tmp/state/operations.lock
        set +e
        python3 /repo/deploy/bin/ops_helper.py lock-exec \
            /tmp/state /tmp/state/operations.lock 9 -- /bin/true \
            >/tmp/symlink-output 2>&1
        symlink_status=$?
        set -e
        printf '__SYMLINK_STATUS=%s\\n' "$symlink_status"
        sed -n '1,20p' /tmp/symlink-output
        printf '__OUTSIDE=%s\\n' "$(< /tmp/outside-lock)"
        """,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "real-inherited-lock-ok" in result.stdout
    assert "__SYMLINK_STATUS=0" not in result.stdout
    assert "symlink" in result.stdout.lower()
    assert "__OUTSIDE=untouched" in result.stdout


def test_secure_lock_rejects_spoofed_separately_opened_fd_under_contention(
    tmp_path: Path,
) -> None:
    result = _run_linux_harness(
        tmp_path,
        """\
        set -Eeuo pipefail
        mkdir /tmp/state
        chmod 700 /tmp/state
        python3 /repo/deploy/bin/ops_helper.py lock-exec \
            /tmp/state /tmp/state/operations.lock 9 -- \
            /bin/bash -c 'touch /tmp/holder-ready; sleep 2' &
        holder=$!
        for _ in 1 2 3 4 5 6 7 8 9 10; do
            [[ ! -e /tmp/holder-ready ]] || break
            sleep 0.1
        done
        set +e
        output="$(
            /bin/bash -c '
                exec 9<>/tmp/state/operations.lock
                OPS_LOCK_HELD=1 OPS_LOCK_FD=9 \
                    python3 /repo/deploy/bin/ops_helper.py verify-lock \
                    /tmp/state /tmp/state/operations.lock 9
            ' 2>&1
        )"
        status=$?
        set -e
        wait "$holder"
        printf '%s\\n__STATUS=%s\\n' "$output" "$status"
        """,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "__STATUS=0" not in result.stdout
    assert "lock" in result.stdout.lower()


def test_secure_lock_rejects_uncontended_separately_opened_canonical_fd(
    tmp_path: Path,
) -> None:
    result = _run_linux_harness(
        tmp_path,
        """\
        set -Eeuo pipefail
        mkdir /tmp/state
        chmod 700 /tmp/state
        : >/tmp/state/operations.lock
        chmod 600 /tmp/state/operations.lock
        set +e
        output="$(
            /bin/bash -c '
                exec 9<>/tmp/state/operations.lock
                OPS_LOCK_HELD=1 OPS_LOCK_FD=9 \
                    python3 /repo/deploy/bin/ops_helper.py verify-lock \
                    /tmp/state /tmp/state/operations.lock 9
            ' 2>&1
        )"
        status=$?
        set -e
        printf '%s\\n__STATUS=%s\\n' "$output" "$status"
        """,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "__STATUS=0" not in result.stdout
    assert "does not own" in result.stdout.lower()


def test_snapshot_symlink_redirect_is_rejected_without_outside_write(
    tmp_path: Path,
) -> None:
    result = _run_linux_harness(
        tmp_path,
        """\
        set -Eeuo pipefail
        mkdir -p /tmp/state /tmp/outside /tmp/source
        chmod 700 /tmp/state /tmp/outside
        ln -s /tmp/outside /tmp/state/snapshots
        cat >/tmp/source/release.env <<'EOF'
        BACKEND_IMAGE=ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0
        FRONTEND_IMAGE=ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0
        BACKEND_PORT=18000
        FRONTEND_PORT=18080
        EOF
        cat >/tmp/source/app.env <<'EOF'
        APP_ENV=production
        MILVUS_URI=http://standalone:19530
        MILVUS_DB_NAME=wiki
        MILVUS_COLLECTION_NAME=collection
        MINIO_ENDPOINT=minio:9000
        MINIO_ACCESS_KEY=x
        MINIO_SECRET_KEY=x
        MINIO_BUCKET=assets
        MEDIA_PUBLIC_BASE_URL=/media
        MYSQL_HOST=mysql
        MYSQL_PORT=3306
        MYSQL_DATABASE=wiki
        MYSQL_USER=x
        MYSQL_PASSWORD=x
        DEEPSEEK_API_KEY=x
        SILICONFLOW_API_KEY=x
        HUIJI_PROCESSED_ROOT=/runtime/rag/huiji
        EOF
        chmod 600 /tmp/source/release.env /tmp/source/app.env
        set +e
        output="$(
            python3 /repo/deploy/bin/ops_helper.py snapshot \
                /tmp/state sha-abcdef0 blue \
                /tmp/source/release.env /tmp/source/app.env /repo 2>&1
        )"
        status=$?
        set -e
        printf '%s\\n__STATUS=%s\\n' "$output" "$status"
        if find /tmp/outside -type f | grep -q .; then
            printf '__OUTSIDE_WRITE=true\\n'
        else
            printf '__OUTSIDE_WRITE=false\\n'
        fi
        """,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "__STATUS=0" not in result.stdout
    assert "symlink" in result.stdout.lower()
    assert "__OUTSIDE_WRITE=false" in result.stdout


@pytest.mark.parametrize("target_name", ["release.env", "app.env"])
def test_snapshot_rejects_final_file_symlinks_before_any_write(
    tmp_path: Path,
    target_name: str,
) -> None:
    result = _run_linux_harness(
        tmp_path,
        f"""\
        set -Eeuo pipefail
        snapshot_dir=/tmp/state/snapshots/sha-abcdef0/blue
        mkdir -p "$snapshot_dir" /tmp/outside /tmp/source
        chmod 700 /tmp/state /tmp/state/snapshots \
            /tmp/state/snapshots/sha-abcdef0 "$snapshot_dir" /tmp/outside
        cat >/tmp/source/release.env <<'EOF'
        BACKEND_IMAGE=ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0
        FRONTEND_IMAGE=ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0
        BACKEND_PORT=18000
        FRONTEND_PORT=18080
        EOF
        cat >/tmp/source/app.env <<'EOF'
        APP_ENV=production
        MILVUS_URI=http://standalone:19530
        MILVUS_DB_NAME=wiki
        MILVUS_COLLECTION_NAME=collection
        MINIO_ENDPOINT=minio:9000
        MINIO_ACCESS_KEY=x
        MINIO_SECRET_KEY=x
        MINIO_BUCKET=assets
        MEDIA_PUBLIC_BASE_URL=/media
        MYSQL_HOST=mysql
        MYSQL_PORT=3306
        MYSQL_DATABASE=wiki
        MYSQL_USER=x
        MYSQL_PASSWORD=x
        DEEPSEEK_API_KEY=x
        SILICONFLOW_API_KEY=x
        HUIJI_PROCESSED_ROOT=/runtime/rag/huiji
        EOF
        chmod 600 /tmp/source/release.env /tmp/source/app.env
        cp "/tmp/source/{target_name}" "/tmp/outside/{target_name}"
        chmod 600 "/tmp/outside/{target_name}"
        ln -s "/tmp/outside/{target_name}" "$snapshot_dir/{target_name}"
        set +e
        output="$(
            python3 /repo/deploy/bin/ops_helper.py snapshot \
                /tmp/state sha-abcdef0 blue \
                /tmp/source/release.env /tmp/source/app.env /repo 2>&1
        )"
        status=$?
        set -e
        printf '%s\\n__STATUS=%s\\n' "$output" "$status"
        if cmp -s "/tmp/source/{target_name}" "/tmp/outside/{target_name}"; then
            printf '__OUTSIDE_UNCHANGED=true\\n'
        else
            printf '__OUTSIDE_UNCHANGED=false\\n'
        fi
        regular_files="$(
            find "$snapshot_dir" -maxdepth 1 -type f -print | wc -l
        )"
        printf '__REGULAR_FILES=%s\\n' "$regular_files"
        """,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "__STATUS=0" not in result.stdout
    assert "symlink" in result.stdout.lower()
    assert "__OUTSIDE_UNCHANGED=true" in result.stdout
    assert "__REGULAR_FILES=0" in result.stdout


def test_strict_app_schema_rejects_bare_secret_placeholder_and_extra_key(
    tmp_path: Path,
) -> None:
    body = _smoke_harness().replace(
        "MINIO_SECRET_KEY=x",
        "MINIO_SECRET_KEY=$RUNTIME_SECRET",
    )
    placeholder = _run_linux_harness(tmp_path, body)
    assert placeholder.returncode != 0
    assert "unresolved placeholder" in (placeholder.stdout + placeholder.stderr)

    extra = _run_linux_harness(
        tmp_path,
        _smoke_harness().replace(
            "HUIJI_PROCESSED_ROOT=/runtime/rag/huiji",
            (
                "HUIJI_PROCESSED_ROOT=/runtime/rag/huiji\n"
                "        UNEXPECTED_APP_KEY=value"
            ),
        ),
    )
    assert extra.returncode != 0
    assert "unexpected" in (extra.stdout + extra.stderr).lower()


def test_app_schema_rejects_absolute_http_media_base(
    tmp_path: Path,
) -> None:
    result = _run_linux_harness(
        tmp_path,
        _smoke_harness().replace(
            "MEDIA_PUBLIC_BASE_URL=/media",
            "MEDIA_PUBLIC_BASE_URL=http://wiki.example/media",
        ),
    )
    assert result.returncode != 0
    assert "https" in (result.stdout + result.stderr).lower()


def test_media_validator_rejects_absolute_origin_unrelated_to_public_base(
    tmp_path: Path,
) -> None:
    result = _run_linux_harness(
        tmp_path,
        """\
        set -Eeuo pipefail
        cat >/tmp/app.env <<'EOF'
        APP_ENV=production
        MILVUS_URI=http://standalone:19530
        MILVUS_DB_NAME=wiki
        MILVUS_COLLECTION_NAME=collection
        MINIO_ENDPOINT=minio:9000
        MINIO_ACCESS_KEY=x
        MINIO_SECRET_KEY=x
        MINIO_BUCKET=assets
        MEDIA_PUBLIC_BASE_URL=https://cdn.invalid/media
        MYSQL_HOST=mysql
        MYSQL_PORT=3306
        MYSQL_DATABASE=wiki
        MYSQL_USER=x
        MYSQL_PASSWORD=x
        DEEPSEEK_API_KEY=x
        SILICONFLOW_API_KEY=x
        HUIJI_PROCESSED_ROOT=/runtime/rag/huiji
        EOF
        python3 /repo/deploy/bin/ops_helper.py validate-media-url \
            /tmp/app.env https://wiki.example \
            https://cdn.invalid/media/object.webp
        """,
    )
    assert result.returncode != 0
    assert "origin" in (result.stdout + result.stderr).lower()


@pytest.mark.parametrize(
    ("media_base", "returned_url"),
    [
        ("/media", "/media/../health"),
        ("/media", "/media/%2e%2e/health"),
        (
            "https://wiki.example/media",
            "https://wiki.example/media/../health",
        ),
        (
            "https://wiki.example/media",
            "https://wiki.example/media/%2E%2E/health",
        ),
    ],
)
def test_media_validator_rejects_literal_and_encoded_dot_segment_escapes(
    tmp_path: Path,
    media_base: str,
    returned_url: str,
) -> None:
    result = _run_linux_harness(
        tmp_path,
        f"""\
        set -Eeuo pipefail
        cat >/tmp/app.env <<'EOF'
        APP_ENV=production
        MILVUS_URI=http://standalone:19530
        MILVUS_DB_NAME=wiki
        MILVUS_COLLECTION_NAME=collection
        MINIO_ENDPOINT=minio:9000
        MINIO_ACCESS_KEY=x
        MINIO_SECRET_KEY=x
        MINIO_BUCKET=assets
        MEDIA_PUBLIC_BASE_URL={media_base}
        MYSQL_HOST=mysql
        MYSQL_PORT=3306
        MYSQL_DATABASE=wiki
        MYSQL_USER=x
        MYSQL_PASSWORD=x
        DEEPSEEK_API_KEY=x
        SILICONFLOW_API_KEY=x
        HUIJI_PROCESSED_ROOT=/runtime/rag/huiji
        EOF
        python3 /repo/deploy/bin/ops_helper.py validate-media-url \
            /tmp/app.env https://wiki.example {returned_url}
        """,
    )
    assert result.returncode != 0
    assert "dot segment" in (result.stdout + result.stderr).lower()


def test_state_schema_and_cleanup_expose_retirement_protocol() -> None:
    helper = _read(OPS_HELPER)
    common = _read(OPS_COMMON)
    cleanup = _read(BIN / "cleanup.sh")
    rollback = _read(BIN / "rollback.sh")
    assert "PREVIOUS_AVAILABLE" in helper
    assert "RETIREMENT_KEYS" in helper
    assert "ops_reconcile_retirement" in common
    assert "retirement.env" in common
    assert "resources_removed" in common
    assert "PREVIOUS_AVAILABLE" in cleanup
    assert "PREVIOUS_AVAILABLE" in rollback
