"""Smoke tests for the top-level module packages."""

from importlib import import_module

import pytest


@pytest.mark.parametrize(
    "package_name",
    (
        "source",
        "delta",
        "extraction",
        "chunking",
        "embedding",
        "store",
        "reporting",
        "flows",
        "config",
    ),
)
def test_module_package_can_be_imported(package_name: str) -> None:
    """Each top-level module package is importable."""
    assert import_module(package_name)
