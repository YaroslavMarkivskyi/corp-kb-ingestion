"""Helpers for Docker Compose command output."""

import json


def parse_compose_ps_output(output: str) -> list[dict[str, object]]:
    """Parse Docker Compose ps JSON array and JSON Lines output."""
    output = output.strip()
    if not output:
        return []
    if output.startswith("["):
        return json.loads(output)
    return [json.loads(line) for line in output.splitlines() if line.strip()]
