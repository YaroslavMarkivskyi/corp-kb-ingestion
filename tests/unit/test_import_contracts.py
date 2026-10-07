"""Tests for the repository import-linter dependency contracts."""

from pathlib import Path
import shutil
import subprocess

import pytest


ROOT_PACKAGES = (
    "source",
    "delta",
    "extraction",
    "chunking",
    "embedding",
    "store",
    "reporting",
    "flows",
    "config",
)


def _sample_project(
    tmp_path: Path, importing_package: str, imported_packages: tuple[str, ...]
) -> Path:
    """Create a minimal project that uses the repository import-linter config."""
    project = tmp_path / "sample_project"
    project.mkdir()
    shutil.copyfile(Path(__file__).parents[2] / ".importlinter", project / ".importlinter")

    for package in ROOT_PACKAGES:
        package_directory = project / package
        package_directory.mkdir()
        (package_directory / "__init__.py").touch()

    imports = "\n".join(f"import {package}" for package in imported_packages)
    (project / importing_package / "__init__.py").write_text(f"{imports}\n")
    return project


def _lint_imports(project: Path) -> subprocess.CompletedProcess[str]:
    """Run the configured import-linter contracts for a sample project."""
    lint_imports = shutil.which("lint-imports")
    assert lint_imports is not None, "import-linter must provide lint-imports"

    return subprocess.run(
        (lint_imports,),
        capture_output=True,
        check=False,
        cwd=project,
        text=True,
    )


def test_flows_may_import_every_architecture_layer(tmp_path: Path) -> None:
    """Flows may coordinate every layer named in the Architecture."""
    project = _sample_project(
        tmp_path,
        "flows",
        ("store", "extraction", "embedding", "source", "delta", "chunking", "reporting"),
    )

    result = _lint_imports(project)

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("importing_package", "imported_package"),
    (
        ("extraction", "store"),
        ("embedding", "store"),
        ("source", "store"),
        ("store", "extraction"),
        ("store", "embedding"),
        ("store", "source"),
        ("chunking", "store"),
        ("chunking", "extraction"),
        ("chunking", "embedding"),
        ("chunking", "reporting"),
        ("chunking", "flows"),
        ("chunking", "azure"),
        ("chunking", "psycopg"),
        ("chunking", "psycopg2"),
        ("chunking", "sqlalchemy"),
        ("chunking", "requests"),
        ("chunking", "httpx"),
        ("chunking", "openai"),
        ("chunking", "boto3"),
    ),
)
def test_architecture_forbidden_imports_are_rejected(
    tmp_path: Path, importing_package: str, imported_package: str
) -> None:
    """The import contracts reject each dependency forbidden by the Architecture."""
    project = _sample_project(tmp_path, importing_package, (imported_package,))

    result = _lint_imports(project)

    assert result.returncode != 0, result.stdout + result.stderr
