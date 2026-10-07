"""Integration coverage for the local PostgreSQL/pgvector and Azurite stack."""

import json
import os
from pathlib import Path
import re
import socket
import subprocess
from urllib.parse import urlparse
from uuid import uuid4

import pytest


PROJECT_ROOT = Path(__file__).parents[2]
EXAMPLE_ENVIRONMENT_FILE = PROJECT_ROOT / ".env.example"


def _read_example_environment() -> dict[str, str]:
    """Read the local settings without requiring a dotenv dependency."""
    assert EXAMPLE_ENVIRONMENT_FILE.is_file(), \
        ".env.example must provide the settings for the local stack"

    settings: dict[str, str] = {}
    for line in EXAMPLE_ENVIRONMENT_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, value = line.split("=", maxsplit=1)
        settings[name] = value
    return {
        name: re.sub(
            r"\$\{([A-Z_]+)\}",
            lambda match: settings[match.group(1)],
            value,
        )
        for name, value in settings.items()
    }


def _available_host_port() -> int:
    """Choose an unused loopback port number for an isolated Compose project."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _published_port(compose_config: dict[str, object], service_name: str) -> str:
    """Return the published host port for the service's sole TCP port."""
    services = compose_config["services"]
    assert isinstance(services, dict)
    service = services[service_name]
    assert isinstance(service, dict)
    ports = service["ports"]
    assert isinstance(ports, list) and len(ports) == 1
    port = ports[0]
    assert isinstance(port, dict)
    return str(port["published"])


def test_compose_runs_an_isolated_stack_on_changed_noncolliding_host_ports() -> None:
    """Compose binds both services to distinct host ports supplied at runtime."""
    postgres_port = _available_host_port()
    azurite_port = _available_host_port()
    while azurite_port == postgres_port:
        azurite_port = _available_host_port()

    environment = {
        **os.environ,
        **_read_example_environment(),
        "KB_PG_PORT": str(postgres_port),
        "KB_BLOB_PORT": str(azurite_port),
        "KB_BLOB_ACCOUNT_URL": (
            f"http://127.0.0.1:{azurite_port}/devstoreaccount1"
        ),
    }
    rendered_config = subprocess.run(
        ("docker", "compose", "config", "--format", "json"),
        capture_output=True,
        check=True,
        cwd=PROJECT_ROOT,
        env=environment,
        text=True,
    )
    compose_config = json.loads(rendered_config.stdout)

    assert _published_port(compose_config, "postgres") == str(postgres_port)
    assert _published_port(compose_config, "azurite") == str(azurite_port)
    assert postgres_port != azurite_port

    project_name = f"port-test-{uuid4().hex}"
    started = False
    try:
        subprocess.run(
            (
                "docker",
                "compose",
                "--project-name",
                project_name,
                "up",
                "--detach",
                "--wait",
            ),
            check=True,
            cwd=PROJECT_ROOT,
            env=environment,
            text=True,
            timeout=60,
        )
        started = True

        import psycopg
        from azure.core.credentials import AzureNamedKeyCredential
        from azure.storage.blob import BlobServiceClient

        with psycopg.connect(
            host=environment["KB_PG_HOST"],
            port=postgres_port,
            dbname=environment["KB_PG_DB"],
            user=environment["KB_PG_USER"],
            password=environment["KB_PG_PASSWORD"],
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                assert cursor.fetchone() == (1,)

        blob_service = BlobServiceClient(
            account_url=environment["KB_BLOB_ACCOUNT_URL"],
            credential=AzureNamedKeyCredential(
                "devstoreaccount1",
                "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==",
            ),
        )
        container = blob_service.get_container_client(f"port-test-{uuid4().hex}")
        container.create_container()
        try:
            assert container.exists()
        finally:
            container.delete_container()
    finally:
        if started:
            subprocess.run(
                (
                    "docker",
                    "compose",
                    "--project-name",
                    project_name,
                    "down",
                    "--volumes",
                ),
                check=False,
                cwd=PROJECT_ROOT,
                env=environment,
                text=True,
            )


@pytest.fixture(scope="module")
def example_environment() -> dict[str, str]:
    """Load the settings used to configure and connect to the local services."""
    settings = _read_example_environment()
    expected_settings = {
        "KB_PG_HOST",
        "KB_PG_PORT",
        "KB_PG_DB",
        "KB_PG_USER",
        "KB_PG_PASSWORD",
        "KB_BLOB_PORT",
        "KB_BLOB_ACCOUNT_URL",
        "KB_BLOB_CONTAINER",
    }
    assert expected_settings <= settings.keys()
    return settings


def test_postgresql_answers_with_example_settings_and_pgvector(
    example_environment: dict[str, str],
) -> None:
    """PostgreSQL authenticates the example user to its example database with pgvector."""
    import psycopg

    with psycopg.connect(
        host=example_environment["KB_PG_HOST"],
        port=int(example_environment["KB_PG_PORT"]),
        dbname=example_environment["KB_PG_DB"],
        user=example_environment["KB_PG_USER"],
        password=example_environment["KB_PG_PASSWORD"],
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user")
            assert cursor.fetchone() == (
                example_environment["KB_PG_DB"],
                example_environment["KB_PG_USER"],
            )
            cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            assert cursor.fetchone() == (1,)


def test_azurite_creates_and_deletes_unique_container(
    example_environment: dict[str, str],
) -> None:
    """Azurite creates and deletes only a unique container for this test run."""
    from azure.core.credentials import AzureNamedKeyCredential
    from azure.storage.blob import BlobServiceClient

    blob_port = int(example_environment["KB_BLOB_PORT"])
    assert urlparse(example_environment["KB_BLOB_ACCOUNT_URL"]).port == blob_port

    blob_service = BlobServiceClient(
        account_url=example_environment["KB_BLOB_ACCOUNT_URL"],
        credential=AzureNamedKeyCredential(
            "devstoreaccount1",
            "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==",
        ),
    )
    container_name = f"{example_environment['KB_BLOB_CONTAINER']}-{uuid4().hex}"
    container = blob_service.get_container_client(container_name)

    created = False
    try:
        container.create_container()
        created = True
        assert container.exists()
    finally:
        if created:
            container.delete_container()
    assert not container.exists()


def test_all_local_services_report_healthy(
    example_environment: dict[str, str],
) -> None:
    """The already-running Compose services report healthy."""
    result = subprocess.run(
        ("docker", "compose", "ps", "--format", "json"),
        capture_output=True,
        check=True,
        cwd=PROJECT_ROOT,
        env={**os.environ, **example_environment},
        text=True,
    )
    services = json.loads(result.stdout)
    if isinstance(services, dict):
        services = [services]

    health_by_service = {service["Service"]: service["Health"] for service in services}
    assert health_by_service == {"postgres": "healthy", "azurite": "healthy"}
