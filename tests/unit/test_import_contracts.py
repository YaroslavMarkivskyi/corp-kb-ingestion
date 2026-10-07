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

EXTERNAL_PACKAGES = (
    "azure",
    "psycopg",
    "psycopg2",
    "sqlalchemy",
    "requests",
    "httpx",
    "openai",
    "boto3",
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

    for package in EXTERNAL_PACKAGES:
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
    ("importing_package", "imported_package", "contract_name"),
    (
        ("extraction", "store", "Layers must not import store"),
        ("embedding", "store", "Layers must not import store"),
        ("source", "store", "Layers must not import store"),
        ("store", "extraction", "Store must not import layers"),
        ("store", "embedding", "Store must not import layers"),
        ("store", "source", "Store must not import layers"),
        (
            "chunking",
            "store",
            "Chunking must not import layers or I/O libraries",
        ),
        (
            "chunking",
            "extraction",
            "Chunking must not import layers or I/O libraries",
        ),
        (
            "chunking",
            "embedding",
            "Chunking must not import layers or I/O libraries",
        ),
        (
            "chunking",
            "reporting",
            "Chunking must not import layers or I/O libraries",
        ),
        (
            "chunking",
            "flows",
            "Chunking must not import layers or I/O libraries",
        ),
        (
            "chunking",
            "azure",
            "Chunking must not import layers or I/O libraries",
        ),
        (
            "chunking",
            "psycopg",
            "Chunking must not import layers or I/O libraries",
        ),
        (
            "chunking",
            "psycopg2",
            "Chunking must not import layers or I/O libraries",
        ),
        (
            "chunking",
            "sqlalchemy",
            "Chunking must not import layers or I/O libraries",
        ),
        (
            "chunking",
            "requests",
            "Chunking must not import layers or I/O libraries",
        ),
        (
            "chunking",
            "httpx",
            "Chunking must not import layers or I/O libraries",
        ),
        (
            "chunking",
            "openai",
            "Chunking must not import layers or I/O libraries",
        ),
        (
            "chunking",
            "boto3",
            "Chunking must not import layers or I/O libraries",
        ),
    ),
)
def test_architecture_forbidden_imports_are_rejected(
    tmp_path: Path,
    importing_package: str,
    imported_package: str,
    contract_name: str,
) -> None:
    """The intended forbidden contract rejects each architectural violation."""
    project = _sample_project(tmp_path, importing_package, (imported_package,))

    result = _lint_imports(project)

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert f"{contract_name} BROKEN" in output
    assert f"{importing_package} is not allowed to import {imported_package}" in output
