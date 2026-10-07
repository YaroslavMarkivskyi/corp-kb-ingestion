"""Integration coverage for the local PostgreSQL/pgvector and Azurite stack."""

import json
import os
from pathlib import Path
import subprocess
from typing import Iterator

import pytest


PROJECT_ROOT = Path(__file__).parents[2]
EXAMPLE_ENVIRONMENT_FILE = PROJECT_ROOT / ".env.example"
POSTGRES_PORT = 5432


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
    return settings


@pytest.fixture(scope="module")
def example_environment() -> dict[str, str]:
    """Load the settings used to configure and connect to the local services."""
    settings = _read_example_environment()
    expected_settings = {
        "KB_PG_HOST",
        "KB_PG_DB",
        "KB_PG_USER",
        "KB_PG_PASSWORD",
        "KB_BLOB_ACCOUNT_URL",
        "KB_BLOB_CONTAINER",
    }
    assert expected_settings <= settings.keys()
    return settings


@pytest.fixture(scope="module", autouse=True)
def local_stack(example_environment: dict[str, str]) -> Iterator[None]:
    """Start the Compose stack once and always stop it when the module is done."""
    compose_environment = {**os.environ, **example_environment}
    subprocess.run(
        ("docker", "compose", "up", "-d", "--wait"),
        check=True,
        cwd=PROJECT_ROOT,
        env=compose_environment,
    )
    try:
        yield
    finally:
        subprocess.run(
            ("docker", "compose", "down", "--volumes"),
            check=True,
            cwd=PROJECT_ROOT,
            env=compose_environment,
        )


def test_postgresql_answers_with_example_settings_and_pgvector(
    example_environment: dict[str, str],
) -> None:
    """PostgreSQL authenticates the example user to its example database with pgvector."""
    import psycopg

    with psycopg.connect(
        host=example_environment["KB_PG_HOST"],
        port=POSTGRES_PORT,
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


def test_azurite_creates_and_deletes_example_container(
    example_environment: dict[str, str],
) -> None:
    """Azurite accepts Blob Storage operations against the example container."""
    from azure.core.credentials import AzureNamedKeyCredential
    from azure.storage.blob import BlobServiceClient

    blob_service = BlobServiceClient(
        account_url=example_environment["KB_BLOB_ACCOUNT_URL"],
        credential=AzureNamedKeyCredential(
            "devstoreaccount1",
            "Eby8vdM02xNOcqFeqCnf2o==",
        ),
    )
    container = blob_service.get_container_client(example_environment["KB_BLOB_CONTAINER"])

    container.create_container()
    try:
        assert container.exists()
    finally:
        container.delete_container()


def test_all_local_services_report_healthy(
    example_environment: dict[str, str],
) -> None:
    """Compose reports the two local services as healthy after waiting for startup."""
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
