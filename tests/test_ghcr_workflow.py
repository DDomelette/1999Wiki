from __future__ import annotations

import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PUBLISH_WORKFLOW = ROOT / ".github" / "workflows" / "publish-images.yml"
BACKFILL_WORKFLOW = ROOT / ".github" / "workflows" / "backfill-ghcr.yml"
TAG_GUARD = ROOT / ".github" / "scripts" / "refuse-existing-image-tags.sh"


def _workflow(path: Path) -> dict[str, object]:
    assert path.is_file(), f"{path.name} is missing"
    payload = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert isinstance(payload, dict)
    return payload


def _jobs(workflow: dict[str, object]) -> dict[str, dict[str, object]]:
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict)
    assert all(isinstance(job, dict) for job in jobs.values())
    return jobs  # type: ignore[return-value]


def _steps(job: dict[str, object]) -> list[dict[str, object]]:
    steps = job.get("steps")
    assert isinstance(steps, list)
    assert all(isinstance(step, dict) for step in steps)
    return steps  # type: ignore[return-value]


def _uses(
    job: dict[str, object],
    action: str,
    *,
    count: int = 1,
) -> list[dict[str, object]]:
    matches = [step for step in _steps(job) if step.get("uses") == action]
    assert len(matches) == count, f"{action} must be used exactly {count} time(s)"
    return matches


def _run_steps(job: dict[str, object]) -> list[dict[str, object]]:
    return [step for step in _steps(job) if "run" in step]


def _run_text(job: dict[str, object]) -> str:
    return "\n".join(str(step["run"]) for step in _run_steps(job))


def _step_running(job: dict[str, object], fragment: str) -> dict[str, object]:
    matches = [
        step for step in _run_steps(job) if fragment in str(step.get("run", ""))
    ]
    assert len(matches) == 1, f"expected one run step containing {fragment!r}"
    return matches[0]


def _step_id(job: dict[str, object], step_id: str) -> dict[str, object]:
    matches = [step for step in _steps(job) if step.get("id") == step_id]
    assert len(matches) == 1, f"expected one step with id {step_id!r}"
    return matches[0]


def _assert_no_secret_expressions_in_run(workflow: dict[str, object]) -> None:
    for job in _jobs(workflow).values():
        for step in _run_steps(job):
            assert "secrets." not in str(step["run"])


def _assert_no_deployment_surface(path: Path) -> None:
    source = path.read_text(encoding="utf-8").casefold()
    for forbidden in (
        r"\bssh\b",
        r"\bscp\b",
        r"docker\s+compose",
        r"\bappleboy\b",
        r"\bcos\b",
        r"\bdeploy(?:ment)?\b",
        r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    ):
        assert re.search(forbidden, source) is None, (
            f"{path.name} contains forbidden deployment surface {forbidden!r}"
        )


def test_publish_builds_once_after_independent_test_jobs() -> None:
    workflow = _workflow(PUBLISH_WORKFLOW)

    assert set(workflow["on"]) == {"workflow_dispatch"}
    jobs = _jobs(workflow)
    assert set(jobs) == {"python-tests", "frontend-tests", "publish"}
    python = jobs["python-tests"]
    frontend = jobs["frontend-tests"]
    publish = jobs["publish"]

    _uses(python, "actions/setup-python@v5")
    _uses(python, "docker/setup-buildx-action@v3")
    python_commands = _run_text(python)
    assert "pip install -r requirements/dev.lock.txt" in python_commands
    assert "python -m pytest -q" in python_commands

    _uses(frontend, "actions/setup-node@v4")
    frontend_commands = _run_text(frontend)
    assert "npm ci" in frontend_commands
    assert "npm test" in frontend_commands
    assert "npm run build" in frontend_commands

    assert publish["needs"] == ["python-tests", "frontend-tests"]
    _uses(publish, "docker/setup-buildx-action@v3")
    builds = _uses(publish, "docker/build-push-action@v6", count=2)
    by_id = {str(step.get("id")): step for step in builds}
    assert set(by_id) == {"backend", "frontend"}
    for component, dockerfile in (
        ("backend", "docker/Dockerfile.backend"),
        ("frontend", "docker/Dockerfile.frontend"),
    ):
        build = by_id[component]
        inputs = build["with"]
        assert isinstance(inputs, dict)
        assert inputs["context"] == "."
        assert inputs["file"] == dockerfile
        assert inputs["platforms"] == "linux/amd64"
        assert inputs["push"] == "false"
        assert inputs["outputs"] == (
            f"type=oci,dest=${{{{ runner.temp }}}}/{component}.oci"
        )
        assert "tags" not in inputs

    skopeo = _step_running(publish, "apt-get install --yes skopeo")
    assert "skopeo --version" in str(skopeo["run"])

    uploads = _uses(publish, "actions/upload-artifact@v4", count=2)
    uploaded_paths = {str(step["with"]["path"]) for step in uploads}
    assert uploaded_paths == {
        "release-manifest.json",
        "publication-failure.json",
    }
    assert not any(path.endswith(".oci") for path in uploaded_paths)


