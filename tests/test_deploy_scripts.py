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
REQUIRED_FILES = (
    DEPLOY / "Caddyfile",
    DEPLOY / "caddy" / "active-upstream.caddy.example",
    DEPLOY / "env" / "caddy.env.example",
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
            "$root/protected/caddy.env"
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
        printf '%s\\n' "$url" >>/tmp/calls
        case "$url" in
            http://127.0.0.1:18080/)
                printf '<!doctype html><div id="root"></div><script src="/assets/app.js"></script>' >"$output"
                ;;
            http://127.0.0.1:18080/assets/app.js)
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
                printf 'fixture-media' >"$output"
                ;;
            *)
                printf 'unexpected URL: %s\\n' "$url" >&2
                exit 22
                ;;
        esac
        EOF
        chmod +x "$stub/curl"
        PATH="$stub:$PATH" \
            SMOKE_RAG_QUESTION='fixture question' \
            /bin/bash /repo/deploy/bin/smoke-test.sh \
            http://127.0.0.1:18080 http://127.0.0.1
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
        if [[ " $* " == *" ps --format json backend frontend "* ]]; then
            printf '%s\\n' '[{"Service":"backend","State":"running","Health":"healthy"},{"Service":"frontend","State":"running","Health":"healthy"}]'
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


def _switch_restore_harness() -> str:
    return """\
        set -Eeuo pipefail
        root=/tmp/1999wiki
        stub=/tmp/stub
        calls=/tmp/calls
        mkdir -p "$root/protected" "$root/releases/sha-abcdef0" \
            "$root/deploy-state" "$root/caddy" "$stub"
        : >"$calls"
        cat >"$root/Caddyfile" <<'EOF'
        :80 {
            import /etc/caddy/active-upstream.caddy
        }
        EOF
        printf 'reverse_proxy 127.0.0.1:18080\\n' >"$root/caddy/active.caddy"
        cat >"$root/protected/caddy.env" <<'EOF'
        SITE_ADDRESS=:80
        MINIO_PROXY_UPSTREAM=127.0.0.1:19000
        EOF
        cat >"$root/protected/app.env" <<'EOF'
        APP_ENV=production
        EOF
        cat >"$root/releases/sha-abcdef0/green.env" <<'EOF'
        BACKEND_IMAGE=ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0
        FRONTEND_IMAGE=ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0
        BACKEND_PORT=18100
        FRONTEND_PORT=18180
        EOF
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
        cat >"$stub/curl" <<'EOF'
        #!/usr/bin/env bash
        exit 99
        EOF
        cat >"$stub/docker" <<'EOF'
        #!/usr/bin/env bash
        printf 'docker %s\\n' "$*" >>/tmp/calls
        exit 0
        EOF
        chmod +x "$stub/caddy" "$stub/curl" "$stub/docker"
        set +e
        output="$(
            PATH="$stub:$PATH" \
            DEPLOY_ROOT="$root" \
            STATE_DIR="$root/deploy-state" \
            RELEASES_DIR="$root/releases" \
            APP_COMPOSE_FILE=/repo/deploy/compose.app.yml \
            APP_ENV_FILE="$root/protected/app.env" \
            CADDY_CONFIG="$root/Caddyfile" \
            CADDY_ENV_FILE="$root/protected/caddy.env" \
            CADDY_IMPORT_PATH=/etc/caddy/active-upstream.caddy \
            ACTIVE_FRAGMENT="$root/caddy/active.caddy" \
            RELEASE_ENV_FILE="$root/releases/sha-abcdef0/green.env" \
            /bin/bash /repo/deploy/bin/switch.sh sha-abcdef0 green 18180 2>&1
        )"
        status=$?
        set -e
        printf '%s\\n__STATUS=%s\\n' "$output" "$status"
        printf '%s\\n' '__FRAGMENT__'
        sed -n '1,20p' "$root/caddy/active.caddy"
        printf '%s\\n' '__CALLS__'
        sed -n '1,200p' "$calls"
        if [[ -e "$root/deploy-state/active.env" ]]; then
            printf '%s\\n' '__STATE_WAS_WRITTEN__'
        fi
    """


