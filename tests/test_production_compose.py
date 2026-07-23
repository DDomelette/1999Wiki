from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy"
INFRA_COMPOSE = DEPLOY / "compose.infra.yml"
APP_COMPOSE = DEPLOY / "compose.app.yml"
INFRA_ENV = DEPLOY / "env" / "infra.env.example"
APP_ENV = DEPLOY / "env" / "app.env.example"
RELEASE_ENV = DEPLOY / "env" / "release.env.example"

EXPECTED_INFRA_IMAGES = {
    "mysql": "mysql:8.0.46-bookworm",
    "minio": "minio/minio:RELEASE.2025-09-07T16-13-09Z",
    "etcd": "quay.io/coreos/etcd:v3.5.25",
    "standalone": "milvusdb/milvus:v2.5.27",
    "attu": "zilliz/attu:v2.6.5",
}
EXPECTED_INFRA_MOUNTS = {
    "mysql": "/srv/1999wiki/mysql:/var/lib/mysql",
    "minio": "/srv/1999wiki/minio:/minio_data",
    "etcd": "/srv/1999wiki/etcd:/etcd",
    "standalone": "/srv/1999wiki/milvus:/var/lib/milvus",
}
REQUIRED_RUNTIME_KEYS = {
    "APP_ENV",
    "MILVUS_URI",
    "MILVUS_DB_NAME",
    "MILVUS_COLLECTION_NAME",
    "MINIO_ENDPOINT",
    "MINIO_SECURE",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
    "MINIO_BUCKET",
    "MEDIA_PUBLIC_BASE_URL",
    "MYSQL_HOST",
    "MYSQL_PORT",
    "MYSQL_DATABASE",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "HUIJI_PROCESSED_ROOT",
}
INFRA_SECRET_KEYS = {
    "MYSQL_ROOT_PASSWORD",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "MINIO_ROOT_USER",
    "MINIO_ROOT_PASSWORD",
}
APP_SECRET_KEYS = {
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
}


def _read(path: Path) -> str:
    assert path.is_file(), f"required production Compose file is missing: {path.relative_to(ROOT)}"
    return path.read_text(encoding="utf-8")


def _compose(path: Path) -> dict[str, Any]:
    parsed = yaml.safe_load(_read(path))
    assert isinstance(parsed, dict), f"{path.name} must contain a YAML mapping"
    assert isinstance(parsed.get("services"), dict), f"{path.name} must define services"
    return parsed


def _environment_map(service: dict[str, Any]) -> dict[str, str]:
    environment = service.get("environment", {})
    if isinstance(environment, dict):
        return {str(key): str(value) for key, value in environment.items()}
    assert isinstance(environment, list)
    return {
        item.split("=", 1)[0]: item.split("=", 1)[1]
        for item in environment
        if isinstance(item, str) and "=" in item
    }


def _env_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    for raw_line in _read(path).splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            keys.add(line.split("=", 1)[0])
    return keys