def test_publish_grants_package_write_only_to_the_publish_job() -> None:
    workflow = _workflow(PUBLISH_WORKFLOW)
    jobs = _jobs(workflow)

    assert workflow["permissions"] == {"contents": "read"}
    for test_job in ("python-tests", "frontend-tests"):
        effective = jobs[test_job].get("permissions", workflow["permissions"])
        assert effective == {"contents": "read"}
        assert "packages" not in effective
    assert jobs["publish"]["permissions"] == {
        "contents": "read",
        "packages": "write",
    }


def test_publish_passes_registry_credentials_only_through_environment() -> None:
    workflow = _workflow(PUBLISH_WORKFLOW)
    publish = _jobs(workflow)["publish"]
    publisher = _step_running(
        publish,
        "python3 .github/scripts/publish_registries.py",
    )

    assert publisher.get("id") == "publisher"
    assert publisher["env"] == {
        "TCR_USERNAME": "${{ secrets.TCR_USERNAME }}",
        "TCR_PASSWORD": "${{ secrets.TCR_PASSWORD }}",
        "TCR_REGISTRY": "${{ vars.TCR_REGISTRY }}",
        "TCR_NAMESPACE": "${{ vars.TCR_NAMESPACE }}",
        "GHCR_USERNAME": "${{ github.actor }}",
        "GHCR_PASSWORD": "${{ secrets.GITHUB_TOKEN }}",
    }
    command = str(publisher["run"])
    for expected in (
        '--commit "$GITHUB_SHA"',
        '--backend-archive "${RUNNER_TEMP}/backend.oci"',
        '--frontend-archive "${RUNNER_TEMP}/frontend.oci"',
        '--authfile "${RUNNER_TEMP}/1999wiki-auth.json"',
        "--manifest-output release-manifest.json",
        "--failure-output publication-failure.json",
        '--workflow-run-id "$GITHUB_RUN_ID"',
    ):
        assert expected in command
    _assert_no_secret_expressions_in_run(workflow)


def test_publish_uploads_only_post_success_manifest_or_guarded_failure() -> None:
    workflow = _workflow(PUBLISH_WORKFLOW)
    publish = _jobs(workflow)["publish"]
    steps = _steps(publish)
    publisher = _step_running(
        publish,
        "python3 .github/scripts/publish_registries.py",
    )
    uploads = _uses(publish, "actions/upload-artifact@v4", count=2)
    by_path = {str(step["with"]["path"]): step for step in uploads}
    manifest = by_path["release-manifest.json"]
    failure = by_path["publication-failure.json"]

    assert steps.index(publisher) < steps.index(manifest)
    assert manifest["if"] == "${{ success() }}"
    assert manifest["with"]["name"] == "release-${{ steps.tag.outputs.tag }}"
    assert failure["if"] == (
        "${{ failure() && hashFiles('publication-failure.json') != '' }}"
    )
    assert failure["with"]["if-no-files-found"] == "error"

    summary = _step_id(publish, "summary")
    summary_command = str(summary["run"])
    for canonical_field in (
        "commit",
        "release_tag",
        "release_state",
        "images",
        "registries",
        "status",
        "ref",
    ):
        assert canonical_field in summary_command
    for forbidden in (
        "steps.backend.outputs",
        "steps.frontend.outputs",
        "GITHUB_SHA",
        "GITHUB_RUN_ID",
    ):
        assert forbidden not in summary_command

    assert ".github/scripts/refuse-existing-image-tags.sh" not in _run_text(publish)
    assert not TAG_GUARD.exists()


