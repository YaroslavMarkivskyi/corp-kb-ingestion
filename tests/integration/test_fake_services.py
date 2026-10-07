"""Red-phase integration coverage for the local fake external services."""

import json
import os
from pathlib import Path
import re
import socket
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest


PROJECT_ROOT = Path(__file__).parents[2]
EXAMPLE_ENVIRONMENT_FILE = PROJECT_ROOT / ".env.example"


def _read_example_environment() -> dict[str, str]:
    """Read local-stack settings, respecting explicit test-process overrides."""
    settings: dict[str, str] = {}
    for line in EXAMPLE_ENVIRONMENT_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            name, value = line.split("=", maxsplit=1)
            settings[name] = value

    settings.update(
        {name: os.environ[name] for name in settings if name in os.environ}
    )
    return {
        name: re.sub(
            r"\$\{([A-Z_]+)\}",
            lambda match: settings[match.group(1)],
            value,
        )
        for name, value in settings.items()
    }


@pytest.fixture(scope="module")
def fake_service_environment() -> dict[str, str]:
    """Provide the connection details and dimension shared by fake-service tests."""
    settings = _read_example_environment()
    expected_settings = {
        "KB_FAKE_DI_PORT",
        "KB_FAKE_OPENAI_PORT",
        "KB_EMBEDDING_DIMENSIONS",
    }
    assert expected_settings <= settings.keys()
    return settings


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    timeout: float = 2,
) -> tuple[int, dict[str, Any]]:
    """POST a JSON payload, returning status and decoded body even for HTTP errors."""
    request = Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


def _post_document(
    document_intelligence_url: str,
    document: bytes,
    *,
    timeout: float = 2,
) -> tuple[int, dict[str, Any]]:
    """Submit a file using the subset of the Layout API the extractor consumes."""
    request = Request(
        f"{document_intelligence_url}/documentintelligence/documentModels/"
        "prebuilt-layout:analyze?api-version=2024-11-30",
        data=document,
        headers={"Content-Type": "application/pdf"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


def _set_next_response(base_url: str, response: str) -> None:
    """Select the single canned result or failure returned by the next request."""
    status, body = _post_json(
        f"{base_url}/__fake__/control",
        {"next_response": response},
    )
    assert (status, body) == (200, {"next_response": response})


def test_fake_services_return_named_layout_embedding_and_request_targets(
    fake_service_environment: dict[str, str],
) -> None:
    """Fakes supply an extractor-ready Layout result and a configured-size vector."""
    document_intelligence_url = (
        f"http://127.0.0.1:{fake_service_environment['KB_FAKE_DI_PORT']}"
    )
    openai_url = f"http://127.0.0.1:{fake_service_environment['KB_FAKE_OPENAI_PORT']}"

    _set_next_response(document_intelligence_url, "layout-contract")
    layout_status, layout = _post_document(
        document_intelligence_url,
        b"%PDF-1.7\nminimal fake document",
    )
    assert layout_status == 200
    assert layout["modelId"] == "prebuilt-layout"
    assert layout["pages"][0]["pageNumber"] == 1
    assert layout["pages"][0]["words"][0]["confidence"] == pytest.approx(0.99)
    assert layout["paragraphs"][0]["role"] == "title"
    assert layout["paragraphs"][0]["boundingRegions"][0]["pageNumber"] == 1
    assert layout["tables"][0]["rowCount"] == 2
    assert layout["tables"][0]["columnCount"] == 2
    assert layout["tables"][0]["confidence"] == pytest.approx(0.98)

    embedding_status, embedding = _post_json(
        f"{openai_url}/v1/embeddings",
        {"input": "A report chunk", "model": "kb-embedding"},
    )
    assert embedding_status == 200
    assert embedding["object"] == "list"
    assert embedding["data"][0]["object"] == "embedding"
    assert embedding["data"][0]["index"] == 0
    assert len(embedding["data"][0]["embedding"]) == int(
        fake_service_environment["KB_EMBEDDING_DIMENSIONS"]
    )

    for base_url, expected_target in (
        (
            document_intelligence_url,
            "/documentintelligence/documentModels/prebuilt-layout:analyze",
        ),
        (openai_url, "/v1/embeddings"),
    ):
        with urlopen(f"{base_url}/__fake__/requests") as response:
            recorded_requests = json.loads(response.read())["requests"]
        assert any(request["target"] == expected_target for request in recorded_requests)


@pytest.mark.parametrize(
    ("service", "next_response", "request_kind", "expected_status", "expected_code"),
    [
        ("document_intelligence", "too_many_requests", "document", 429, "too_many_requests"),
        ("openai", "password_protected", "embedding", 403, "password_protected"),
        ("document_intelligence", "invalid_file", "document", 422, "invalid_file"),
    ],
)
def test_fake_services_can_fail_the_next_request_as_configured(
    fake_service_environment: dict[str, str],
    service: str,
    next_response: str,
    request_kind: str,
    expected_status: int,
    expected_code: str,
) -> None:
    """Tests can make either fake return the documented next-request failure."""
    base_url = (
        f"http://127.0.0.1:{fake_service_environment['KB_FAKE_DI_PORT']}"
        if service == "document_intelligence"
        else f"http://127.0.0.1:{fake_service_environment['KB_FAKE_OPENAI_PORT']}"
    )
    _set_next_response(base_url, next_response)

    if request_kind == "document":
        status, body = _post_document(base_url, b"not a valid PDF")
    else:
        status, body = _post_json(
            f"{base_url}/v1/embeddings",
            {"input": "A report chunk", "model": "kb-embedding"},
        )

    assert status == expected_status
    assert body["error"]["code"] == expected_code


def test_fake_services_can_timeout_the_next_request(
    fake_service_environment: dict[str, str],
) -> None:
    """The OpenAI fake can make a caller exercise its timeout handling."""
    openai_url = f"http://127.0.0.1:{fake_service_environment['KB_FAKE_OPENAI_PORT']}"
    _set_next_response(openai_url, "timeout")

    with pytest.raises((TimeoutError, socket.timeout)):
        _post_json(
            f"{openai_url}/v1/embeddings",
            {"input": "A report chunk", "model": "kb-embedding"},
            timeout=0.05,
        )
