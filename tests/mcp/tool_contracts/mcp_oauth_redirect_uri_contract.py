# ruff: noqa: S105, S310
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Tests for MCP OAuth redirect URI validation.

Boundary contract:
- Owns: dynamic OAuth client redirect URI safety and exact-match contracts.
- Must not: start tunnels, call public domains, or mutate external OAuth
providers.
- Allows: ephemeral localhost MCP servers and synthetic redirect URI strings.
- Split when: registration, authorization, and persistence checks need separate
slices.
- Merge when: mcp_http_contract owns all remote OAuth redirect invariants
directly.
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
from contextlib import AbstractContextManager
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple, Self, cast, override
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import (
    HTTPRedirectHandler,
    OpenerDirector,
    Request,
    build_opener,
)

import pytest
from mcp import (
    RemoteMcpHttpOptions,
    build_remote_mcp_http_server,
    http_server,
    reset_remote_mcp_oauth_state,
    revoke_remote_mcp_bearer_token,
)
from mcp.http_server import (
    AUTH_AUDIT_MAX_EVENTS,
    REMOTE_MCP_OPERATOR_PASSWORD_ENV,
)

if TYPE_CHECKING:
    from http.client import HTTPResponse as ClientHTTPResponse

    from mcp.http_server import RemoteMcpHttpServer

    from tests.support.json_payloads import JsonObject

SAFE_REDIRECT_URIS = (
    "https://chat.openai.com/aip/plugin/callback",
    "https://chat.openai.com/backend-api/aip/plugin/callback",
    "https://chatgpt.com/aip/plugin/callback",
    "http://127.0.0.1:39117/oauth/callback",
    "http://localhost/oauth/callback",
    "http://[::1]:39117/oauth/callback",
    "make-mcp://oauth/callback",
)
DEFAULT_OPERATOR_PASSWORD = "test-operator-login"
DEFAULT_PKCE_CODE_VERIFIER = "make-mcp-test-pkce-verifier-redirect-uri"
DEFAULT_REMOTE_MCP_TEST_PORT = 0
UNSAFE_REDIRECT_URIS = (
    "",
    "/oauth/callback",
    "https://*.example.com/oauth/callback",
    "javascript:alert(1)",
    "file:///tmp/oauth/callback",
    "https://user:pass@example.com/oauth/callback",
    "http://example.com/oauth/callback",
    "https://attacker.example/oauth/callback",
    "https://chat.openai.com.evil.example/aip/plugin/callback",
    "https://chatgpt.com.evil.example/aip/plugin/callback",
    "https://chatgpt.com/",
    "https://chat.openai.com/aip/plugin/callback\nX-Injected: yes",
    "https://chat.openai.com/aip/plugin/callback\r\nX-Injected: yes",
)
PROTECTED_DESCRIPTOR_METHODS = (
    ("resources/list", "resources"),
    ("prompts/list", "prompts"),
)
PUBLIC_HEALTH_METADATA_FIELDS = {
    "host",
    "port",
    "public_base_url",
    "server_name",
    "transport",
}