def _env_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in _read(path).splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def _validation_app_env(tmp_path: Path) -> Path:
    values = _env_values(APP_ENV)
    values.update(
        {
            "MINIO_ACCESS_KEY": "compose-validation-user",
            "MINIO_SECRET_KEY": "compose-validation-not-a-secret",
            "MYSQL_USER": "compose-validation-user",
            "MYSQL_PASSWORD": "compose-validation-not-a-secret",
        }
    )
    path = tmp_path / "app.env"
    path.write_text(
        "\n".join(f"{key}={value}" for key, value in values.items()) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def _service_networks(service: dict[str, Any]) -> set[str]:
    networks = service.get("networks", {"default": None})
    if isinstance(networks, list):
        return {str(network) for network in networks}
    assert isinstance(networks, dict)
    return {str(network) for network in networks}


def _assert_bounded_json_logging(service: dict[str, Any]) -> None:
    assert service["logging"] == {
        "driver": "json-file",
        "options": {"max-size": "10m", "max-file": "3"},
    }


def test_required_production_compose_and_environment_examples_exist() -> None:
    for path in (INFRA_COMPOSE, APP_COMPOSE, INFRA_ENV, APP_ENV, RELEASE_ENV):
        assert path.is_file(), f"missing {path.relative_to(ROOT)}"


def test_infrastructure_owns_pinned_persistent_services() -> None:
    compose = _compose(INFRA_COMPOSE)
    services = compose["services"]
    assert set(services) == set(EXPECTED_INFRA_IMAGES)

    for name, image in EXPECTED_INFRA_IMAGES.items():
        service = services[name]
        assert service["image"] == image
        assert service["restart"] == "unless-stopped"
        assert service.get("healthcheck", {}).get("test")
        _assert_bounded_json_logging(service)

    for name, mount in EXPECTED_INFRA_MOUNTS.items():
        assert mount in services[name]["volumes"]


def test_infrastructure_network_is_external_and_all_services_join_it() -> None:
    compose = _compose(INFRA_COMPOSE)
    assert compose["networks"] == {
        "infra": {"external": True, "name": "1999wiki-infra"}
    }
    for service in compose["services"].values():
        assert _service_networks(service) == {"infra"}


def test_milvus_waits_for_healthy_etcd_and_minio() -> None:
    depends_on = _compose(INFRA_COMPOSE)["services"]["standalone"]["depends_on"]
    assert depends_on == {
        "etcd": {"condition": "service_healthy"},
        "minio": {"condition": "service_healthy"},
    }


def test_only_minio_api_is_normally_published_and_attu_is_diagnostic_only() -> None:
    services = _compose(INFRA_COMPOSE)["services"]
    assert services["minio"]["ports"] == [
        "127.0.0.1:${MINIO_HOST_PORT:-19000}:9000"
    ]
    for name in ("mysql", "etcd", "standalone"):
        assert "ports" not in services[name]

    attu = services["attu"]
    assert attu["profiles"] == ["diagnostics"]
    assert attu["ports"] == ["127.0.0.1:${ATTU_HOST_PORT:-13001}:3000"]


def test_infrastructure_secrets_are_required_without_password_defaults() -> None:
    raw = _read(INFRA_COMPOSE)
    for variable in INFRA_SECRET_KEYS:
        assert re.search(
            rf"\$\{{{variable}:\?[^}}]+\}}", raw
        ), f"{variable} must use required interpolation"
        assert not re.search(
            rf"(?<!\$)\$\{{{variable}(?::-|-[^}}])", raw
        ), f"{variable} must not have a fallback"

    values = _env_values(INFRA_ENV)
    assert all(values[variable] == "" for variable in INFRA_SECRET_KEYS)
    instructions = _read(INFRA_ENV)
    assert "chmod 600" in instructions
    assert "outside Git" in instructions


def test_mysql_healthcheck_never_places_a_password_in_process_arguments() -> None:
    command = " ".join(
        str(part)
        for part in _compose(INFRA_COMPOSE)["services"]["mysql"]["healthcheck"]["test"]
    )
    assert command == "CMD mysqladmin ping -h 127.0.0.1 --silent"
    assert "MYSQL_ROOT_PASSWORD" not in command
    assert not re.search(r"(?:^|\s)(?:-p|--password)(?:\s|=|$)", command)


def test_application_services_have_operational_guards() -> None:
    services = _compose(APP_COMPOSE)["services"]
    assert set(services) == {"backend", "frontend"}
    for service in services.values():
        assert service["restart"] == "unless-stopped"
        assert service.get("healthcheck", {}).get("test")
        _assert_bounded_json_logging(service)

    assert services["frontend"]["depends_on"] == {
        "backend": {"condition": "service_healthy"}
    }


def test_backend_healthcheck_enforces_full_production_readiness() -> None:
    healthcheck = _compose(APP_COMPOSE)["services"]["backend"]["healthcheck"]
    assert healthcheck["test"][:3] == ["CMD", "python", "-c"]
    command = healthcheck["test"][3]
    compile(command, "<backend-compose-healthcheck>", "exec")
    assert "json.load" in command
    assert "timeout=3" in command
    assert re.search(r"""data\.get\(['"]status['"]\)\s*==\s*['"]ok['"]""", command)
    assert re.search(
        r"""data\.get\(['"]vectorstore_loaded['"]\)\s+is\s+True""", command
    )
    assert re.search(
        r"""data\.get\(['"]provenance_status['"]\)\s*==\s*['"]pass['"]""",
        command,
    )


def test_frontend_healthcheck_enforces_static_and_proxied_backend_readiness() -> None:
    healthcheck = _compose(APP_COMPOSE)["services"]["frontend"]["healthcheck"]
    assert healthcheck["test"][0] == "CMD-SHELL"
    command = healthcheck["test"][1]
    assert "wget -q -T 3 -O - http://127.0.0.1:8080/)" in command
    assert "wget -q -T 3 -O - http://127.0.0.1:8080/health)" in command
    assert '<div id="root"></div>' in command
    assert """grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"'""" in command
    assert (
        """grep -Eq '"vectorstore_loaded"[[:space:]]*:[[:space:]]*true'"""
        in command
    )
    assert (
        """grep -Eq '"provenance_status"[[:space:]]*:[[:space:]]*"pass"'"""
        in command
    )
    assert "&&" in command


def test_application_images_ports_and_rag_mount_are_release_scoped() -> None:
    services = _compose(APP_COMPOSE)["services"]
    assert services["backend"]["image"] == "${BACKEND_IMAGE:?Set BACKEND_IMAGE}"
    assert services["frontend"]["image"] == "${FRONTEND_IMAGE:?Set FRONTEND_IMAGE}"
    assert services["backend"]["ports"] == ["127.0.0.1:${BACKEND_PORT}:8000"]
    assert services["frontend"]["ports"] == ["127.0.0.1:${FRONTEND_PORT}:8080"]
    assert (
        "/srv/1999wiki/rag-artifacts:/runtime/rag/huiji:ro"
        in services["backend"]["volumes"]
    )
    assert "volumes" not in services["frontend"]
    assert services["backend"]["env_file"] == [
        "${APP_ENV_FILE:?Set APP_ENV_FILE to a protected runtime env file}"
    ]


def test_application_slot_network_stays_project_private() -> None:
    compose = _compose(APP_COMPOSE)
    services = compose["services"]
    assert _service_networks(services["backend"]) == {"default", "infra"}
    assert _service_networks(services["frontend"]) == {"default"}
    assert compose["networks"]["infra"] == {
        "external": True,
        "name": "1999wiki-infra",
    }
    assert compose["networks"]["default"] == {}
    assert "name" not in compose["networks"]["default"]

    for service in services.values():
        networks = service.get("networks", {})
        if isinstance(networks, dict):
            assert all(
                not isinstance(config, dict) or "aliases" not in config
                for config in networks.values()
            )


def test_runtime_and_release_environment_examples_are_separated() -> None:
    app_keys = _env_keys(APP_ENV)
    release_keys = _env_keys(RELEASE_ENV)
    assert REQUIRED_RUNTIME_KEYS <= app_keys
    assert {"BACKEND_IMAGE", "FRONTEND_IMAGE", "BACKEND_PORT", "FRONTEND_PORT"} == release_keys
    assert app_keys.isdisjoint(release_keys)

    app_example = _read(APP_ENV)
    assert "MILVUS_URI=http://standalone:19530" in app_example
    assert "MINIO_ENDPOINT=minio:9000" in app_example
    assert "MYSQL_HOST=mysql" in app_example
    assert "APP_ENV=production" in app_example
    assert "MEDIA_PUBLIC_BASE_URL=/media" in app_example
    assert "HUIJI_PROCESSED_ROOT=/runtime/rag/huiji" in app_example
    app_values = _env_values(APP_ENV)
    assert all(app_values[variable] == "" for variable in APP_SECRET_KEYS)
    assert "chmod 600" in app_example
    assert "outside Git" in app_example

    release_example = _read(RELEASE_ENV)
    assert "ghcr.io/ddomelette/1999wiki-backend:sha-replace-before-production" in release_example
    assert "ghcr.io/ddomelette/1999wiki-frontend:sha-replace-before-production" in release_example


def test_application_compose_rejects_missing_protected_runtime_env_path() -> None:
    docker = shutil.which("docker")
    assert docker, "Docker CLI is required to validate production Compose"

    environment = os.environ.copy()
    environment.pop("APP_ENV_FILE", None)
    result = subprocess.run(
        [
            docker,
            "compose",
            "-p",
            "1999wiki-missing-app-env",
            "--env-file",
            str(RELEASE_ENV),
            "-f",
            str(APP_COMPOSE),
            "config",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode != 0
    assert "APP_ENV_FILE" in result.stderr


@pytest.mark.parametrize(
    ("project_name", "backend_port", "frontend_port"),
    [
        ("1999wiki-blue", "18100", "18180"),
        ("1999wiki-green", "18200", "18280"),
    ],
)
def test_docker_compose_config_renders_each_application_slot(
    tmp_path: Path,
    project_name: str,
    backend_port: str,
    frontend_port: str,
) -> None:
    docker = shutil.which("docker")
    assert docker, "Docker CLI is required to validate production Compose"

    app_env = _validation_app_env(tmp_path)
    environment = os.environ.copy()
    environment.update(
        {
            "APP_ENV_FILE": str(app_env),
            "BACKEND_IMAGE": "ghcr.io/ddomelette/1999wiki-backend:sha-0123456",
            "FRONTEND_IMAGE": "ghcr.io/ddomelette/1999wiki-frontend:sha-0123456",
            "BACKEND_PORT": backend_port,
            "FRONTEND_PORT": frontend_port,
        }
    )
    result = subprocess.run(
        [
            docker,
            "compose",
            "-p",
            project_name,
            "--env-file",
            str(RELEASE_ENV),
            "-f",
            str(APP_COMPOSE),
            "config",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert f"name: {project_name}" in result.stdout


def test_docker_compose_config_renders_infrastructure_without_network_creation() -> None:
    docker = shutil.which("docker")
    assert docker, "Docker CLI is required to validate production Compose"

    environment = os.environ.copy()
    environment.update(
        {
            "MYSQL_ROOT_PASSWORD": "compose-validation-not-a-secret",
            "MYSQL_USER": "compose-validation-user",
            "MYSQL_PASSWORD": "compose-validation-not-a-secret",
            "MINIO_ROOT_USER": "compose-validation-user",
            "MINIO_ROOT_PASSWORD": "compose-validation-not-a-secret",
        }
    )
    result = subprocess.run(
        [
            docker,
            "compose",
            "-p",
            "1999wiki-infra-validation",
            "--env-file",
            str(INFRA_ENV),
            "-f",
            str(INFRA_COMPOSE),
            "config",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "name: 1999wiki-infra" in result.stdout


def test_infrastructure_example_cannot_satisfy_required_secrets() -> None:
    docker = shutil.which("docker")
    assert docker, "Docker CLI is required to validate production Compose"

    environment = os.environ.copy()
    for variable in INFRA_SECRET_KEYS:
        environment.pop(variable, None)
    result = subprocess.run(
        [
            docker,
            "compose",
            "-p",
            "1999wiki-empty-infra-secrets",
            "--env-file",
            str(INFRA_ENV),
            "-f",
            str(INFRA_COMPOSE),
            "config",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode != 0
    assert any(variable in result.stderr for variable in INFRA_SECRET_KEYS)
