"""Unit tests for Docker Compose service-status parsing."""

from tests.helpers.compose import parse_compose_ps_output


COMPOSE_SERVICES = [
    {
        "Name": "corp-kb-ingestion-postgres-1",
        "Service": "postgres",
        "State": "running",
        "Health": "healthy",
    },
    {
        "Name": "corp-kb-ingestion-azurite-1",
        "Service": "azurite",
        "State": "running",
        "Health": "healthy",
    },
]


def test_parses_compose_ps_json_array() -> None:
    """Compose v2's JSON array format gives all reported services."""
    output = """[
  {"Name": "corp-kb-ingestion-postgres-1", "Service": "postgres", "State": "running", "Health": "healthy"},
  {"Name": "corp-kb-ingestion-azurite-1", "Service": "azurite", "State": "running", "Health": "healthy"}
]"""

    assert parse_compose_ps_output(output) == COMPOSE_SERVICES


def test_parses_compose_ps_json_lines() -> None:
    """Compose v5's JSON Lines format gives all reported services."""
    output = """{"Name": "corp-kb-ingestion-postgres-1", "Service": "postgres", "State": "running", "Health": "healthy"}
{"Name": "corp-kb-ingestion-azurite-1", "Service": "azurite", "State": "running", "Health": "healthy"}
"""

    assert parse_compose_ps_output(output) == COMPOSE_SERVICES


def test_parses_empty_compose_ps_output() -> None:
    """No Compose output means no services are reported."""
    assert parse_compose_ps_output("") == []
