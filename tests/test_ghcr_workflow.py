from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "publish-images.yml"


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

    forbidden = ("ssh", "deploy", "deployment")
    assert not any(token in WORKFLOW.read_text(encoding="utf-8").casefold() for token in forbidden)
