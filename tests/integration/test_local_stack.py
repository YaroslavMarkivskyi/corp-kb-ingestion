"""Acceptance test for the local PostgreSQL/pgvector and Azurite stack."""

from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).parents[2]
COMPOSE_FILE = PROJECT_ROOT / "compose.yaml"


def _service_definition(compose: str, service_name: str) -> str:
    """Return one top-level Compose service definition."""
    service = re.search(
        rf"^  {service_name}:\n(?P<definition>.*?)(?=^  [^ ].*?:\n|\Z)",
        compose,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert service is not None, f"Compose must define a {service_name!r} service"
    return service.group("definition")


def test_compose_defines_local_pgvector_and_azurite_services() -> None:
    """The local stack uses pgvector PostgreSQL and exposes Azurite Blob Storage."""
    assert COMPOSE_FILE.is_file(), "compose.yaml must define the local development stack"
    compose = COMPOSE_FILE.read_text()

    postgres = _service_definition(compose, "postgres")
    assert re.search(r"^    image: pgvector/pgvector(?:[:@][^\s]+)?$", postgres, re.MULTILINE)
    assert re.search(r"^      - [\"']?5432:5432[\"']?$", postgres, re.MULTILINE)

    azurite = _service_definition(compose, "azurite")
    assert re.search(
        r"^    image: mcr\.microsoft\.com/azure-storage/azurite(?:[:@][^\s]+)?$",
        azurite,
        re.MULTILINE,
    )
    assert re.search(r"^      - [\"']?10000:10000[\"']?$", azurite, re.MULTILINE)