def test_backfill_downloads_exact_release_and_calls_validating_cli() -> None:
    workflow = _workflow(BACKFILL_WORKFLOW)

    assert set(workflow["on"]) == {"workflow_dispatch"}
    dispatch = workflow["on"]["workflow_dispatch"]
    assert isinstance(dispatch, dict)
    inputs = dispatch["inputs"]
    assert isinstance(inputs, dict)
    assert set(inputs) == {"release_run_id", "release_tag", "expected_commit"}
    for name in inputs:
        assert inputs[name]["required"] == "true"

    assert workflow["permissions"] == {
        "contents": "read",
        "actions": "read",
        "packages": "write",
    }
    assert workflow["concurrency"] == {
        "group": (
            "publish-images-${{ inputs.expected_commit }}-ghcr-backfill"
        ),
        "cancel-in-progress": "false",
    }
    jobs = _jobs(workflow)
    assert set(jobs) == {"backfill"}
    backfill = jobs["backfill"]

    download = _uses(backfill, "actions/download-artifact@v4")[0]
    assert download["with"]["run-id"] == "${{ inputs.release_run_id }}"
    assert download["with"]["name"] == "release-${{ inputs.release_tag }}"
    assert download["with"]["path"] == "release-input"

    validation = _step_running(backfill, "^sha-[0-9a-f]{7}$")
    validation_command = str(validation["run"])
    assert _steps(backfill).index(validation) < _steps(backfill).index(download)
    assert (
        '[[ ! "$RELEASE_RUN_ID" =~ ^[1-9][0-9]*$ ]]'
        in validation_command
    )
    assert "^[0-9a-f]{40}$" in validation_command
    assert 'sha-${EXPECTED_COMMIT:0:7}' in validation_command
    assert validation["env"] == {
        "RELEASE_RUN_ID": "${{ inputs.release_run_id }}",
        "RELEASE_TAG": "${{ inputs.release_tag }}",
        "EXPECTED_COMMIT": "${{ inputs.expected_commit }}",
    }
    assert "inputs.release_run_id" not in validation_command

    run_id_pattern = re.compile(r"[1-9][0-9]*", flags=re.ASCII)
    for accepted in ("1", "9", "10", "123456790"):
        assert run_id_pattern.fullmatch(accepted)
    for rejected in (
        "",
        "0",
        "+1",
        "-1",
        " 1",
        "1 ",
        "01",
        "123abc",
        "1e3",
        "１２３",
        "١٢٣",
    ):
        assert run_id_pattern.fullmatch(rejected) is None

    skopeo = _step_running(backfill, "apt-get install --yes skopeo")
    assert "skopeo --version" in str(skopeo["run"])

    command_step = _step_running(
        backfill,
        "python3 .github/scripts/backfill_ghcr.py",
    )
    assert command_step["env"] == {
        "EXPECTED_COMMIT": "${{ inputs.expected_commit }}",
        "TCR_USERNAME": "${{ secrets.TCR_USERNAME }}",
        "TCR_PASSWORD": "${{ secrets.TCR_PASSWORD }}",
        "TCR_REGISTRY": "${{ vars.TCR_REGISTRY }}",
        "TCR_NAMESPACE": "${{ vars.TCR_NAMESPACE }}",
        "GHCR_USERNAME": "${{ github.actor }}",
        "GHCR_PASSWORD": "${{ secrets.GITHUB_TOKEN }}",
    }
    command = str(command_step["run"])
    for expected in (
        "--manifest release-input/release-manifest.json",
        '--commit "$EXPECTED_COMMIT"',
        '--authfile "${RUNNER_TEMP}/1999wiki-backfill-auth.json"',
        "--attestation-output mirror-attestation.json",
        "--failure-output mirror-failure.json",
        '--workflow-run-id "$GITHUB_RUN_ID"',
        "--completed-at",
    ):
        assert expected in command
    _assert_no_secret_expressions_in_run(workflow)


def test_backfill_uploads_only_attestation_or_guarded_failure() -> None:
    workflow = _workflow(BACKFILL_WORKFLOW)
    backfill = _jobs(workflow)["backfill"]
    uploads = _uses(backfill, "actions/upload-artifact@v4", count=2)
    by_path = {str(step["with"]["path"]): step for step in uploads}
    assert set(by_path) == {"mirror-attestation.json", "mirror-failure.json"}

    attestation = by_path["mirror-attestation.json"]
    assert attestation["if"] == "${{ success() }}"
    assert attestation["with"]["name"] == (
        "mirror-${{ inputs.release_tag }}-${{ github.run_id }}"
    )
    failure = by_path["mirror-failure.json"]
    assert failure["if"] == (
        "${{ failure() && hashFiles('mirror-failure.json') != '' }}"
    )
    assert failure["with"]["if-no-files-found"] == "error"

    assert not _uses(backfill, "docker/build-push-action@v6", count=0)


def test_workflows_have_no_deployment_or_server_operations() -> None:
    _assert_no_deployment_surface(PUBLISH_WORKFLOW)
    _assert_no_deployment_surface(BACKFILL_WORKFLOW)
