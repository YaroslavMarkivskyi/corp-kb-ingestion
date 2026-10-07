"""Smoke tests for the top-level module packages."""

from importlib import import_module
from pathlib import Path
import shutil
import subprocess

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
    import_module(package_name)


def test_import_linter_contracts_pass() -> None:
    """The configured import-linter contracts all pass."""
    lint_imports = shutil.which("lint-imports")
    assert lint_imports is not None, "import-linter must provide lint-imports"

    result = subprocess.run(
        (lint_imports,),
        capture_output=True,
        check=False,
        cwd=Path(__file__).parents[2],
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