def _cleanup_harness(confirmation: str) -> str:
    return f"""\
        set -Eeuo pipefail
        root=/tmp/1999wiki
        stub=/tmp/stub
        calls=/tmp/calls
        mkdir -p "$root/protected" "$root/releases/sha-abcdef0" \
            "$root/deploy-state" "$stub"
        : >"$calls"
        printf 'APP_ENV=production\\n' >"$root/protected/app.env"
        cat >"$root/releases/sha-abcdef0/green.env" <<'EOF'
        BACKEND_IMAGE=ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0
        FRONTEND_IMAGE=ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0
        BACKEND_PORT=18100
        FRONTEND_PORT=18180
        EOF
        cat >"$root/deploy-state/active.env" <<'EOF'
        ACTIVE_SLOT=blue
        ACTIVE_RELEASE=sha-1234567
        EOF
        cat >"$stub/docker" <<'EOF'
        #!/usr/bin/env bash
        set -Eeuo pipefail
        printf 'docker %s\\n' "$*" >>/tmp/calls
        exit 0
        EOF
        chmod +x "$stub/docker"
        set +e
        output="$(
            PATH="$stub:$PATH" \
            DEPLOY_ROOT="$root" \
            RELEASES_DIR="$root/releases" \
            STATE_DIR="$root/deploy-state" \
            APP_COMPOSE_FILE=/repo/deploy/compose.app.yml \
            APP_ENV_FILE="$root/protected/app.env" \
            RELEASE_ENV_FILE="$root/releases/sha-abcdef0/green.env" \
            /bin/bash /repo/deploy/bin/cleanup.sh \
            sha-abcdef0 green {confirmation!r} 2>&1
        )"
        status=$?
        set -e
        printf '%s\\n__STATUS=%s\\n' "$output" "$status"
        printf '%s\\n' '__CALLS__'
        sed -n '1,120p' "$calls"
    """


@pytest.mark.parametrize("path", REQUIRED_FILES)
def test_required_blue_green_controls_exist(path: Path) -> None:
    assert path.is_file(), f"missing {path.relative_to(ROOT)}"


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
        assert contract in text
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
            sed -i 's/^MINIO_SECRET_KEY=.*/MINIO_SECRET_KEY=""/' \
                "$root/protected/app.env"
            """,
            "MINIO_SECRET_KEY",
        ),
        (
            'rm -f "$root/rag-artifacts/active_build.v1.json"',
            "active RAG pointer",
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
    smoke_root = calls.index("curl http://127.0.0.1:18080/")
    candidate_stop = calls.index(" stop backend frontend")
    assert backend_pull < frontend_pull < compose_up < smoke_root < candidate_stop
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
    temp_config = text.index("TEMP_CONFIG")
    validate = text.index('caddy validate --config "$TEMP_CONFIG"')
    save_previous = text.index('cp -p "$ACTIVE_FRAGMENT" "$PRIOR_FRAGMENT_TMP"')
    replace = text.index('mv -f "$TEMP_FRAGMENT" "$ACTIVE_FRAGMENT"')
    reload_caddy = text.index('caddy reload --config "$CADDY_CONFIG"', replace)
    public_verify = text.index("verify_public_health ||", reload_caddy)
    record_state = text.index('mv -f "$STATE_TMP" "$ACTIVE_STATE_FILE"')
    stop_old = text.index("stop_previous_slot", record_state)
    assert temp_config < validate < save_previous < replace < reload_caddy
    assert reload_caddy < public_verify < record_state < stop_old
    assert "restore_previous_fragment" in text


def test_switch_reload_failure_atomically_restores_fragment_and_omits_state(
    tmp_path: Path,
) -> None:
    result = _run_linux_harness(tmp_path, _switch_restore_harness())
    assert result.returncode == 0, result.stderr
    assert "__STATUS=0" not in result.stdout
    fragment = result.stdout.partition("__FRAGMENT__")[2].partition("__CALLS__")[0]
    assert fragment.strip() == "reverse_proxy 127.0.0.1:18080"
    calls = result.stdout.partition("__CALLS__")[2]
    assert calls.count("caddy reload") == 2
    assert "__STATE_WAS_WRITTEN__" not in result.stdout


def test_rollback_only_restores_the_recorded_application_and_fragment() -> None:
    text = _read(BIN / "rollback.sh")
    assert "compose.infra" not in text
    assert "1999wiki-infra" not in text
    assert '-p "$PREVIOUS_PROJECT"' in text
    assert "previous_compose start backend frontend" in text
    assert 'mv -f "$RESTORE_TMP" "$ACTIVE_FRAGMENT"' in text
    assert 'caddy validate --config "$TEMP_CONFIG"' in text
    assert 'caddy reload --config "$CADDY_CONFIG"' in text
    assert 'verify_health_url "$PUBLIC_BASE_URL"' in text


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
        "event: done",
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


def test_cleanup_is_exactly_scoped_and_requires_release_confirmation() -> None:
    text = _read(BIN / "cleanup.sh")
    assert 'CONFIRMATION="remove-${SLOT}-${RELEASE}"' in text
    assert 'docker compose -p "$PROJECT"' in text
    assert " down " in text
    assert "--volumes" not in text
    assert "1999wiki-infra" in text
    assert 'docker image rm "$BACKEND_IMAGE" "$FRONTEND_IMAGE"' in text


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
    assert (
        "docker image rm "
        "ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0 "
        "ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0"
    ) in calls
    assert "--volumes" not in calls
    assert "prune" not in calls
    assert "1999wiki-infra" not in calls


def test_cleanup_wrong_confirmation_issues_no_docker_command(tmp_path: Path) -> None:
    result = _run_linux_harness(tmp_path, _cleanup_harness("wrong"))
    assert result.returncode == 0, result.stderr
    assert "__STATUS=0" not in result.stdout
    assert result.stdout.partition("__CALLS__")[2].strip() == ""
