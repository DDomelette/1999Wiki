from __future__ import annotations

import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "publish-images.yml"
TAG_GUARD = ROOT / ".github" / "scripts" / "refuse-existing-image-tags.sh"
MANIFEST_BUILDER = ROOT / "deploy" / "bin" / "release_manifest.py"
SCRIPT_TEST_IMAGE = "python:3.11.15-slim-bookworm"


def _workflow() -> dict[str, object]:
    assert WORKFLOW.is_file(), "manual GHCR publishing workflow is missing"
    payload = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert isinstance(payload, dict)
    return payload


def _steps(job: dict[str, object]) -> list[dict[str, object]]:
    steps = job.get("steps")
    assert isinstance(steps, list)
    assert all(isinstance(step, dict) for step in steps)
    return steps


def _runs(job: dict[str, object]) -> list[str]:
    return [str(step["run"]) for step in _steps(job) if "run" in step]


def _uses(job: dict[str, object], action: str) -> dict[str, object]:
    matches = [step for step in _steps(job) if step.get("uses") == action]
    assert len(matches) == 1, f"{action} must be used exactly once"
    return matches[0]


def test_manual_ghcr_workflow_verifies_then_publishes_immutable_images() -> None:
    workflow = _workflow()

    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert workflow["permissions"] == {"contents": "read", "packages": "write"}
    assert workflow["concurrency"] == {
        "group": "publish-images-${{ github.sha }}",
        "cancel-in-progress": "false",
    }

    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    python = jobs["python-tests"]
    frontend = jobs["frontend-tests"]
    publish = jobs["publish"]
    assert all(isinstance(job, dict) for job in (python, frontend, publish))

    for job in (python, frontend, publish):
        checkout = _uses(job, "actions/checkout@v4")
        assert checkout["with"] == {"lfs": "true", "ref": "${{ github.sha }}"}
        assert "git lfs pull" in _runs(job)

    _uses(python, "actions/setup-python@v5")
    python_commands = "\n".join(_runs(python))
    assert "pip install -r requirements/dev.lock.txt" in python_commands
    assert "python -m pytest -q" in python_commands

    _uses(frontend, "actions/setup-node@v4")
    frontend_commands = "\n".join(_runs(frontend))
    assert "npm ci" in frontend_commands
    assert "npm test" in frontend_commands
    assert "npm run build" in frontend_commands

    assert publish["needs"] == ["python-tests", "frontend-tests"]
    _uses(publish, "docker/setup-buildx-action@v3")
    login = _uses(publish, "docker/login-action@v3")
    assert login["with"] == {
        "registry": "ghcr.io",
        "username": "${{ github.actor }}",
        "password": "${{ secrets.GITHUB_TOKEN }}",
    }

    tag = next(step for step in _steps(publish) if step.get("id") == "tag")
    assert tag["shell"] == "bash"
    assert tag["run"] == 'short_sha="${GITHUB_SHA::7}"\necho "tag=sha-${short_sha}" >> "$GITHUB_OUTPUT"\n'

    backend = next(step for step in _steps(publish) if step.get("id") == "backend")
    frontend_image = next(step for step in _steps(publish) if step.get("id") == "frontend")
    guard = next(step for step in _steps(publish) if step.get("id") == "immutability")
    assert ".github/scripts/refuse-existing-image-tags.sh" in guard["run"]
    assert _steps(publish).index(guard) < _steps(publish).index(backend)
    for image, dockerfile, repository in (
        (backend, "docker/Dockerfile.backend", "ghcr.io/ddomelette/1999wiki-backend"),
        (frontend_image, "docker/Dockerfile.frontend", "ghcr.io/ddomelette/1999wiki-frontend"),
    ):
        assert image["uses"] == "docker/build-push-action@v6"
        assert image["with"] == {
            "context": ".",
            "file": dockerfile,
            "push": "true",
            "tags": f"{repository}:${{{{ steps.tag.outputs.tag }}}}",
            "cache-from": "type=gha",
            "cache-to": "type=gha,mode=max",
        }

    summary = next(step for step in _steps(publish) if step.get("id") == "summary")
    assert "steps.backend.outputs.digest" in summary["run"]
    assert "steps.frontend.outputs.digest" in summary["run"]
    assert "$GITHUB_STEP_SUMMARY" in summary["run"]
    manifest = next(step for step in _steps(publish) if step.get("id") == "manifest")
    assert "deploy/bin/release_manifest.py create" in manifest["run"]
    assert "release-manifest.json" in manifest["run"]
    artifact = _uses(publish, "actions/upload-artifact@v4")
    assert artifact["with"]["path"] == "release-manifest.json"
    assert artifact["with"]["if-no-files-found"] == "error"

    forbidden = ("ssh", "scp", "docker compose", "appleboy")
    assert not any(token in WORKFLOW.read_text(encoding="utf-8").casefold() for token in forbidden)


