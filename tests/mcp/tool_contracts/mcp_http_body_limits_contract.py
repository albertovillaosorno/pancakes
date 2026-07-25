# ruff: noqa: S105
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Tests for MCP HTTP request body limits.

Boundary contract:
- Owns: body-size and media-type guard contracts.
- Must not: start tunnels, public services, or external mutation.
- Allows: ephemeral localhost servers and raw sockets.
- Split when: transport parsing needs reusable HTTP helpers.
- Merge when: mcp_http_contract owns this guard surface.
"""

from __future__ import annotations

import json
import socket
import threading
from contextlib import AbstractContextManager
from http import HTTPStatus
from typing import TYPE_CHECKING, NamedTuple, Self, cast
from urllib.parse import urlencode, urlparse

from mcp import RemoteMcpHttpOptions, build_remote_mcp_http_server, http_server

if TYPE_CHECKING:
    from pathlib import Path

    from mcp.http_server import RemoteMcpHttpServer

    from tests.support.json_payloads import JsonObject

REGISTER_BODY = (
    b'{"redirect_uris":["https://chat.openai.com/aip/plugin/callback"]}'
)
HTTP_STATUS_CODE_PART_COUNT = 2
DEFAULT_OPERATOR_PASSWORD = "test-operator-login"


class _HttpResponse(NamedTuple):
    body: str

    def json_object(self) -> JsonObject:
        payload = cast("object", json.loads(self.body))
        assert isinstance(payload, dict), (
            f"Expected JSON object response: {self.body}"
        )
        return cast("JsonObject", payload)


class _RawPostOptions(NamedTuple):
    content_type: str | None
    content_length: str | None = None
    include_content_length: bool = True
    expected_status: HTTPStatus = HTTPStatus.OK


class _RunningRemoteServer(AbstractContextManager["_RunningRemoteServer"]):
    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root
        self._server: RemoteMcpHttpServer | None = None
        self._thread: threading.Thread | None = None
        self.base_url = ""

    def __enter__(self) -> Self:
        server = build_remote_mcp_http_server(
            RemoteMcpHttpOptions(
                repo_root=self._repo_root,
                port=0,
                public_base_url=http_server.DEFAULT_PUBLIC_BASE_URL,
                operator_password=DEFAULT_OPERATOR_PASSWORD,
            )
        )
        host, port = cast("tuple[str, int]", server.server_address)
        self.base_url = f"http://{host}:{port}"
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._server = server
        self._thread = thread
        return self

    def __exit__(
        self, exc_type: object, exc: object, traceback: object
    ) -> bool | None:
        del exc_type, exc, traceback
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        return None


def test_remote_mcp_http_accepts_bounded_json_and_form_content_types(
    tmp_path: Path,
) -> None:
    """JSON and form endpoints accept the exact media types plus charset.

    parameters.
    """
    with _RunningRemoteServer(tmp_path) as server:
        registration = _post_raw(
            server,
            "/register",
            REGISTER_BODY,
            options=_RawPostOptions(
                content_type="application/json; charset=utf-8",
                expected_status=HTTPStatus.CREATED,
            ),
        ).json_object()
        token_error = _post_raw(
            server,
            "/token",
            urlencode({"grant_type": "client_credentials"}).encode("utf-8"),
            options=_RawPostOptions(
                content_type="application/x-www-form-urlencoded; charset=utf-8",
                expected_status=HTTPStatus.BAD_REQUEST,
            ),
        ).json_object()

    assert registration.get("client_id"), (
        f"Registration with JSON content type failed: {registration}"
    )
    assert token_error.get("error") == "Unsupported grant type.", (
        f"Form content type should reach token validation: {token_error}"
    )


def test_remote_mcp_http_rejects_missing_and_wrong_json_content_type(
    tmp_path: Path,
) -> None:
    """JSON endpoints require application/json instead of sniffing request.

    bodies.
    """
    with _RunningRemoteServer(tmp_path) as server:
        missing_type = _post_raw(
            server,
            "/register",
            REGISTER_BODY,
            options=_RawPostOptions(
                content_type=None,
                expected_status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            ),
        ).json_object()
        wrong_type = _post_raw(
            server,
            "/register",
            REGISTER_BODY,
            options=_RawPostOptions(
                content_type="text/plain",
                expected_status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            ),
        ).json_object()

    assert missing_type.get("error") == "Invalid OAuth registration request.", (
        f"Missing JSON content type must be bounded: {missing_type}"
    )
    assert wrong_type.get("error") == "Invalid OAuth registration request.", (
        f"Wrong JSON content type must be bounded: {wrong_type}"
    )


def test_remote_mcp_http_rejects_wrong_form_content_type(
    tmp_path: Path,
) -> None:
    """OAuth form endpoints require URL-encoded form media type."""
    with _RunningRemoteServer(tmp_path) as server:
        wrong_type = _post_raw(
            server,
            "/token",
            urlencode({"grant_type": "authorization_code"}).encode("utf-8"),
            options=_RawPostOptions(
                content_type="application/json",
                expected_status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            ),
        ).json_object()

    assert wrong_type.get("error") == "Invalid OAuth token request.", (
        f"Wrong form content type must be bounded: {wrong_type}"
    )


def test_remote_mcp_http_requires_content_length_for_json_bodies(
    tmp_path: Path,
) -> None:
    """HTTP body readers reject missing Content-Length before parsing JSON."""
    with _RunningRemoteServer(tmp_path) as server:
        missing_length = _post_raw(
            server,
            "/register",
            REGISTER_BODY,
            options=_RawPostOptions(
                content_type="application/json",
                include_content_length=False,
                expected_status=HTTPStatus.LENGTH_REQUIRED,
            ),
        ).json_object()

    assert (
        missing_length.get("error") == "Invalid OAuth registration request."
    ), f"Missing Content-Length must be bounded: {missing_length}"


def test_remote_mcp_http_rejects_invalid_and_negative_content_lengths(
    tmp_path: Path,
) -> None:
    """Malformed Content-Length values stay bounded as bad requests."""
    with _RunningRemoteServer(tmp_path) as server:
        invalid_length = _post_raw(
            server,
            "/register",
            REGISTER_BODY,
            options=_RawPostOptions(
                content_type="application/json",
                content_length="not-a-number",
                expected_status=HTTPStatus.BAD_REQUEST,
            ),
        ).json_object()
        negative_length = _post_raw(
            server,
            "/token",
            urlencode({"grant_type": "authorization_code"}).encode("utf-8"),
            options=_RawPostOptions(
                content_type="application/x-www-form-urlencoded",
                content_length="-1",
                expected_status=HTTPStatus.BAD_REQUEST,
            ),
        ).json_object()

    assert (
        invalid_length.get("error") == "Invalid OAuth registration request."
    ), f"Invalid Content-Length must be bounded: {invalid_length}"
    assert negative_length.get("error") == "Invalid OAuth token request.", (
        f"Negative Content-Length must be bounded: {negative_length}"
    )


def test_remote_mcp_http_rejects_oversized_json_and_form_bodies(
    tmp_path: Path,
) -> None:
    """Declared body sizes over the transport caps fail before body parsing."""
    with _RunningRemoteServer(tmp_path) as server:
        json_too_large = _post_raw(
            server,
            "/mcp",
            b"",
            options=_RawPostOptions(
                content_type="application/json",
                content_length=str(http_server.MAX_MCP_JSON_BODY_BYTES + 1),
                expected_status=HTTPStatus.CONTENT_TOO_LARGE,
            ),
        ).json_object()
        form_too_large = _post_raw(
            server,
            "/token",
            b"",
            options=_RawPostOptions(
                content_type="application/x-www-form-urlencoded",
                content_length=str(http_server.MAX_MCP_FORM_BODY_BYTES + 1),
                expected_status=HTTPStatus.CONTENT_TOO_LARGE,
            ),
        ).json_object()

    assert json_too_large.get("error") == "Invalid JSON-RPC request.", (
        f"Oversized JSON-RPC bodies must be bounded: {json_too_large}"
    )
    assert form_too_large.get("error") == "Invalid OAuth token request.", (
        f"Oversized form bodies must be bounded: {form_too_large}"
    )


def _post_raw(
    server: _RunningRemoteServer,
    path: str,
    body: bytes,
    *,
    options: _RawPostOptions,
) -> _HttpResponse:
    parsed = urlparse(server.base_url)
    assert parsed.hostname is not None, (
        f"Unexpected test server URL: {server.base_url}"
    )
    assert parsed.port is not None, (
        f"Unexpected test server URL: {server.base_url}"
    )
    headers = [
        f"POST {path} HTTP/1.1 ",
        f"Host: {parsed.hostname}:{parsed.port}",
        "Connection: close",
    ]
    if options.content_type is not None:
        headers.append(f"Content-Type: {options.content_type}")
    if options.include_content_length:
        declared_length = options.content_length or str(len(body))
        headers.append(f"Content-Length: {declared_length}")
    raw_request = ("\r\n".join(headers) + "\r\n\r\n").encode("ascii") + body
    with socket.create_connection(
        (parsed.hostname, parsed.port), timeout=5
    ) as client:
        client.sendall(raw_request)
        client.shutdown(socket.SHUT_WR)
        raw_response = _read_socket_response(client)
    return _parse_raw_http_response(
        raw_response,
        request_url=f"{server.base_url}{path}",
        expected_status=options.expected_status,
    )


def _read_socket_response(client: socket.socket) -> bytes:
    chunks: list[bytes] = []
    while True:
        chunk = client.recv(65_536)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _parse_raw_http_response(
    raw_response: bytes,
    *,
    request_url: str,
    expected_status: HTTPStatus,
) -> _HttpResponse:
    header_bytes, separator, body_bytes = raw_response.partition(b"\r\n\r\n")
    assert separator, (
        f"Missing HTTP response body separator for {request_url}: "
        f"{raw_response!r}"
    )
    header_lines = header_bytes.decode("iso-8859-1").split("\r\n")
    status_parts = header_lines[0].split(" ", 2)
    assert not (len(status_parts) < HTTP_STATUS_CODE_PART_COUNT), (
        f"Malformed HTTP status line for {request_url}: {header_lines[0]}"
    )
    assert status_parts[1].isdigit(), (
        f"Malformed HTTP status line for {request_url}: {header_lines[0]}"
    )
    status = int(status_parts[1])
    body = body_bytes.decode("utf-8")
    assert status == expected_status, (
        f"Unexpected HTTP status {status} for {request_url}: {body}"
    )
    return _HttpResponse(body=body)
