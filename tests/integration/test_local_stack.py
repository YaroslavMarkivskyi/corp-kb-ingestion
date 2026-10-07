"""Smoke test for the local PostgreSQL and Azurite services."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[2]
AZURITE_DEV_ACCOUNT_KEY = "Eby8vdM02xNOcqFeqCnf2o=="


def _example_environment() -> dict[str, str]:
    """Load the local-only variables supplied to developers."""
    environment_file = PROJECT_ROOT / ".env.example"
    assert environment_file.is_file(), ".env.example must document local settings"

    environment: dict[str, str] = {}
    for line in environment_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, separator, value = line.partition("=")
            assert separator, f"invalid environment line: {line}"
            environment[key] = value

    return environment


def test_local_stack_accepts_connections_using_example_environment() -> None:
    """PostgreSQL exposes pgvector and Azurite serves the configured container."""
    environment = _example_environment()
    expected_variables = {
        "KB_PG_HOST",
        "KB_PG_DB",
        "KB_PG_USER",
        "KB_BLOB_ACCOUNT_URL",
        "KB_BLOB_CONTAINER",
    }
    assert expected_variables <= environment.keys()

    import psycopg
    from azure.storage.blob import BlobServiceClient

    with psycopg.connect(
        dbname=environment["KB_PG_DB"],
        host=environment["KB_PG_HOST"],
        user=environment["KB_PG_USER"],
        connect_timeout=5,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            assert cursor.fetchone() is not None

    blob_service = BlobServiceClient(
        account_url=environment["KB_BLOB_ACCOUNT_URL"],
        credential=AZURITE_DEV_ACCOUNT_KEY,
    )
    container = blob_service.get_container_client(environment["KB_BLOB_CONTAINER"])
    if not container.exists():
        container.create_container()
    assert container.exists()