def test_existing_tag_guard_refuses_existing_and_indeterminate_registry_state(
    tmp_path: Path,
) -> None:
    docker = shutil.which("docker")
    assert docker, "Docker CLI is required for the workflow behavior probe"
    harness = tmp_path / "tag-guard.sh"
    harness.write_text(
        textwrap.dedent(
            """\
            set -Eeuo pipefail
            mkdir -p /tmp/stub
            cat >/tmp/stub/docker <<'EOF'
            #!/usr/bin/env bash
            set -Eeuo pipefail
            case "${PROBE_MODE:?}" in
                existing)
                    if [[ "$*" == *"1999wiki-frontend"* ]]; then
                        exit 0
                    fi
                    printf 'manifest unknown\\n' >&2
                    exit 1
                    ;;
                absent)
                    printf 'manifest unknown\\n' >&2
                    exit 1
                    ;;
                transient)
                    printf 'registry timeout\\n' >&2
                    exit 1
                    ;;
            esac
            EOF
            chmod +x /tmp/stub/docker
            backend=ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0
            frontend=ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0
            for mode in existing absent transient; do
                set +e
                output="$(
                    PATH="/tmp/stub:$PATH" PROBE_MODE="$mode" \
                    /bin/bash /repo/.github/scripts/refuse-existing-image-tags.sh \
                        "$backend" "$frontend" 2>&1
                )"
                status=$?
                set -e
                printf '__%s_STATUS=%s\\n%s\\n' \
                    "${mode^^}" "$status" "$output"
            done
            """
        ),
        encoding="utf-8",
        newline="\n",
    )
    result = subprocess.run(
        [
            docker,
            "run",
            "--rm",
            "-v",
            f"{ROOT}:/repo:ro",
            "-v",
            f"{tmp_path}:/case:ro",
            SCRIPT_TEST_IMAGE,
            "/bin/bash",
            "/case/tag-guard.sh",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "__EXISTING_STATUS=0" not in result.stdout
    assert "already exists" in result.stdout
    assert "__ABSENT_STATUS=0" in result.stdout
    assert "__TRANSIENT_STATUS=0" not in result.stdout
    assert "could not prove" in result.stdout


def test_release_manifest_schema_binds_full_commit_tags_and_digests(
    tmp_path: Path,
) -> None:
    output = tmp_path / "release-manifest.json"
    commit = "abcdef0123456789abcdef0123456789abcdef01"
    backend_digest = "sha256:" + "a" * 64
    frontend_digest = "sha256:" + "b" * 64
    result = subprocess.run(
        [
            sys.executable,
            MANIFEST_BUILDER,
            "create",
            "--commit",
            commit,
            "--backend-tag",
            "ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0",
            "--backend-digest",
            backend_digest,
            "--frontend-tag",
            "ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0",
            "--frontend-digest",
            frontend_digest,
            "--output",
            output,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "schema_version": "1999wiki.release/v1",
        "commit": commit,
        "images": {
            "backend": {
                "tag": "ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0",
                "digest": backend_digest,
                "ref": (
                    "ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0@"
                    + backend_digest
                ),
            },
            "frontend": {
                "tag": "ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0",
                "digest": frontend_digest,
                "ref": (
                    "ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0@"
                    + frontend_digest
                ),
            },
        },
    }
    verified = subprocess.run(
        [
            sys.executable,
            MANIFEST_BUILDER,
            "verify",
            "--manifest",
            output,
            "--commit",
            commit,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert verified.returncode == 0, verified.stdout + verified.stderr
    assert verified.stdout.splitlines() == [
        f"RELEASE_COMMIT={commit}",
        (
            "BACKEND_IMAGE="
            "ghcr.io/ddomelette/1999wiki-backend:sha-abcdef0@"
            + backend_digest
        ),
        (
            "FRONTEND_IMAGE="
            "ghcr.io/ddomelette/1999wiki-frontend:sha-abcdef0@"
            + frontend_digest
        ),
    ]