class _NoRedirectHandler(HTTPRedirectHandler):
    @override
    def redirect_request(
        self,
        req: Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> Request | None:
        del req, fp, code, msg, headers, newurl
        return None


NO_REDIRECT_OPENER: OpenerDirector = build_opener(_NoRedirectHandler)


class _HttpResponse(NamedTuple):
    status: int
    headers: dict[str, str]
    body: str

    def json_object(self) -> JsonObject:
        payload = cast("object", json.loads(self.body))
        assert isinstance(payload, dict), (
            f"Expected JSON object response: {self.body}"
        )
        return cast("JsonObject", payload)


class _RunningRemoteServer(AbstractContextManager["_RunningRemoteServer"]):
    def __init__(
        self, repo_root: Path, *, use_operator_oauth_store: bool = False
    ) -> None:
        self._repo_root = repo_root
        self._use_operator_oauth_store = use_operator_oauth_store
        self._server: RemoteMcpHttpServer | None = None
        self._thread: threading.Thread | None = None
        self.base_url = ""

    def __enter__(self) -> Self:
        server = build_remote_mcp_http_server(self._options())
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

    @property
    def remote_server(self) -> RemoteMcpHttpServer:
        assert self._server is not None
        return self._server

    def oauth_options(self) -> RemoteMcpHttpOptions:
        """Return matching OAuth options for direct store operations."""
        return self._options(port=DEFAULT_REMOTE_MCP_TEST_PORT)

    def token_store_path(self) -> Path:
        """Return the isolated token store path used by this test server."""
        return (
            self._repo_root / "src" / "mcp" / "data" / "oauth" / "tokens.json"
        )

    def _options(self, *, port: int = 0) -> RemoteMcpHttpOptions:
        if self._use_operator_oauth_store:
            return RemoteMcpHttpOptions(
                repo_root=self._repo_root,
                port=port,
                public_base_url=http_server.DEFAULT_PUBLIC_BASE_URL,
                operator_password=DEFAULT_OPERATOR_PASSWORD,
            )
        return RemoteMcpHttpOptions(
            repo_root=self._repo_root,
            port=port,
            public_base_url=http_server.DEFAULT_PUBLIC_BASE_URL,
            operator_password=DEFAULT_OPERATOR_PASSWORD,
            oauth_client_store_path=Path("src/mcp/data/oauth/clients.json"),
            oauth_token_store_path=Path("src/mcp/data/oauth/tokens.json"),
        )


def _no_operator_password_dotenv_paths(_repo_root: Path) -> tuple[Path, ...]:
    """Return the computed result for the caller."""
    return ()


def test_remote_mcp_requires_operator_password_at_startup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Remote MCP fails closed when no operator password is configured."""
    monkeypatch.delenv(REMOTE_MCP_OPERATOR_PASSWORD_ENV, raising=False)
    monkeypatch.setattr(
        http_server,
        "_operator_password_dotenv_paths",
        _no_operator_password_dotenv_paths,
    )
    with pytest.raises(ValueError, match="operator password is required"):
        _ = build_remote_mcp_http_server(
            RemoteMcpHttpOptions(
                repo_root=tmp_path,
                port=0,
                public_base_url=http_server.DEFAULT_PUBLIC_BASE_URL,
            )
        )


def test_remote_mcp_oauth_registers_safe_redirect_uris(tmp_path: Path) -> None:
    """Dynamic client registration accepts safe redirect URI shapes."""
    with _RunningRemoteServer(tmp_path) as server:
        registrations = tuple(
            _register_oauth_client(server, redirect_uri)
            for redirect_uri in SAFE_REDIRECT_URIS
        )

    returned_uris = tuple(
        registration["redirect_uris"] for registration in registrations
    )
    assert returned_uris == tuple(
        [redirect_uri] for redirect_uri in SAFE_REDIRECT_URIS
    ), f"Safe redirect URI registration drifted: {registrations}"


def test_remote_mcp_oauth_uses_schoenwald_root_state_store(
    tmp_path: Path,
) -> None:
    """Schoenwald-hosted MCP OAuth state is stable root state, not child repo.

    output.
    """
    operator_root = tmp_path / "schoenwald"
    repo_root = operator_root / "repos" / "proprietary" / "pancakes"
    (operator_root / "commands").mkdir(parents=True)
    repo_root.mkdir(parents=True)
    _ = (operator_root / "AGENTS.md").write_text(
        "# Test operator root\n", encoding="utf-8"
    )

    with _RunningRemoteServer(
        repo_root, use_operator_oauth_store=True
    ) as server:
        registration = _register_oauth_client(
            server, "http://localhost/oauth/callback"
        )
        _ = _issue_oauth_token(
            server,
            redirect_uri="http://localhost/oauth/callback",
            client_id=cast("str", registration["client_id"]),
        )

    root_oauth_dir = operator_root / "data" / "pancakes-mcp" / "oauth"
    repo_oauth_dir = repo_root / "src" / "mcp" / "data" / "oauth"
    assert (root_oauth_dir / "clients.json").is_file()
    assert (root_oauth_dir / "tokens.json").is_file()
    assert not (repo_oauth_dir / "clients.json").exists()
    assert not (repo_oauth_dir / "tokens.json").exists()


def test_remote_mcp_oauth_token_survives_server_restart(tmp_path: Path) -> None:
    """Persisted local bearer tokens remain valid across MCP process.

    restarts.
    """
    redirect_uri = "https://chatgpt.com/aip/plugin/callback"
    with _RunningRemoteServer(tmp_path) as server:
        token_payload = _issue_oauth_token(server, redirect_uri=redirect_uri)
        access_token = cast("str", token_payload["access_token"])
        before_restart = _post_json(
            server,
            "/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": "prompts/list", "params": {}},
            expected_status=HTTPStatus.OK,
            headers={"Authorization": f"Bearer {access_token}"},
        ).json_object()

    token_store_path = (
        tmp_path / "src" / "mcp" / "data" / "oauth" / "tokens.json"
    )
    persisted_payload = cast(
        "JsonObject",
        json.loads(token_store_path.read_text(encoding="utf-8")),
    )
    persisted_tokens = cast("list[JsonObject]", persisted_payload["tokens"])
    with _RunningRemoteServer(tmp_path) as restarted_server:
        after_restart = _post_json(
            restarted_server,
            "/mcp",
            {"jsonrpc": "2.0", "id": 2, "method": "prompts/list", "params": {}},
            expected_status=HTTPStatus.OK,
            headers={"Authorization": f"Bearer {access_token}"},
        ).json_object()

    assert "prompts" in cast("JsonObject", before_restart["result"])
    assert "prompts" in cast("JsonObject", after_restart["result"])
    assert len(persisted_tokens) == 1
    assert persisted_tokens[0]["access_token"] == access_token
    assert persisted_tokens[0]["access_token_sha256"] != access_token


def test_remote_mcp_oauth_restart_and_new_token_do_not_prune_expired_store(
    tmp_path: Path,
) -> None:
    """Ordinary restart and reauth preserve existing token rows unless.

    explicitly revoked.
    """
    redirect_uri = "https://chatgpt.com/aip/plugin/callback"
    with _RunningRemoteServer(tmp_path) as server:
        token_payload = _issue_oauth_token(server, redirect_uri=redirect_uri)
        expired_access_token = cast("str", token_payload["access_token"])

    token_store_path = (
        tmp_path / "src" / "mcp" / "data" / "oauth" / "tokens.json"
    )
    token_store_payload = cast(
        "JsonObject",
        json.loads(token_store_path.read_text(encoding="utf-8")),
    )
    persisted_tokens = cast("list[JsonObject]", token_store_payload["tokens"])
    persisted_tokens[0]["issued_at"] = 1
    persisted_tokens[0]["expires_at"] = 2
    _ = token_store_path.write_text(
        json.dumps(
            token_store_payload, ensure_ascii=True, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )

    with _RunningRemoteServer(tmp_path) as restarted_server:
        expired_response = _post_json(
            restarted_server,
            "/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": "prompts/list", "params": {}},
            expected_status=HTTPStatus.UNAUTHORIZED,
            headers={"Authorization": f"Bearer {expired_access_token}"},
        ).json_object()
        new_token_payload = _issue_oauth_token(
            restarted_server, redirect_uri=redirect_uri
        )

    after_reauth_payload = cast(
        "JsonObject",
        json.loads(token_store_path.read_text(encoding="utf-8")),
    )
    after_reauth_tokens = cast(
        "list[JsonObject]", after_reauth_payload["tokens"]
    )
    after_reauth_access_tokens = {
        cast("str", token["access_token"])
        for token in after_reauth_tokens
        if isinstance(token.get("access_token"), str)
    }

    _assert_http_bearer_required(expired_response)
    assert expired_access_token in after_reauth_access_tokens
    assert (
        cast("str", new_token_payload["access_token"])
        in after_reauth_access_tokens
    )


def test_remote_mcp_tools_list_is_public_for_action_refresh(
    tmp_path: Path,
) -> None:
    """Tool descriptors stay public so ChatGPT can refresh actions before.

    reauth.
    """
    with _RunningRemoteServer(tmp_path) as server:
        response = _post_json(
            server,
            "/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            expected_status=HTTPStatus.OK,
            headers={"Authorization": "Bearer stale-or-wrong-test-token"},
        ).json_object()

    result_value = response.get("result")
    assert isinstance(result_value, dict), (
        f"Expected tools/list result: {response}"
    )
    result = cast("JsonObject", result_value)
    assert "tools" in result, (
        f"Public tools/list did not return tool descriptors: {response}"
    )
    assert response.get("error_code") != "oauth_bearer_token_required", (
        f"Action refresh still triggers reauthentication: {response}"
    )


def test_remote_mcp_project_create_descriptor_avoids_raw_blueprint_arguments(
    tmp_path: Path,
) -> None:
    """ChatGPT should not be invited to send raw blueprint JSON or secret-like.

    values.
    """
    with _RunningRemoteServer(tmp_path) as server:
        response = _post_json(
            server,
            "/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            expected_status=HTTPStatus.OK,
        ).json_object()

    result = cast("JsonObject", response["result"])
    tools = cast("list[JsonObject]", result["tools"])
    create_tool = next(
        tool for tool in tools if tool["name"] == "project.create"
    )
    import_tool = next(
        tool for tool in tools if tool["name"] == "project.draft.import"
    )
    input_schema = cast("JsonObject", create_tool["inputSchema"])
    properties = cast("JsonObject", input_schema["properties"])
    prompt_surface = {
        "description": create_tool["description"],
        "inputSchema": input_schema,
        "importDescription": import_tool["description"],
        "importInputSchema": import_tool["inputSchema"],
    }
    serialized_prompt_surface = json.dumps(prompt_surface, sort_keys=True)

    assert "blueprint_json" not in properties
    assert "make_blueprint_json" not in properties
    assert "intent" not in properties
    assert "customer_intent" not in properties
    assert "staged_draft_path" in properties
    assert "staged_draft_sha256" in properties
    assert "blueprint_artifact_path" not in properties
    assert "make_blueprint_artifact_path" not in properties
    assert "sensitive" not in serialized_prompt_surface.casefold()
    assert "credential" not in serialized_prompt_surface.casefold()
    assert "token" not in serialized_prompt_surface.casefold()
    assert "sk_test" not in serialized_prompt_surface
    assert "Bearer " not in serialized_prompt_surface
    assert "https://" not in serialized_prompt_surface


@pytest.mark.parametrize(
    ("method", "blocked_key"), PROTECTED_DESCRIPTOR_METHODS
)
def test_remote_mcp_protected_descriptor_methods_require_bearer_token(
    tmp_path: Path,
    method: str,
    blocked_key: str,
) -> None:
    """Non-tool MCP descriptors are not anonymously enumerable."""
    with _RunningRemoteServer(tmp_path) as server:
        response = _post_json(
            server,
            "/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": {}},
            expected_status=HTTPStatus.UNAUTHORIZED,
        ).json_object()

    _assert_http_bearer_required(response)
    assert blocked_key not in response, (
        f"Descriptor leaked without auth: {method} -> {response}"
    )


def test_remote_mcp_rejects_wrong_bearer_token_before_tool_calls(
    tmp_path: Path,
) -> None:
    """Wrong bearer credentials cannot call MCP tools."""
    with _RunningRemoteServer(tmp_path) as server:
        response = _post_json(
            server,
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "catalog.search",
                    "arguments": {"query": "auth"},
                },
            },
            expected_status=HTTPStatus.UNAUTHORIZED,
            headers={"Authorization": "Bearer wrong-test-token"},
        ).json_object()

    _assert_http_bearer_required(response)
    assert "tools" not in response


def test_remote_mcp_catalog_work_tools_require_authorized_bearer(
    tmp_path: Path,
) -> None:
    """Catalog work tool names cannot bypass password-gated MCP.

    authorization.
    """
    with _RunningRemoteServer(tmp_path) as server:
        response = _post_json(
            server,
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "catalog.work.next",
                    "arguments": {"worker_id": "ChatGPT.com"},
                },
            },
            expected_status=HTTPStatus.UNAUTHORIZED,
        ).json_object()

    _assert_http_bearer_required(response)
    assert "lease_token" not in response
    assert "units" not in response


def test_remote_mcp_initialize_remains_public_handshake(tmp_path: Path) -> None:
    """MCP initialize remains anonymous so OAuth-capable clients can start.

    linking.
    """
    with _RunningRemoteServer(tmp_path) as server:
        response = _post_json(
            server,
            "/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            expected_status=HTTPStatus.OK,
        ).json_object()

    result_value = response.get("result")
    assert isinstance(result_value, dict), (
        f"Expected initialize result: {response}"
    )
    result = cast("JsonObject", result_value)
    assert result.get("protocolVersion") == "2025-06-18", (
        f"Anonymous initialize response changed: {response}"
    )
    assert isinstance(result.get("serverInfo"), dict), (
        f"Missing serverInfo: {response}"
    )


def test_remote_mcp_hostname_root_json_rpc_alias_supports_action_refresh(
    tmp_path: Path,
) -> None:
    """The public hostname root compatibility alias can refresh tool.

    descriptors.
    """
    with _RunningRemoteServer(tmp_path) as server:
        response = _post_json(
            server,
            "/",
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            expected_status=HTTPStatus.OK,
        ).json_object()

    result_value = response.get("result")
    assert isinstance(result_value, dict), (
        f"Expected root tools/list result: {response}"
    )
    assert "tools" in result_value, (
        f"Root JSON-RPC alias failed action refresh: {response}"
    )


def test_remote_mcp_public_health_does_not_expose_origin_metadata(
    tmp_path: Path,
) -> None:
    """Public health routes expose only liveness, not loopback origin.

    details.
    """
    with _RunningRemoteServer(tmp_path) as server:
        root_response = _get_json(
            server, "/", expected_status=HTTPStatus.OK
        ).json_object()
        health_response = _get_json(
            server, "/health", expected_status=HTTPStatus.OK
        ).json_object()

    assert root_response == {"status": "ok"}, (
        f"Root health leaked metadata: {root_response}"
    )
    assert health_response == {"status": "ok"}, (
        f"Health leaked metadata: {health_response}"
    )
    leaked_root_fields = PUBLIC_HEALTH_METADATA_FIELDS.intersection(
        root_response
    )
    leaked_health_fields = PUBLIC_HEALTH_METADATA_FIELDS.intersection(
        health_response
    )
    assert not leaked_root_fields, (
        f"Root health leaked fields: {sorted(leaked_root_fields)}"
    )
    assert not leaked_health_fields, (
        f"Health leaked fields: {sorted(leaked_health_fields)}"
    )


@pytest.mark.parametrize("redirect_uri", UNSAFE_REDIRECT_URIS)
def test_remote_mcp_oauth_rejects_unsafe_redirect_uris(
    tmp_path: Path,
    redirect_uri: str,
) -> None:
    """Dynamic client registration rejects unsafe redirect URI shapes."""
    with _RunningRemoteServer(tmp_path) as server:
        response = _post_json(
            server,
            "/register",
            {"redirect_uris": [redirect_uri]},
            expected_status=HTTPStatus.BAD_REQUEST,
        ).json_object()

    assert response.get("error") == "Invalid OAuth redirect URI.", (
        f"Unsafe redirect URI was not rejected: {redirect_uri!r} -> {response}"
    )


def test_remote_mcp_oauth_rejects_non_string_redirect_uri_entries(
    tmp_path: Path,
) -> None:
    """Dynamic client registration rejects mixed-shape redirect URI arrays."""
    with _RunningRemoteServer(tmp_path) as server:
        response = _post_json(
            server,
            "/register",
            {
                "redirect_uris": [
                    "https://chat.openai.com/aip/plugin/callback",
                    123,
                ]
            },
            expected_status=HTTPStatus.BAD_REQUEST,
        ).json_object()

    assert response.get("error") == "Invalid OAuth redirect URI.", (
        f"Non-string redirect URI entry was accepted: {response}"
    )


def test_remote_mcp_oauth_requires_exact_registered_redirect_uri(
    tmp_path: Path,
) -> None:
    """Authorization rejects close-but-not-exact redirect URI matches."""
    registered_redirect_uri = "http://localhost/oauth/callback"
    mismatched_redirect_uri = "http://127.0.0.1/oauth/callback"
    with _RunningRemoteServer(tmp_path) as server:
        registration = _register_oauth_client(server, registered_redirect_uri)
        response = _post_form(
            server,
            "/authorize",
            {
                "client_id": cast("str", registration["client_id"]),
                "redirect_uri": mismatched_redirect_uri,
                "state": "state-1",
                "code_challenge": _pkce_s256_challenge(
                    DEFAULT_PKCE_CODE_VERIFIER
                ),
                "code_challenge_method": "S256",
                "operator_password": DEFAULT_OPERATOR_PASSWORD,
            },
            expected_status=HTTPStatus.BAD_REQUEST,
        ).json_object()

    assert (
        response.get("error")
        == "Redirect URI is not registered for this OAuth client."
    ), f"Authorization accepted an inexact redirect URI: {response}"


def test_remote_mcp_oauth_ignores_persisted_unsafe_redirect_uri(
    tmp_path: Path,
) -> None:
    """Persisted dynamic clients with unsafe redirect URIs are not restored."""
    client_store_path = (
        tmp_path / "src" / "mcp" / "data" / "oauth" / "clients.json"
    )
    client_store_path.parent.mkdir(parents=True)
    _ = client_store_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "clients": [
                    {
                        "client_id": "unsafe-client",
                        "redirect_uris": ["javascript:alert(1)"],
                        "issued_at": 1_800_000_000,
                    }
                ],
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    with _RunningRemoteServer(tmp_path) as server:
        response = _post_form(
            server,
            "/authorize",
            {
                "client_id": "unsafe-client",
                "redirect_uri": "https://chat.openai.com/aip/plugin/callback",
                "state": "state-1",
                "code_challenge": _pkce_s256_challenge(
                    DEFAULT_PKCE_CODE_VERIFIER
                ),
                "code_challenge_method": "S256",
                "operator_password": DEFAULT_OPERATOR_PASSWORD,
            },
            expected_status=HTTPStatus.BAD_REQUEST,
        ).json_object()

    assert response.get("error") == "Unknown OAuth client.", (
        f"Persisted unsafe redirect URI was restored: {response}"
    )


def test_remote_mcp_rejects_wrong_operator_password_and_records_redacted_audit(
    tmp_path: Path,
) -> None:
    """Wrong operator passwords fail closed and leave bounded redacted audit.

    evidence.
    """
    with _RunningRemoteServer(tmp_path) as server:
        registration = _register_oauth_client(
            server, "http://localhost/oauth/callback"
        )
        client_id = cast("str", registration["client_id"])
        response = _post_form(
            server,
            "/authorize",
            {
                "client_id": client_id,
                "redirect_uri": "http://localhost/oauth/callback",
                "state": "state-1",
                "code_challenge": _pkce_s256_challenge(
                    DEFAULT_PKCE_CODE_VERIFIER
                ),
                "code_challenge_method": "S256",
                "operator_password": "wrong-operator-login",
            },
            expected_status=HTTPStatus.UNAUTHORIZED,
        ).json_object()
        events = server.remote_server.auth_audit_events()

    audit_payload = json.dumps(
        [event._asdict() for event in events], sort_keys=True
    )
    assert response.get("error_code") == "oauth_operator_password_invalid"
    assert len(events) <= AUTH_AUDIT_MAX_EVENTS
    assert events[-1].event_type == "oauth_authorize"
    assert events[-1].status == "invalid_password"
    assert events[-1].client_id_sha256 != client_id
    assert DEFAULT_OPERATOR_PASSWORD not in audit_payload
    assert "wrong-operator-login" not in audit_payload


def test_remote_mcp_revoked_bearer_token_cannot_reach_tools(
    tmp_path: Path,
) -> None:
    """Local token revocation removes persisted access before the next server.

    start.
    """
    redirect_uri = "http://localhost/oauth/callback"
    with _RunningRemoteServer(tmp_path) as server:
        token_payload = _issue_oauth_token(server, redirect_uri=redirect_uri)
        access_token = cast("str", token_payload["access_token"])
        allowed = _post_json(
            server,
            "/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            expected_status=HTTPStatus.OK,
            headers={"Authorization": f"Bearer {access_token}"},
        ).json_object()

    reset_payload = revoke_remote_mcp_bearer_token(
        server.oauth_options(), access_token
    )
    with _RunningRemoteServer(tmp_path) as server:
        blocked = _post_json(
            server,
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "catalog.search",
                    "arguments": {"query": "auth"},
                },
            },
            expected_status=HTTPStatus.UNAUTHORIZED,
            headers={"Authorization": f"Bearer {access_token}"},
        ).json_object()

    assert "tools" in cast("JsonObject", allowed["result"])
    assert reset_payload == {
        "status": "revoked",
        "revoked": True,
        "secrets_printed": False,
    }
    _assert_http_bearer_required(blocked)


def test_remote_mcp_oauth_reset_clears_clients_and_tokens_without_secret_output(
    tmp_path: Path,
) -> None:
    """Local OAuth reset clears persisted auth state without returning.

    secrets.
    """
    with _RunningRemoteServer(tmp_path) as server:
        registration = _register_oauth_client(
            server, "http://localhost/oauth/callback"
        )
        token_payload = _issue_oauth_token(
            server,
            redirect_uri="http://localhost/oauth/callback",
            client_id=cast("str", registration["client_id"]),
        )

    reset_payload = reset_remote_mcp_oauth_state(server.oauth_options())
    with _RunningRemoteServer(tmp_path) as server:
        response = _post_form(
            server,
            "/authorize",
            {
                "client_id": cast("str", registration["client_id"]),
                "redirect_uri": "http://localhost/oauth/callback",
                "state": "state-1",
                "code_challenge": _pkce_s256_challenge(
                    DEFAULT_PKCE_CODE_VERIFIER
                ),
                "code_challenge_method": "S256",
                "operator_password": DEFAULT_OPERATOR_PASSWORD,
            },
            expected_status=HTTPStatus.BAD_REQUEST,
        ).json_object()

    serialized_reset = json.dumps(reset_payload, sort_keys=True)
    assert cast("str", token_payload["access_token"]) not in serialized_reset
    assert reset_payload == {
        "status": "reset",
        "clients_cleared": True,
        "tokens_cleared": True,
        "secrets_printed": False,
    }
    assert response.get("error") == "Unknown OAuth client."


def _register_oauth_client(
    server: _RunningRemoteServer, redirect_uri: str
) -> JsonObject:
    return _post_json(
        server,
        "/register",
        {"redirect_uris": [redirect_uri]},
        expected_status=HTTPStatus.CREATED,
    ).json_object()


def _assert_http_bearer_required(response: JsonObject) -> None:
    assert (
        response.get("error") == "Bearer token is required for MCP requests."
    ), f"Expected HTTP bearer-token error: {response}"
    assert response.get("error_code") == "oauth_bearer_token_required", (
        f"Expected stable bearer-token error code: {response}"
    )
    assert "result" not in response, (
        f"Protected MCP method returned JSON-RPC result: {response}"
    )


def _issue_oauth_token(
    server: _RunningRemoteServer,
    *,
    redirect_uri: str,
    client_id: str | None = None,
) -> JsonObject:
    actual_client_id = client_id
    if actual_client_id is None:
        registration = _register_oauth_client(server, redirect_uri)
        actual_client_id = cast("str", registration["client_id"])
    authorization = _post_form(
        server,
        "/authorize",
        {
            "client_id": actual_client_id,
            "redirect_uri": redirect_uri,
            "state": "state-1",
            "code_challenge": _pkce_s256_challenge(DEFAULT_PKCE_CODE_VERIFIER),
            "code_challenge_method": "S256",
            "operator_password": DEFAULT_OPERATOR_PASSWORD,
        },
        expected_status=HTTPStatus.FOUND,
    )
    location = authorization.headers["location"]
    parsed_location = urlparse(location)
    code_values = parse_qs(parsed_location.query).get("code")
    assert code_values, (
        f"Authorization response did not include code: {authorization}"
    )
    return _post_form(
        server,
        "/token",
        {
            "grant_type": "authorization_code",
            "code": code_values[0],
            "client_id": actual_client_id,
            "redirect_uri": redirect_uri,
            "code_verifier": DEFAULT_PKCE_CODE_VERIFIER,
        },
        expected_status=HTTPStatus.OK,
    ).json_object()


def _pkce_s256_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _post_json(
    server: _RunningRemoteServer,
    path: str,
    payload: JsonObject,
    *,
    expected_status: HTTPStatus,
    headers: dict[str, str] | None = None,
) -> _HttpResponse:
    request_headers = {"Content-Type": "application/json"}
    if headers is not None:
        request_headers.update(headers)
    request = Request(
        f"{server.base_url}{path}",
        data=json.dumps(payload, ensure_ascii=True).encode("utf-8"),
        headers=request_headers,
        method="POST",
    )
    return _open_request(request, expected_status=expected_status)


def _get_json(
    server: _RunningRemoteServer,
    path: str,
    *,
    expected_status: HTTPStatus,
) -> _HttpResponse:
    request = Request(
        f"{server.base_url}{path}",
        method="GET",
    )
    return _open_request(request, expected_status=expected_status)


def _post_form(
    server: _RunningRemoteServer,
    path: str,
    payload: dict[str, str],
    *,
    expected_status: HTTPStatus,
) -> _HttpResponse:
    request = Request(
        f"{server.base_url}{path}",
        data=urlencode(payload).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    return _open_request(request, expected_status=expected_status)


def _open_request(
    request: Request, *, expected_status: HTTPStatus
) -> _HttpResponse:
    try:
        response_context = cast(
            "ClientHTTPResponse",
            NO_REDIRECT_OPENER.open(request, timeout=5),
        )
        with response_context as response:
            body = response.read().decode("utf-8")
            status = response.status
            headers = {
                key.lower(): value for key, value in response.headers.items()
            }
    except HTTPError as exc:
        try:
            body = exc.read().decode("utf-8")
            status = exc.code
            headers = {key.lower(): value for key, value in exc.headers.items()}
        finally:
            exc.close()
    assert status == expected_status, (
        f"Unexpected HTTP status {status} for {request.full_url}: {body}"
    )
    return _HttpResponse(status=status, headers=headers, body=body)
