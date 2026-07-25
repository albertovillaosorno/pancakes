# ruff: noqa: E501, S105
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001055#repo.mcp.remote-http-loopback-transport
# - 001055#repo.mcp.remote-oauth-discovery
# - 001055#repo.mcp.required-tool-surface
# - 001067#repo.mcp.client-routing.one-time-auth-session-posture
# - 001067#repo.mcp.client-routing.native-gpt-latency-and-output
# - 001055#repo.mcp.scenario-builder-micro-tools
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end
"""Loopback HTTP transport for the repository MCP surface.

Boundary contract:
- Owns: remote MCP HTTP/OAuth discovery over a loopback origin for Cloudflare
Tunnel.
- Must not: start credentialed tunnels, mutate live Make accounts, or add
destructive tools.
- Allows: public tool descriptor refresh, bearer-token-gated reads, and local
scenario workspace
  tools.
- Split when: OAuth persistence, UI login, or non-loopback hosting needs full
services.
- Merge when: another module owns the same HTTP transport and OAuth discovery
surface.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import secrets
import sqlite3
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from typing import TYPE_CHECKING, Final, NamedTuple, cast, override
from urllib.parse import ParseResult, parse_qs, urlencode, urlparse

from blueprints.validation.network_hosts import host_ip_candidates
from languages.make.raw_specs.paths import resolve_repo_relative_path

from mcp.context import (
    get_mcp_prompt,
    mcp_prompt_registry,
    mcp_resource_registry,
    read_mcp_resource,
)
from mcp.executor import execute_mcp_tool, warm_catalog_snapshot
from mcp.registry import mcp_tool_registry
from mcp.server import MCP_SERVER_NAME

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from mcp.models import (
        JsonObject,
        McpOauthScope,
        McpPromptDefinition,
        McpResourceDefinition,
        McpToolDefinition,
    )

DEFAULT_REMOTE_MCP_HOST = "127.0.0.1"
DEFAULT_REMOTE_MCP_PORT = 8787
# The public hostname identifies one operator's deployment, so it is read from
# the environment instead of being compiled in. Without it the server still
# serves on loopback; only the published base URL is unset.
PUBLIC_HOST_UUID_ENV: Final = "PANCAKES_MCP_PUBLIC_HOST_UUID"
PUBLIC_BASE_DOMAIN_ENV: Final = "PANCAKES_MCP_PUBLIC_BASE_DOMAIN"
PUBLIC_BASE_URL_ENV: Final = "PANCAKES_MCP_PUBLIC_URL"


def _default_public_base_url() -> str:
    """Resolve the published base URL from the operator environment.

    Returns:
        The configured base URL, or an empty string when unset.
    """
    explicit = os.environ.get(PUBLIC_BASE_URL_ENV, "").strip()
    if explicit:
        return explicit
    host_uuid = os.environ.get(PUBLIC_HOST_UUID_ENV, "").strip()
    base_domain = os.environ.get(PUBLIC_BASE_DOMAIN_ENV, "").strip()
    if host_uuid and base_domain:
        return f"https://{host_uuid}.{base_domain}"
    return ""


DEFAULT_PUBLIC_BASE_URL: Final = _default_public_base_url()
DEFAULT_OAUTH_CLIENT_STORE_PATH = Path("src/mcp/data/oauth/clients.json")
DEFAULT_OAUTH_TOKEN_STORE_PATH = Path("src/mcp/data/oauth/tokens.json")
DEFAULT_OPERATOR_OAUTH_CLIENT_STORE_PATH = Path(
    "data/pancakes-mcp/oauth/clients.json"
)
DEFAULT_OPERATOR_OAUTH_TOKEN_STORE_PATH = Path(
    "data/pancakes-mcp/oauth/tokens.json"
)
REMOTE_MCP_OPERATOR_PASSWORD_ENV = "REMOTE_MCP_OPERATOR_PASSWORD"
MCP_PROTOCOL_VERSION = "2025-06-18"
AUTHORIZATION_HEADER_PART_COUNT = 2
OAUTH_READ_SCOPE = "mcp:read"
OAUTH_WRITE_SCOPE = "mcp:write"
OAUTH_SCOPE = f"{OAUTH_READ_SCOPE} {OAUTH_WRITE_SCOPE}"
OAUTH_UNSUPPORTED_SCOPE_ERROR = "Unsupported OAuth scope requested."
OAUTH_SCOPES: Final = (OAUTH_READ_SCOPE, OAUTH_WRITE_SCOPE)
OAUTH_TOKEN_STORE_SCHEMA_VERSION = 2
SHA256_HEX_LENGTH = 64
TOKEN_EXPIRY_SECONDS = 10 * 365 * 24 * 60 * 60
OAUTH_CODE_EXPIRY_SECONDS = 600
MCP_RPC_PATHS = frozenset(("/", "/mcp"))
JSON_REQUEST_CONTENT_TYPE = "application/json"
FORM_REQUEST_CONTENT_TYPE = "application/x-www-form-urlencoded"
MAX_MCP_JSON_BODY_BYTES: Final = 1_048_576
MAX_MCP_FORM_BODY_BYTES: Final = 65_536
AUTH_AUDIT_MAX_EVENTS: Final = 100
AUTH_AUDIT_MAX_FIELD_CHARS: Final = 160
APPROVED_OAUTH_CUSTOM_REDIRECT_SCHEMES: Final = frozenset({"make-mcp"})
APPROVED_OAUTH_HTTPS_REDIRECT_URIS: Final = frozenset(
    {"https://chat.openai.com/aip/plugin/callback"}
)
APPROVED_OAUTH_HTTPS_REDIRECT_HOSTS: Final = frozenset(
    {
        "chat.openai.com",
        "chatgpt.com",
    }
)
LOCAL_ARTIFACT_PERMISSION_COPY: Final[dict[str, str]] = {
    "catalog.modify": (
        "Updating typed local catalog state only; dry-runs write nothing."
    ),
    "catalog.node.modify": "Updating typed local catalog graph nodes only.",
    "catalog.edge.propose": "Recording typed local catalog edge proposal only.",
    "catalog.edge.apply": "Applying approved local catalog graph edge only.",
    "catalog.review.add": (
        "Recording local catalog review item only; dry-runs write nothing."
    ),
    "project.draft.stage": (
        "Staging local project draft only; dry-runs write nothing."
    ),
    "project.draft.import": (
        "Staging local project artifact only; dry-runs write nothing."
    ),
    "project.create": "Creating local project draft only.",
    "project.edit": "Editing local project graph only.",
    "project.make": "Writing local Make artifact projection only.",
    "project.modules.add": "Adding local project module only.",
    "project.modules.modify": "Modifying local project module only.",
    "project.modules.delete": "Previewing local project module removal only.",
    "project.filters.add": "Adding local project filter only.",
    "project.filters.modify": "Modifying local project filter only.",
    "project.filters.delete": "Previewing local project filter removal only.",
    "project.error_handlers.add": "Adding local error handler only.",
    "project.error_handlers.modify": "Modifying local error handler only.",
    "project.error_handlers.delete": (
        "Previewing local error handler removal only."
    ),
    "backlog.add": "Recording local SQLite backlog item only.",
    "backlog.end": "Closing local SQLite backlog item only.",
}


class RemoteMcpHttpOptions(NamedTuple):
    """Configuration for one loopback HTTP MCP server."""

    repo_root: Path
    host: str = DEFAULT_REMOTE_MCP_HOST
    port: int = DEFAULT_REMOTE_MCP_PORT
    public_base_url: str = DEFAULT_PUBLIC_BASE_URL
    oauth_client_store_path: Path | None = None
    oauth_token_store_path: Path | None = None
    operator_password: str | None = None


class OAuthClientRecord(NamedTuple):
    """One dynamically registered OAuth client."""

    client_id: str
    redirect_uris: tuple[str, ...]
    issued_at: int


class OAuthCodeRecord(NamedTuple):
    """One short-lived authorization code."""

    code: str
    client_id: str
    redirect_uri: str
    issued_at: int
    scopes: tuple[McpOauthScope, ...]
    code_challenge: str | None = None
    code_challenge_method: str | None = None


class OAuthTokenRecord(NamedTuple):
    """One bearer token accepted by the MCP endpoint."""

    access_token_hash: str
    client_id: str
    issued_at: int
    expires_at: int
    scopes: tuple[McpOauthScope, ...]
    access_token: str | None = None


class OAuthIssuedToken(NamedTuple):
    """One newly issued bearer token and its persisted hash-backed record."""

    access_token: str
    record: OAuthTokenRecord


class RemoteMcpAuthAuditEvent(NamedTuple):
    """One bounded redacted authentication audit event."""

    occurred_at: int
    event_type: str
    status: str
    remote_ip: str
    method: str
    path: str
    client_id_sha256: str | None
    scope: str | None


class HttpBodyReadError(Exception):
    """Bounded HTTP body read failure with an explicit response status."""

    def __init__(self, status: HTTPStatus, message: str) -> None:
        """Create one HTTP body read error."""
        super().__init__(message)
        self.status = status


class RemoteMcpOAuthStore:
    """OAuth state for the local remote MCP origin."""

    def __init__(
        self, *, client_store_path: Path, token_store_path: Path
    ) -> None:
        """Create client, code, and token stores."""
        self._client_store_path = client_store_path
        self._token_store_path = token_store_path
        self._lock = Lock()
        self._clients = _load_oauth_clients(client_store_path)
        self._codes: dict[str, OAuthCodeRecord] = {}
        self._tokens = _load_oauth_tokens(token_store_path)

    def register_client(
        self, redirect_uris: tuple[str, ...]
    ) -> OAuthClientRecord:
        """Register one dynamic OAuth client.

        Returns:
            The persisted dynamic OAuth client record.
        """
        with self._lock:
            client_id = secrets.token_urlsafe(24)
            record = OAuthClientRecord(
                client_id=client_id,
                redirect_uris=redirect_uris,
                issued_at=_epoch_seconds(),
            )
            self._clients[client_id] = record
            _save_oauth_clients(self._client_store_path, self._clients.values())
            return record

    def issue_code(
        self,
        *,
        client_id: str,
        redirect_uri: str,
        scopes: tuple[McpOauthScope, ...],
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
    ) -> OAuthCodeRecord:
        """Issue one authorization code for a known client.

        Returns:
            The issued authorization code record.

        Raises:
            ValueError: If the client or redirect URI is invalid.
        """
        with self._lock:
            client = self._clients.get(client_id)
            if client is None:
                message = "Unknown OAuth client."
                raise ValueError(message)
            if redirect_uri not in client.redirect_uris:
                message = (
                    "Redirect URI is not registered for this OAuth client."
                )
                raise ValueError(message)
            code = secrets.token_urlsafe(24)
            record = OAuthCodeRecord(
                code=code,
                client_id=client_id,
                redirect_uri=redirect_uri,
                issued_at=_epoch_seconds(),
                scopes=scopes,
                code_challenge=code_challenge,
                code_challenge_method=code_challenge_method,
            )
            self._codes[code] = record
            return record

    def exchange_code(
        self,
        *,
        code: str,
        client_id: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> OAuthIssuedToken:
        """Exchange one authorization code for a bearer token.

        Returns:
            The issued bearer token and persisted token record.

        Raises:
            ValueError: If the code, redirect URI, or PKCE verifier is invalid.
        """
        with self._lock:
            record = self._codes.get(code)
            if (
                record is None
                or record.client_id != client_id
                or record.redirect_uri != redirect_uri
            ):
                message = "Invalid OAuth authorization code."
                raise ValueError(message)
            now = _epoch_seconds()
            if record.issued_at + OAUTH_CODE_EXPIRY_SECONDS <= now:
                _ = self._codes.pop(code)
                message = "Expired OAuth authorization code."
                raise ValueError(message)
            if record.code_challenge is not None and not _pkce_s256_matches(
                code_verifier,
                record.code_challenge,
            ):
                _ = self._codes.pop(code)
                message = "Invalid OAuth PKCE verifier."
                raise ValueError(message)
            _ = self._codes.pop(code)
            access_token = secrets.token_urlsafe(32)
            token = OAuthTokenRecord(
                access_token_hash=_oauth_token_hash(access_token),
                client_id=client_id,
                issued_at=now,
                expires_at=now + TOKEN_EXPIRY_SECONDS,
                scopes=record.scopes,
                access_token=access_token,
            )
            self._tokens[token.access_token_hash] = token
            _save_oauth_tokens(self._token_store_path, self._tokens.values())
            return OAuthIssuedToken(access_token=access_token, record=token)

    def token_record(self, access_token: str) -> OAuthTokenRecord | None:
        """Return a valid bearer token record, if present and not expired."""
        with self._lock:
            token_hash = _oauth_token_hash(access_token)
            token = self._tokens.get(token_hash)
            if token is None:
                return None
            if token.expires_at > _epoch_seconds():
                return token
            return None

    def revoke_token(self, access_token: str) -> bool:
        """Revoke one bearer token without persisting or returning its value.

        Returns:
            Whether a stored bearer-token hash was removed.
        """
        with self._lock:
            token_hash = _oauth_token_hash(access_token)
            removed = self._tokens.pop(token_hash, None) is not None
            if removed:
                _save_oauth_tokens(
                    self._token_store_path, self._tokens.values()
                )
            return removed

    def revoke_client(self, client_id: str) -> bool:
        """Revoke one OAuth client and all stored tokens issued for it.

        Returns:
            Whether a client or bearer-token hash was removed.
        """
        with self._lock:
            removed_client = self._clients.pop(client_id, None) is not None
            self._codes = {
                code: record
                for code, record in self._codes.items()
                if record.client_id != client_id
            }
            token_count_before = len(self._tokens)
            self._tokens = {
                token_hash: record
                for token_hash, record in self._tokens.items()
                if record.client_id != client_id
            }
            removed_token = len(self._tokens) != token_count_before
            if removed_client:
                _save_oauth_clients(
                    self._client_store_path, self._clients.values()
                )
            if removed_token:
                _save_oauth_tokens(
                    self._token_store_path, self._tokens.values()
                )
            return removed_client or removed_token

    def reset(self) -> None:
        """Clear local OAuth clients, codes, and bearer-token hashes."""
        with self._lock:
            self._clients = {}
            self._codes = {}
            self._tokens = {}
            _save_oauth_clients(self._client_store_path, ())
            _save_oauth_tokens(self._token_store_path, ())


class RemoteMcpHttpServer(ThreadingHTTPServer):
    """Threading HTTP server carrying MCP origin state."""

    def __init__(
        self,
        options: RemoteMcpHttpOptions,
        oauth_store: RemoteMcpOAuthStore,
        operator_password: str | None,
    ) -> None:
        """Build one HTTP server with repository MCP state."""
        super().__init__((options.host, options.port), RemoteMcpHttpHandler)
        self.options = options
        self.oauth_store = oauth_store
        self.operator_password = operator_password
        self.tool_list_result = _build_tool_list_result()
        self.tool_scope_by_name = _build_tool_scope_by_name()
        self._auth_audit_lock = Lock()
        self._auth_audit_events: list[RemoteMcpAuthAuditEvent] = []

    def record_auth_audit(self, event: RemoteMcpAuthAuditEvent) -> None:
        """Record one bounded redacted auth audit event."""
        with self._auth_audit_lock:
            self._auth_audit_events.append(event)
            del self._auth_audit_events[:-AUTH_AUDIT_MAX_EVENTS]

    def auth_audit_events(self) -> tuple[RemoteMcpAuthAuditEvent, ...]:
        """Return a bounded copy of redacted auth audit evidence."""
        with self._auth_audit_lock:
            return tuple(self._auth_audit_events)


class RemoteMcpHttpHandler(BaseHTTPRequestHandler):
    """HTTP request handler for OAuth discovery and MCP JSON-RPC."""

    server_version = "MakeMcpRemote/1"

    def do_GET(self) -> None:
        """Handle read-side HTTP routes."""
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/health"}:
            self._send_json(HTTPStatus.OK, self._health_payload())
            return
        if _path_is_well_known(
            parsed.path, "/.well-known/oauth-protected-resource"
        ):
            self._send_json(HTTPStatus.OK, self._protected_resource_metadata())
            return
        if _path_is_well_known(
            parsed.path, "/.well-known/oauth-authorization-server"
        ):
            self._send_json(
                HTTPStatus.OK, self._authorization_server_metadata()
            )
            return
        if parsed.path == "/authorize":
            self._authorize(
                parse_qs(parsed.query), operator_authenticated=False
            )
            return
        if parsed.path == "/mcp":
            self._send_json(
                HTTPStatus.METHOD_NOT_ALLOWED,
                {"error": "MCP endpoint expects JSON-RPC POST requests."},
                headers={
                    "WWW-Authenticate": _www_authenticate_challenge(
                        self._remote_server().options.public_base_url
                    )
                },
            )
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Unknown route."})

    def do_POST(self) -> None:
        """Handle OAuth and MCP JSON-RPC write-side HTTP routes."""
        parsed = urlparse(self.path)
        if parsed.path == "/register":
            self._register_client()
            return
        if parsed.path == "/authorize":
            self._authorize_with_operator_password()
            return
        if parsed.path == "/token":
            self._exchange_token()
            return
        if parsed.path in MCP_RPC_PATHS:
            self._handle_mcp_rpc()
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Unknown route."})

    @override
    def log_message(self, format: str, *args: object) -> None:
        """Suppress default stderr logging; the service owns bounded logs."""
        del format, args

    def _authorize(
        self,
        query: Mapping[str, list[str]],
        *,
        operator_authenticated: bool,
    ) -> None:
        """Handle OAuth authorization by issuing a code redirect."""
        client_id = _first_query_value(query, "client_id")
        redirect_uri = _first_query_value(query, "redirect_uri")
        state = _first_query_value(query, "state", trim=False)
        scope_text = _first_query_value(query, "scope")
        code_challenge = _first_query_value(query, "code_challenge")
        code_challenge_method = _first_query_value(
            query, "code_challenge_method"
        )
        if client_id is None or redirect_uri is None:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                _oauth_error(
                    "Missing OAuth query fields.", "oauth_query_fields_missing"
                ),
            )
            return
        try:
            _validate_oauth_redirect_uri(redirect_uri)
        except (TypeError, ValueError) as exc:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                _oauth_error(
                    "Invalid OAuth redirect URI.",
                    "oauth_redirect_uri_invalid",
                    detail=str(exc),
                ),
            )
            return
        try:
            scopes = _requested_oauth_scopes(scope_text)
        except ValueError as exc:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                _oauth_error(str(exc), "oauth_scope_unsupported"),
            )
            return
        if not operator_authenticated:
            self._send_operator_login_form(query)
            return
        pkce_error = _pkce_authorization_error(
            code_challenge, code_challenge_method
        )
        if pkce_error is not None:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                _oauth_error(pkce_error, "oauth_pkce_invalid"),
            )
            return
        try:
            code = self._remote_server().oauth_store.issue_code(
                client_id=client_id,
                redirect_uri=redirect_uri,
                scopes=scopes,
                code_challenge=code_challenge,
                code_challenge_method=code_challenge_method,
            )
        except ValueError as exc:
            error = str(exc)
            self._record_auth_audit(
                event_type="oauth_authorize",
                status="rejected",
                client_id=client_id,
                scope=_oauth_scope_text(scopes),
            )
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                _oauth_error(error, _oauth_authorization_error_code(error)),
            )
            return
        self._record_auth_audit(
            event_type="oauth_authorize",
            status="accepted",
            client_id=client_id,
            scope=_oauth_scope_text(scopes),
        )
        redirect_query: dict[str, str] = {"code": code.code}
        if state is not None:
            redirect_query["state"] = state
        separator = "&" if "?" in redirect_uri else "?"
        self.send_response(HTTPStatus.FOUND)
        self.send_header(
            "Location", f"{redirect_uri}{separator}{urlencode(redirect_query)}"
        )
        self.end_headers()

    def _authorize_with_operator_password(self) -> None:
        """Authorize an OAuth request after validating the local operator.

        password.
        """
        try:
            form = self._read_form_body()
        except HttpBodyReadError as exc:
            self._send_json(
                exc.status,
                _oauth_error(
                    "Invalid OAuth authorization request.",
                    "oauth_authorization_request_invalid",
                    detail=str(exc),
                ),
            )
            return
        except (UnicodeDecodeError, ValueError) as exc:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                _oauth_error(
                    "Invalid OAuth authorization request.",
                    "oauth_authorization_request_invalid",
                    detail=str(exc),
                ),
            )
            return
        if not self._operator_password_matches(
            _first_query_value(form, "operator_password")
        ):
            if not self._operator_password_configured():
                self._record_auth_audit(
                    event_type="oauth_authorize",
                    status="password_unconfigured",
                    client_id=_first_query_value(form, "client_id"),
                    scope=_first_query_value(form, "scope"),
                )
                self._send_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    _oauth_error(
                        "Operator password is not configured.",
                        "oauth_operator_password_unconfigured",
                    ),
                )
                return
            self._record_auth_audit(
                event_type="oauth_authorize",
                status="invalid_password",
                client_id=_first_query_value(form, "client_id"),
                scope=_first_query_value(form, "scope"),
            )
            self._send_json(
                HTTPStatus.UNAUTHORIZED,
                _oauth_error(
                    "Invalid operator password.",
                    "oauth_operator_password_invalid",
                ),
            )
            return
        self._authorize(form, operator_authenticated=True)

    def _operator_password_configured(self) -> bool:
        """Return whether the server has a configured operator password."""
        return self._remote_server().operator_password is not None

    def _operator_password_matches(self, supplied_password: str | None) -> bool:
        """Return whether a submitted password matches the configured operator.

        password.
        """
        expected_password = self._remote_server().operator_password
        if expected_password is None or supplied_password is None:
            return False
        return secrets.compare_digest(supplied_password, expected_password)

    def _send_operator_login_form(self, query: Mapping[str, list[str]]) -> None:
        """Return a minimal OAuth password form for browser-based MCP login."""
        hidden_inputs = "\n".join(
            _hidden_input(name, value)
            for name in (
                "client_id",
                "redirect_uri",
                "state",
                "scope",
                "code_challenge",
                "code_challenge_method",
            )
            if (value := _first_query_value(query, name, trim=name != "state"))
            is not None
        )
        body = (
            '<!doctype html><html><head><meta charset="utf-8">'
            "<title>Make MCP Login</title></head><body>"
            "<h1>Make MCP Login</h1>"
            '<form method="post" action="/authorize">'
            f"{hidden_inputs}"
            '<label>Password <input name="operator_password" type="password" '
            'autocomplete="current-password" autofocus></label>'
            '<button type="submit">Authorize</button>'
            "</form></body></html>"
        ).encode()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        _ = self.wfile.write(body)

    def _register_client(self) -> None:
        """Handle OAuth dynamic client registration."""
        try:
            payload = self._read_json_body()
        except HttpBodyReadError as exc:
            self._send_json(
                exc.status,
                _oauth_error(
                    "Invalid OAuth registration request.",
                    "oauth_registration_request_invalid",
                    detail=str(exc),
                ),
            )
            return
        except (
            json.JSONDecodeError,
            TypeError,
            UnicodeDecodeError,
            ValueError,
        ) as exc:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                _oauth_error(
                    "Invalid OAuth registration request.",
                    "oauth_registration_request_invalid",
                    detail=str(exc),
                ),
            )
            return
        try:
            redirect_uris = _oauth_redirect_uri_tuple(
                payload.get("redirect_uris")
            )
        except (TypeError, ValueError) as exc:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                _oauth_error(
                    "Invalid OAuth redirect URI.",
                    "oauth_redirect_uri_invalid",
                    detail=str(exc),
                ),
            )
            return
        if not redirect_uris:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                _oauth_error(
                    "Dynamic registration requires redirect_uris.",
                    "oauth_redirect_uris_missing",
                ),
            )
            return
        client = self._remote_server().oauth_store.register_client(
            redirect_uris
        )
        self._send_json(
            HTTPStatus.CREATED,
            {
                "client_id": client.client_id,
                "client_id_issued_at": client.issued_at,
                "redirect_uris": list(client.redirect_uris),
                "grant_types": ["authorization_code"],
                "response_types": ["code"],
                "scope": OAUTH_SCOPE,
                "token_endpoint_auth_method": "none",
            },
        )

    def _exchange_token(self) -> None:
        """Handle OAuth token exchange."""
        try:
            form = self._read_form_body()
        except HttpBodyReadError as exc:
            self._send_oauth_token_json(
                exc.status,
                _oauth_error(
                    "Invalid OAuth token request.",
                    "oauth_token_request_invalid",
                    detail=str(exc),
                ),
            )
            return
        except (UnicodeDecodeError, ValueError) as exc:
            self._send_oauth_token_json(
                HTTPStatus.BAD_REQUEST,
                _oauth_error(
                    "Invalid OAuth token request.",
                    "oauth_token_request_invalid",
                    detail=str(exc),
                ),
            )
            return
        if _first_query_value(form, "grant_type") != "authorization_code":
            self._record_auth_audit(
                event_type="oauth_token", status="unsupported_grant"
            )
            self._send_oauth_token_json(
                HTTPStatus.BAD_REQUEST,
                _oauth_error(
                    "Unsupported grant type.", "oauth_grant_type_unsupported"
                ),
            )
            return
        code = _first_query_value(form, "code")
        client_id = _first_query_value(form, "client_id")
        redirect_uri = _first_query_value(form, "redirect_uri")
        code_verifier = _first_query_value(form, "code_verifier")
        if code is None or client_id is None or redirect_uri is None:
            self._record_auth_audit(
                event_type="oauth_token",
                status="missing_fields",
                client_id=client_id,
            )
            self._send_oauth_token_json(
                HTTPStatus.BAD_REQUEST,
                _oauth_error(
                    "Missing token request fields.",
                    "oauth_token_fields_missing",
                ),
            )
            return
        try:
            _validate_oauth_redirect_uri(redirect_uri)
        except ValueError as exc:
            self._send_oauth_token_json(
                HTTPStatus.BAD_REQUEST,
                _oauth_error(
                    "Invalid OAuth redirect URI.",
                    "oauth_redirect_uri_invalid",
                    detail=str(exc),
                ),
            )
            return
        try:
            issued_token = self._remote_server().oauth_store.exchange_code(
                code=code,
                client_id=client_id,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
            )
        except ValueError as exc:
            error = str(exc)
            self._record_auth_audit(
                event_type="oauth_token",
                status="rejected",
                client_id=client_id,
            )
            self._send_oauth_token_json(
                HTTPStatus.BAD_REQUEST,
                _oauth_error(error, _oauth_token_error_code(error)),
            )
            return
        self._record_auth_audit(
            event_type="oauth_token",
            status="accepted",
            client_id=client_id,
            scope=_oauth_scope_text(issued_token.record.scopes),
        )
        self._send_oauth_token_json(
            HTTPStatus.OK,
            {
                "access_token": issued_token.access_token,
                "token_type": "Bearer",
                "expires_in": TOKEN_EXPIRY_SECONDS,
                "scope": _oauth_scope_text(issued_token.record.scopes),
            },
        )

    def _handle_mcp_rpc(self) -> None:
        """Handle one MCP JSON-RPC request."""
        try:
            request_payload = self._read_json_body()
        except HttpBodyReadError as exc:
            self._send_body_read_error(exc, error="Invalid JSON-RPC request.")
            return
        except (
            json.JSONDecodeError,
            TypeError,
            UnicodeDecodeError,
            ValueError,
        ) as exc:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "Invalid JSON-RPC request.",
                    "detail": str(exc),
                },
            )
            return
        method = _optional_text(request_payload.get("method"))
        token_record = (
            None
            if _anonymous_mcp_method(method)
            else self._bearer_token_record()
        )
        if not _anonymous_mcp_method(method) and token_record is None:
            self._record_auth_audit(
                event_type="mcp_bearer", status="missing_or_invalid"
            )
            challenge = _www_authenticate_challenge(
                self._remote_server().options.public_base_url
            )
            self._send_json(
                HTTPStatus.UNAUTHORIZED,
                _oauth_error(
                    "Bearer token is required for MCP requests.",
                    "oauth_bearer_token_required",
                ),
                headers={"WWW-Authenticate": challenge},
            )
            return
        if token_record is not None:
            self._record_auth_audit(
                event_type="mcp_bearer",
                status="accepted",
                client_id=token_record.client_id,
                scope=_oauth_scope_text(token_record.scopes),
            )
        response_payload = self._mcp_response(
            request_payload, token_record=token_record
        )
        if response_payload is None:
            self.send_response(HTTPStatus.ACCEPTED)
            self.end_headers()
            return
        self._send_json(HTTPStatus.OK, response_payload)

    def _mcp_response(
        self,
        request_payload: JsonObject,
        *,
        token_record: OAuthTokenRecord | None,
    ) -> JsonObject | None:
        """Return one JSON-RPC response for a supported MCP method."""
        method = _optional_text(request_payload.get("method"))
        request_id = request_payload.get("id")
        if request_id is None:
            return None
        try:
            params = _object_or_empty(request_payload.get("params"))
        except (TypeError, ValueError) as exc:
            return _json_rpc_error(request_id, -32602, str(exc))
        return self._mcp_method_response(
            request_id=request_id,
            method=method,
            params=params,
            token_record=token_record,
        )

    def _mcp_method_response(
        self,
        *,
        request_id: object,
        method: str | None,
        params: JsonObject,
        token_record: OAuthTokenRecord | None,
    ) -> JsonObject:
        """Return one JSON-RPC response for a supported MCP method."""
        if method == "initialize":
            return _json_rpc_result(request_id, self._initialize_result())
        if method == "tools/list":
            return self._tools_list_response(
                request_id, token_record=token_record
            )
        context_response = self._mcp_context_method_response(
            request_id=request_id,
            method=method,
            params=params,
            token_record=token_record,
        )
        if context_response is not None:
            return context_response
        if method == "tools/call":
            try:
                return _json_rpc_result(
                    request_id,
                    self._call_tool(params, token_record=token_record),
                )
            except (TypeError, ValueError) as exc:
                return _json_rpc_error(request_id, -32602, str(exc))
        return _json_rpc_error(
            request_id, -32601, f"Unknown MCP method: {method}"
        )

    def _mcp_context_method_response(
        self,
        *,
        request_id: object,
        method: str | None,
        params: JsonObject,
        token_record: OAuthTokenRecord | None,
    ) -> JsonObject | None:
        """Return the computed result for the caller."""
        if method == "resources/list":
            return self._resource_list_response(
                request_id, token_record=token_record
            )
        if method == "prompts/list":
            return self._prompt_list_response(
                request_id, token_record=token_record
            )
        if method == "resources/read":
            return self._read_resource_response(
                request_id=request_id, params=params
            )
        if method == "prompts/get":
            auth_response = self._read_scope_required_response(token_record)
            if auth_response is not None:
                return _json_rpc_result(request_id, auth_response)
            return self._get_prompt_response(
                request_id=request_id, params=params
            )
        return None

    def _tools_list_response(
        self,
        request_id: object,
        *,
        token_record: OAuthTokenRecord | None,
    ) -> JsonObject:
        """Return the public tool descriptor list used by MCP clients for.

        action.

        refresh.
        """
        del token_record
        return _json_rpc_result(
            request_id, self._remote_server().tool_list_result
        )

    def _resource_list_response(
        self,
        request_id: object,
        *,
        token_record: OAuthTokenRecord | None,
    ) -> JsonObject:
        """Return resource descriptors when the bearer token has read scope."""
        auth_response = self._read_scope_required_response(
            token_record,
            error_description=(
                "The mcp:read scope is required to list MCP resources."
            ),
        )
        if auth_response is not None:
            return _json_rpc_result(request_id, auth_response)
        resources = [
            _resource_payload(resource) for resource in mcp_resource_registry()
        ]
        return _json_rpc_result(request_id, {"resources": resources})

    def _prompt_list_response(
        self,
        request_id: object,
        *,
        token_record: OAuthTokenRecord | None,
    ) -> JsonObject:
        """Return prompt descriptors when the bearer token has read scope."""
        auth_response = self._read_scope_required_response(
            token_record,
            error_description=(
                "The mcp:read scope is required to list MCP prompts."
            ),
        )
        if auth_response is not None:
            return _json_rpc_result(request_id, auth_response)
        prompts = [_prompt_payload(prompt) for prompt in mcp_prompt_registry()]
        return _json_rpc_result(request_id, {"prompts": prompts})

    def _read_scope_required_response(
        self,
        token_record: OAuthTokenRecord | None,
        *,
        error_description: str = "The mcp:read scope is required to read MCP prompts.",
    ) -> JsonObject | None:
        """Return the computed result for the caller."""
        required_scope = cast("McpOauthScope", OAUTH_READ_SCOPE)
        if _token_has_scope(token_record, required_scope):
            return None
        challenge = _www_authenticate_challenge(
            self._remote_server().options.public_base_url,
            scope=required_scope,
            error_description=error_description,
        )
        return _scope_required_result(challenge, required_scope)

    def _read_resource_response(
        self,
        *,
        request_id: object,
        params: JsonObject,
    ) -> JsonObject:
        """Return one resources/read response or JSON-RPC parameter error."""
        try:
            content = read_mcp_resource(
                repo_root=self._remote_server().options.repo_root,
                uri=_required_text(params, "uri"),
            )
            return _json_rpc_result(request_id, {"contents": [content]})
        except (OSError, TypeError, ValueError) as exc:
            return _json_rpc_error(request_id, -32602, str(exc))

    def _get_prompt_response(
        self,
        *,
        request_id: object,
        params: JsonObject,
    ) -> JsonObject:
        """Return one prompts/get response or JSON-RPC parameter error."""
        try:
            prompt = get_mcp_prompt(
                repo_root=self._remote_server().options.repo_root,
                name=_required_text(params, "name"),
            )
            return _json_rpc_result(request_id, prompt)
        except (OSError, TypeError, ValueError) as exc:
            return _json_rpc_error(request_id, -32602, str(exc))

    def _call_tool(
        self,
        params: JsonObject,
        *,
        token_record: OAuthTokenRecord | None,
    ) -> JsonObject:
        """Execute one MCP tool call without per-tool approval prompts.

        Returns:
            The MCP tools/call response payload.
        """
        tool_name = _required_text(params, "name")
        required_scope = self._remote_server().tool_scope_by_name.get(
            tool_name, OAUTH_WRITE_SCOPE
        )
        if not _token_has_scope(token_record, required_scope):
            challenge = _www_authenticate_challenge(
                self._remote_server().options.public_base_url,
                scope=required_scope,
                error_description=(
                    f"The {required_scope} scope is required for this MCP tool."
                ),
            )
            return _scope_required_result(challenge, required_scope)
        arguments = _object_or_empty(params.get("arguments"))
        result = execute_mcp_tool(
            tool_name=tool_name,
            arguments=arguments,
            repo_root=self._remote_server().options.repo_root,
        )
        payload: JsonObject = (
            result.payload if result.ok else {"error": result.error or "failed"}
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        payload, ensure_ascii=True, sort_keys=True
                    ),
                }
            ],
            "isError": not result.ok,
        }

    @staticmethod
    def _initialize_result() -> JsonObject:
        """Return MCP initialize response metadata."""
        return {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {
                "tools": {"listChanged": False},
                "prompts": {"listChanged": False},
            },
            "serverInfo": {"name": MCP_SERVER_NAME, "version": "0.0.0"},
        }

    @staticmethod
    def _health_payload() -> JsonObject:
        """Return minimal remote origin health metadata."""
        return {"status": "ok"}

    def _protected_resource_metadata(self) -> JsonObject:
        """Return OAuth protected resource metadata."""
        base_url = self._remote_server().options.public_base_url
        return {
            "resource": base_url,
            "authorization_servers": [base_url],
            "scopes_supported": list(OAUTH_SCOPES),
            "bearer_methods_supported": ["header"],
        }

    def _authorization_server_metadata(self) -> JsonObject:
        """Return OAuth authorization server metadata."""
        base_url = self._remote_server().options.public_base_url
        return {
            "issuer": base_url,
            "authorization_endpoint": f"{base_url}/authorize",
            "token_endpoint": f"{base_url}/token",
            "registration_endpoint": f"{base_url}/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
            "scopes_supported": list(OAUTH_SCOPES),
        }

    def _bearer_token_record(self) -> OAuthTokenRecord | None:
        """Return the computed result for the caller."""
        authorization = self.headers.get("Authorization", "")
        auth_parts = authorization.split(None, 1)
        if (
            len(auth_parts) != AUTHORIZATION_HEADER_PART_COUNT
            or auth_parts[0].casefold() != "bearer"
        ):
            return None
        token = auth_parts[1].strip()
        if not token:
            return None
        return self._remote_server().oauth_store.token_record(token)

    def _read_json_body(self) -> JsonObject:
        """Read a JSON object request body.

        Returns:
            The parsed JSON object body.

        Raises:
            TypeError: If the request body is not a JSON object.
        """
        self._require_content_type(JSON_REQUEST_CONTENT_TYPE)
        raw_body = self._read_body(max_bytes=MAX_MCP_JSON_BODY_BYTES)
        if not raw_body:
            return {}
        payload = cast("object", json.loads(raw_body.decode("utf-8")))
        if not isinstance(payload, dict):
            message = "Expected a JSON object request body."
            raise TypeError(message)
        return {
            str(key): value
            for key, value in cast("Mapping[object, object]", payload).items()
        }

    def _read_form_body(self) -> dict[str, list[str]]:
        """Read a URL-encoded form request body.

        Returns:
            The parsed form values.
        """
        self._require_content_type(FORM_REQUEST_CONTENT_TYPE)
        return parse_qs(
            self._read_body(max_bytes=MAX_MCP_FORM_BODY_BYTES).decode("utf-8")
        )

    def _require_content_type(self, expected_content_type: str) -> None:
        """Require one HTTP request media type before body parsing.

        Raises:
        HttpBodyReadError: If the request media type is missing or unsupported.
        """
        content_type = self.headers.get("Content-Type")
        media_type = (
            ""
            if content_type is None
            else content_type.split(";", 1)[0].strip().casefold()
        )
        if media_type != expected_content_type:
            message = f"Expected Content-Type {expected_content_type}."
            raise HttpBodyReadError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, message)

    def _read_body(self, *, max_bytes: int) -> bytes:
        """Read request body bytes.

        Returns:
            The request body bytes.

        Raises:
        HttpBodyReadError: If Content-Length is missing, invalid, or too large.
        """
        length_text = self.headers.get("Content-Length")
        if length_text is None:
            message = "Content-Length is required."
            raise HttpBodyReadError(HTTPStatus.LENGTH_REQUIRED, message)
        try:
            length = int(length_text)
        except ValueError as exc:
            message = "Content-Length must be an integer."
            raise HttpBodyReadError(HTTPStatus.BAD_REQUEST, message) from exc
        if length < 0:
            message = "Content-Length must be non-negative."
            raise HttpBodyReadError(HTTPStatus.BAD_REQUEST, message)
        if length > max_bytes:
            message = f"Content-Length must not exceed {max_bytes} bytes."
            raise HttpBodyReadError(HTTPStatus.CONTENT_TOO_LARGE, message)
        return self.rfile.read(length) if length > 0 else b""

    def _send_body_read_error(
        self, exc: HttpBodyReadError, *, error: str
    ) -> None:
        """Send a route-specific JSON error for a bounded body read failure."""
        self._send_json(exc.status, {"error": error, "detail": str(exc)})

    def _send_json(
        self,
        status: HTTPStatus,
        payload: JsonObject,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """Send one JSON response."""
        body = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode(
            "utf-8"
        )
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if headers is not None:
            for name, value in headers.items():
                self.send_header(name, value)
        self.end_headers()
        _ = self.wfile.write(body)

    def _send_oauth_token_json(
        self, status: HTTPStatus, payload: JsonObject
    ) -> None:
        """Send one OAuth token endpoint JSON response with cache hardening."""
        self._send_json(status, payload, headers={"Pragma": "no-cache"})

    def _remote_server(self) -> RemoteMcpHttpServer:
        """Return the typed HTTP server instance."""
        return cast("RemoteMcpHttpServer", self.server)

    def _record_auth_audit(
        self,
        *,
        event_type: str,
        status: str,
        client_id: str | None = None,
        scope: str | None = None,
    ) -> None:
        """Append one redacted auth event to the bounded in-process audit log.

        Record only bounded audit data.
        """
        self._remote_server().record_auth_audit(
            RemoteMcpAuthAuditEvent(
                occurred_at=_epoch_seconds(),
                event_type=_bounded_audit_text(event_type),
                status=_bounded_audit_text(status),
                remote_ip=_bounded_audit_text(str(self.client_address[0])),
                method=_bounded_audit_text(self.command),
                path=_bounded_audit_text(urlparse(self.path).path),
                client_id_sha256=_optional_sha256_text(client_id),
                scope=None if scope is None else _bounded_audit_text(scope),
            )
        )


def build_remote_mcp_http_server(
    options: RemoteMcpHttpOptions,
) -> RemoteMcpHttpServer:
    """Build a remote MCP HTTP server without starting it.

    Returns:
        The configured remote MCP HTTP server.
    """
    _validate_remote_mcp_http_options(options)
    return RemoteMcpHttpServer(
        options=options,
        oauth_store=RemoteMcpOAuthStore(
            client_store_path=_oauth_client_store_path(options),
            token_store_path=_oauth_token_store_path(options),
        ),
        operator_password=_operator_password(options),
    )


def serve_remote_mcp_http(options: RemoteMcpHttpOptions) -> None:
    """Run the remote MCP HTTP server until the process exits."""
    with build_remote_mcp_http_server(options) as server:
        _start_knowledge_prewarm(options.repo_root)
        server.serve_forever()


def reset_remote_mcp_oauth_state(options: RemoteMcpHttpOptions) -> JsonObject:
    """Clear local OAuth clients and bearer-token hashes without exposing.

    secrets.

    Returns:
        A redacted reset receipt.
    """
    oauth_store = RemoteMcpOAuthStore(
        client_store_path=_oauth_client_store_path(options),
        token_store_path=_oauth_token_store_path(options),
    )
    oauth_store.reset()
    return {
        "status": "reset",
        "clients_cleared": True,
        "tokens_cleared": True,
        "secrets_printed": False,
    }


def revoke_remote_mcp_bearer_token(
    options: RemoteMcpHttpOptions,
    access_token: str,
) -> JsonObject:
    """Revoke one local bearer token without printing or persisting its.

    plaintext.

    Returns:
        A redacted revocation receipt.
    """
    oauth_store = RemoteMcpOAuthStore(
        client_store_path=_oauth_client_store_path(options),
        token_store_path=_oauth_token_store_path(options),
    )
    revoked = oauth_store.revoke_token(access_token)
    return {
        "status": "revoked" if revoked else "not_found",
        "revoked": revoked,
        "secrets_printed": False,
    }


def revoke_remote_mcp_client(
    options: RemoteMcpHttpOptions, client_id: str
) -> JsonObject:
    """Revoke one local OAuth client and its bearer-token hashes.

    Returns:
        A redacted client-revocation receipt.
    """
    oauth_store = RemoteMcpOAuthStore(
        client_store_path=_oauth_client_store_path(options),
        token_store_path=_oauth_token_store_path(options),
    )
    revoked = oauth_store.revoke_client(client_id)
    return {
        "status": "revoked" if revoked else "not_found",
        "revoked": revoked,
        "secrets_printed": False,
    }


def _start_knowledge_prewarm(repo_root: Path) -> None:
    """Start background Make knowledge-store preloading for low-latency tool.

    calls.
    """
    thread = Thread(
        target=_warm_knowledge_context, args=(repo_root,), daemon=True
    )
    thread.start()


def _validate_remote_mcp_http_options(options: RemoteMcpHttpOptions) -> None:
    """Validate remote MCP HTTP options before allocating runtime state.

    Raises:
        ValueError: If the host, public URL, or operator password is unsafe.
    """
    _validate_remote_mcp_http_host(options.host)
    _validate_remote_mcp_public_base_url(options.public_base_url)
    if _operator_password(options) is None:
        message = (
            "Remote MCP operator password is required. Configure "
            f"{REMOTE_MCP_OPERATOR_PASSWORD_ENV} locally before serving "
            f"remote MCP."
        )
        raise ValueError(message)


def _validate_remote_mcp_http_host(host: str) -> None:
    """Validate that the remote MCP HTTP origin stays on loopback.

    Raises:
    ValueError: If the configured bind host is outside the loopback boundary.
    """
    normalized_host = host.casefold().rstrip(".")
    if normalized_host == "localhost" or any(
        candidate.is_loopback
        for candidate in host_ip_candidates(normalized_host)
    ):
        return
    message = "Remote MCP HTTP host must be localhost or a loopback IP address."
    raise ValueError(message)


def _validate_remote_mcp_public_base_url(public_base_url: str) -> None:
    """Validate the public HTTPS origin used in OAuth metadata and challenges.

    Raises:
        ValueError: If the public base URL is unsafe for OAuth metadata.
    """
    if any(char.isspace() or char in {'"', "\\"} for char in public_base_url):
        message = "Remote MCP public base URL contains unsafe characters."
        raise ValueError(message)
    parsed = urlparse(public_base_url)
    if parsed.scheme.casefold() != "https":
        message = "Remote MCP public base URL must use https."
        raise ValueError(message)
    try:
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError as exc:
        message = "Remote MCP public base URL is malformed."
        raise ValueError(message) from exc
    if hostname is None:
        message = "Remote MCP public base URL must include a host."
        raise ValueError(message)
    if _is_non_public_base_url_host(hostname):
        message = "Remote MCP public base URL must use a public host."
        raise ValueError(message)
    if parsed.username is not None or parsed.password is not None:
        message = "Remote MCP public base URL must not include credentials."
        raise ValueError(message)
    if (
        parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        message = (
            "Remote MCP public base URL must be an origin without path or query"
            "parts."
        )
        raise ValueError(message)


def _is_non_public_base_url_host(hostname: str) -> bool:
    """Return if an advertised public OAuth origin uses a non-public host."""
    normalized = hostname.casefold().rstrip(".")
    if normalized == "localhost":
        return True
    return any(
        not candidate.is_global for candidate in host_ip_candidates(normalized)
    )


def _warm_knowledge_context(repo_root: Path) -> None:
    """Best-effort preload for the retained SQLite catalog search surface."""
    try:
        warm_catalog_snapshot(repo_root=repo_root)
    except (OSError, ValueError, sqlite3.Error):
        return


def _oauth_client_store_path(options: RemoteMcpHttpOptions) -> Path:
    """Return the OAuth client store path for this runtime."""
    return _oauth_state_path(
        options,
        configured_path=options.oauth_client_store_path,
        repo_default=DEFAULT_OAUTH_CLIENT_STORE_PATH,
        operator_default=DEFAULT_OPERATOR_OAUTH_CLIENT_STORE_PATH,
    )


def _oauth_token_store_path(options: RemoteMcpHttpOptions) -> Path:
    """Return the OAuth token store path for this runtime."""
    return _oauth_state_path(
        options,
        configured_path=options.oauth_token_store_path,
        repo_default=DEFAULT_OAUTH_TOKEN_STORE_PATH,
        operator_default=DEFAULT_OPERATOR_OAUTH_TOKEN_STORE_PATH,
    )


def _oauth_state_path(
    options: RemoteMcpHttpOptions,
    *,
    configured_path: Path | None,
    repo_default: Path,
    operator_default: Path,
) -> Path:
    """Return a configured, operator-root, or repo-confined OAuth state path."""
    if configured_path is not None:
        return resolve_repo_relative_path(options.repo_root, configured_path)
    operator_root = _schoenwald_operator_root(options.repo_root)
    if operator_root is not None:
        return _operator_data_path(operator_root, operator_default)
    return resolve_repo_relative_path(
        options.repo_root,
        repo_default,
    )


def _operator_data_path(operator_root: Path, relative_path: Path) -> Path:
    """Resolve a Schoenwald root data path without allowing path escapes.

    Returns:
        The resolved path under the operator root data namespace.

    Raises:
    ValueError: If the path is absolute or escapes the operator root data
    namespace.
    """
    if relative_path.is_absolute() or relative_path.drive:
        message = f"Operator data path must be relative: {relative_path}"
        raise ValueError(message)
    resolved_root = operator_root.resolve()
    data_root = (resolved_root / "data").resolve()
    resolved_path = (resolved_root / relative_path).resolve()
    if not resolved_path.is_relative_to(data_root):
        message = (
            f"Operator data path escapes the root data namespace:"
            f"{relative_path}"
        )
        raise ValueError(message)
    return resolved_path


def _operator_password(options: RemoteMcpHttpOptions) -> str | None:
    """Return the configured local operator password, if one is available."""
    explicit_password = _normalized_secret(options.operator_password)
    if explicit_password is not None:
        return explicit_password
    environment_password = _normalized_secret(
        os.environ.get(REMOTE_MCP_OPERATOR_PASSWORD_ENV)
    )
    if environment_password is not None:
        return environment_password
    for dotenv_path in _operator_password_dotenv_paths(options.repo_root):
        dotenv_password = _dotenv_secret(
            dotenv_path, REMOTE_MCP_OPERATOR_PASSWORD_ENV
        )
        if dotenv_password is not None:
            return dotenv_password
    return None


def _operator_password_dotenv_paths(repo_root: Path) -> tuple[Path, ...]:
    """Return local operator env files that may configure the remote MCP.

    password.
    """
    paths = [repo_root / ".env"]
    operator_root = _schoenwald_operator_root(repo_root)
    if operator_root is not None:
        operator_dotenv = operator_root / ".env"
        if operator_dotenv not in paths:
            paths.append(operator_dotenv)
    return tuple(paths)


def _schoenwald_operator_root(repo_root: Path) -> Path | None:
    """Return the Schoenwald operator root for a child repository, when.

    discoverable.
    """
    resolved_repo_root = repo_root.resolve()
    for candidate in (resolved_repo_root, *resolved_repo_root.parents):
        if (
            (candidate / "AGENTS.md").is_file()
            and (candidate / "commands").is_dir()
            and (candidate / "repos").is_dir()
        ):
            return candidate
    return None


def _normalized_secret(value: str | None) -> str | None:
    """Return a non-empty secret value stripped of common env-file quoting."""
    if value is None:
        return None
    stripped = value.strip().strip('"').strip("'")
    return stripped or None


def _dotenv_secret(path: Path, key: str) -> str | None:
    """Read one secret from a local .env file without exposing it in process.

    output.

    Returns:
        The secret value, or None when unavailable.
    """
    if not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    prefix = f"{key}="
    for line in lines:
        if line.startswith(prefix):
            return _normalized_secret(line.removeprefix(prefix))
    return None


def _load_oauth_clients(
    client_store_path: Path,
) -> dict[str, OAuthClientRecord]:
    """Load persisted dynamic OAuth client registrations.

    Returns:
        Valid persisted OAuth client records keyed by client id.
    """
    if not client_store_path.is_file():
        return {}
    try:
        payload = cast(
            "object", json.loads(client_store_path.read_text(encoding="utf-8"))
        )
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    payload_map = cast("Mapping[str, object]", payload)
    client_payloads = payload_map.get("clients")
    if not isinstance(client_payloads, list):
        return {}
    clients: dict[str, OAuthClientRecord] = {}
    now = _epoch_seconds()
    for client_payload in cast("list[object]", client_payloads):
        if not isinstance(client_payload, dict):
            continue
        client_map = cast("Mapping[str, object]", client_payload)
        client_id = _optional_text(client_map.get("client_id"))
        try:
            redirect_uris = _oauth_redirect_uri_tuple(
                client_map.get("redirect_uris")
            )
        except (TypeError, ValueError):
            continue
        issued_at = client_map.get("issued_at")
        if (
            client_id is None
            or not redirect_uris
            or not _valid_epoch_timestamp(issued_at)
        ):
            continue
        issued_at_value = cast("int", issued_at)
        if issued_at_value > now:
            continue
        clients[client_id] = OAuthClientRecord(
            client_id=client_id,
            redirect_uris=redirect_uris,
            issued_at=issued_at_value,
        )
    return clients


def _save_oauth_clients(
    client_store_path: Path,
    clients: Iterable[OAuthClientRecord],
) -> None:
    """Persist dynamic OAuth client registrations without auth codes or.

    tokens.
    """
    client_records = tuple(sorted(clients, key=lambda item: item.client_id))
    payload = {
        "schema_version": 1,
        "clients": [
            {
                "client_id": client.client_id,
                "redirect_uris": list(client.redirect_uris),
                "issued_at": client.issued_at,
            }
            for client in client_records
        ],
    }
    client_store_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = client_store_path.with_name(
        f"{client_store_path.name}.{secrets.token_hex(8)}.tmp"
    )
    _ = temp_path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _ = temp_path.replace(client_store_path)


def _load_oauth_tokens(token_store_path: Path) -> dict[str, OAuthTokenRecord]:
    """Load persisted bearer tokens from ignored local runtime state.

    Returns:
        Structurally valid OAuth bearer token records keyed by token hash.
    """
    if not token_store_path.is_file():
        return {}
    try:
        payload = cast(
            "object", json.loads(token_store_path.read_text(encoding="utf-8"))
        )
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    payload_map = cast("Mapping[str, object]", payload)
    token_payloads = payload_map.get("tokens")
    if not isinstance(token_payloads, list):
        return {}
    tokens: dict[str, OAuthTokenRecord] = {}
    now = _epoch_seconds()
    for token_payload in cast("list[object]", token_payloads):
        if not isinstance(token_payload, dict):
            continue
        token_map = cast("Mapping[str, object]", token_payload)
        record = _oauth_token_record(token_map=token_map, now=now)
        if record is None:
            continue
        tokens[record.access_token_hash] = record
    return tokens


def _oauth_token_record(
    *,
    token_map: Mapping[str, object],
    now: int,
) -> OAuthTokenRecord | None:
    """Return one trusted persisted token record, if the payload is valid."""
    access_token = _optional_text(token_map.get("access_token"))
    access_token_hash = _stored_oauth_token_hash(token_map)
    client_id = _optional_text(token_map.get("client_id"))
    issued_at = token_map.get("issued_at")
    expires_at = token_map.get("expires_at")
    if access_token_hash is None or client_id is None:
        return None
    if access_token is not None and not secrets.compare_digest(
        access_token_hash,
        _oauth_token_hash(access_token),
    ):
        return None
    if not _valid_epoch_timestamp(issued_at) or not _valid_epoch_timestamp(
        expires_at
    ):
        return None
    issued_at_value = cast("int", issued_at)
    expires_at_value = cast("int", expires_at)
    if issued_at_value > now or issued_at_value >= expires_at_value:
        return None
    scopes = _stored_oauth_scopes(token_map.get("scopes"))
    if scopes is None:
        return None
    return OAuthTokenRecord(
        access_token_hash=access_token_hash,
        client_id=client_id,
        issued_at=issued_at_value,
        expires_at=expires_at_value,
        scopes=scopes,
        access_token=access_token,
    )


def _stored_oauth_token_hash(token_map: Mapping[str, object]) -> str | None:
    """Return a persisted token hash or migrate one legacy plaintext token.

    value.
    """
    access_token_hash = _optional_text(token_map.get("access_token_sha256"))
    if access_token_hash is not None:
        normalized_hash = access_token_hash.casefold()
        return (
            normalized_hash
            if _valid_oauth_token_hash(normalized_hash)
            else None
        )
    legacy_access_token = _optional_text(token_map.get("access_token"))
    if legacy_access_token is None:
        return None
    return _oauth_token_hash(legacy_access_token)


def _oauth_token_hash(access_token: str) -> str:
    """Return the stable storage hash for one bearer token."""
    return hashlib.sha256(access_token.encode("utf-8")).hexdigest()


def _optional_sha256_text(value: str | None) -> str | None:
    """Return a redacted stable hash for optional audit identifiers."""
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _bounded_audit_text(value: str) -> str:
    """Return one bounded audit field without control characters."""
    normalized = " ".join(value.split())
    if len(normalized) <= AUTH_AUDIT_MAX_FIELD_CHARS:
        return normalized
    return normalized[:AUTH_AUDIT_MAX_FIELD_CHARS]


def _valid_oauth_token_hash(value: str) -> bool:
    """Return whether a stored token hash has the expected SHA-256 hex shape."""
    return len(value) == SHA256_HEX_LENGTH and all(
        character in "0123456789abcdef" for character in value
    )


def _stored_oauth_scopes(value: object) -> tuple[McpOauthScope, ...] | None:
    """Return the computed result for the caller."""
    if value is None:
        return OAUTH_SCOPES
    if not isinstance(value, list):
        return None
    if not value:
        return None
    try:
        return _oauth_scope_tuple(
            tuple(item for item in cast("list[object]", value))
        )
    except (TypeError, ValueError):
        return None


def _valid_epoch_timestamp(value: object) -> bool:
    """Return whether a stored JSON value is a usable epoch timestamp."""
    return not isinstance(value, bool) and isinstance(value, int)


def _save_oauth_tokens(
    token_store_path: Path,
    token_records: Iterable[OAuthTokenRecord],
) -> None:
    """Persist bearer token hashes to ignored local runtime state."""
    records = tuple(sorted(token_records, key=lambda item: item.issued_at))
    payload = {
        "schema_version": OAUTH_TOKEN_STORE_SCHEMA_VERSION,
        "tokens": [
            {
                "access_token_sha256": token.access_token_hash,
                "access_token": token.access_token,
                "client_id": token.client_id,
                "issued_at": token.issued_at,
                "expires_at": token.expires_at,
                "scopes": list(token.scopes),
            }
            for token in records
        ],
    }
    token_store_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = token_store_path.with_name(
        f"{token_store_path.name}.{secrets.token_hex(8)}.tmp"
    )
    _ = temp_path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _ = temp_path.replace(token_store_path)


def _hidden_input(name: str, value: str) -> str:
    """Return one escaped hidden input for the OAuth password form."""
    escaped_name = html.escape(name, quote=True)
    escaped_value = html.escape(value, quote=True)
    return (
        f'<input type="hidden" name="{escaped_name}" value="{escaped_value}">'
    )


def _tool_payload(tool: McpToolDefinition) -> JsonObject:
    """Return one MCP tool payload."""
    security_schemes = _oauth_security_schemes(tool)
    meta: JsonObject = {
        "securitySchemes": security_schemes,
        "openai/toolInvocation/invoking": _tool_invoking_text(tool),
        "openai/toolInvocation/invoked": _tool_invoked_text(tool),
    }
    payload: JsonObject = {
        "name": tool.name,
        "title": _tool_title(tool.name),
        "description": tool.description,
        "inputSchema": tool.input_schema(),
        "securitySchemes": security_schemes,
        "_meta": meta,
    }
    if tool.annotations is not None:
        payload["annotations"] = {
            "readOnlyHint": tool.annotations.read_only_hint,
            "destructiveHint": tool.annotations.destructive_hint,
            "idempotentHint": tool.annotations.idempotent_hint,
            "openWorldHint": tool.annotations.open_world_hint,
        }
        meta["pancakes/securityBoundary"] = _tool_security_boundary(tool)
    permission_copy = _tool_local_permission_copy(tool)
    if permission_copy:
        meta["pancakes/localPermissionCopy"] = permission_copy
    return payload


def tool_payload(tool: McpToolDefinition) -> JsonObject:
    """Return one MCP tool payload for contract tests."""
    return _tool_payload(tool)


def _resource_payload(resource: McpResourceDefinition) -> JsonObject:
    """Return one MCP resource descriptor payload."""
    return {
        "uri": resource.uri,
        "name": resource.name,
        "description": resource.description,
        "mimeType": resource.mime_type,
    }


def _prompt_payload(prompt: McpPromptDefinition) -> JsonObject:
    """Return one MCP prompt descriptor payload."""
    return {
        "name": prompt.name,
        "description": prompt.description,
    }


def _anonymous_mcp_method(method: str | None) -> bool:
    """Return whether an MCP method is safe to handle before OAuth linking."""
    return method in {
        "initialize",
        "notifications/initialized",
        "tools/list",
    }


def _path_is_well_known(path: str, prefix: str) -> bool:
    """Return whether an OAuth well-known route matches root or path-qualified.

    form.
    """
    return path == prefix or path.startswith(f"{prefix}/")


def _pkce_s256_matches(code_verifier: str | None, code_challenge: str) -> bool:
    """Return whether a PKCE S256 verifier matches the stored challenge."""
    if code_verifier is None:
        return False
    try:
        verifier_bytes = code_verifier.encode("ascii")
    except UnicodeEncodeError:
        return False
    digest = hashlib.sha256(verifier_bytes).digest()
    actual = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return secrets.compare_digest(actual, code_challenge)


def _pkce_authorization_error(
    code_challenge: str | None,
    code_challenge_method: str | None,
) -> str | None:
    """Return the PKCE authorization request error, if one exists."""
    if code_challenge is None:
        if code_challenge_method is not None:
            return "PKCE code_challenge_method requires code_challenge."
        return "PKCE S256 code_challenge is required."
    if code_challenge_method != "S256":
        return "Only PKCE S256 code challenges are supported."
    return None


def _oauth_security_schemes(tool: McpToolDefinition) -> list[JsonObject]:
    """Return no per-tool OAuth descriptors so MCP clients do not prompt."""
    del tool
    return []


def _token_has_scope(
    token_record: OAuthTokenRecord | None,
    required_scope: McpOauthScope,
) -> bool:
    """Return whether one token record carries the required MCP OAuth scope."""
    return token_record is not None and required_scope in token_record.scopes


def _tool_security_boundary(tool: McpToolDefinition) -> JsonObject:
    """Return Pancakes-specific tool boundary metadata."""
    annotations = tool.annotations
    if annotations is None:
        return {}
    return {
        "classification": annotations.classification,
        "localOnly": annotations.local_only,
        "providerApiCall": annotations.provider_api_call,
        "credentialValueTransfer": annotations.credential_value_transfer,
        "secretOutput": annotations.secret_output,
        "authorizationScope": OAUTH_READ_SCOPE
        if tool.read_only
        else OAUTH_WRITE_SCOPE,
    }


def _build_tool_list_result() -> JsonObject:
    """Return the static MCP tools/list response payload for this server.

    process.
    """
    return {"tools": [_tool_payload(tool) for tool in mcp_tool_registry()]}


def _build_tool_scope_by_name() -> dict[str, McpOauthScope]:
    """Return OAuth execution scopes keyed by MCP tool name."""
    return {
        tool.name: OAUTH_READ_SCOPE if tool.read_only else OAUTH_WRITE_SCOPE
        for tool in mcp_tool_registry()
    }


def _tool_local_permission_copy(tool: McpToolDefinition) -> JsonObject:
    """Return the computed result for the caller."""
    summary = LOCAL_ARTIFACT_PERMISSION_COPY.get(tool.name)
    annotations = tool.annotations
    if summary is None or annotations is None or not annotations.local_only:
        return {}
    return {
        "summary": summary,
        "surface": "local_artifact",
        "readOnlyHint": annotations.read_only_hint,
        "liveServiceCall": False,
        "valueTransfer": False,
        "secretOutput": False,
    }


def _tool_invoking_text(tool: McpToolDefinition) -> str:
    """Return compact invocation status text for one tool."""
    invoking_text = {
        "mcp.session.start": "Preparing local session intent",
        "catalog.index": "Reading local catalog indexes",
        "catalog.search": "Searching local catalog",
        "catalog.inspect": "Inspecting local catalog entity",
        "catalog.modify": "Preparing local catalog update",
        "catalog.node.modify": "Preparing local catalog node update",
        "catalog.edge.propose": "Preparing local catalog edge proposal",
        "catalog.edge.apply": "Preparing local catalog edge apply",
        "catalog.review.add": "Preparing local catalog review item",
        "project.search": "Searching local project metadata",
        "project.draft.stage": "Preparing local project draft stage",
        "project.draft.import": "Preparing local project artifact stage",
        "project.create": "Preparing local project creation",
        "project.health": "Reading local project health",
        "project.view": "Reading local project graph",
        "project.edit": "Preparing local project edit",
        "project.verify": "Verifying local project",
        "project.capabilities.inspect": "Inspecting local capability metadata",
        "project.make": "Preparing Make artifact preview",
        "project.package.inspect": "Inspecting local package section",
        "project.next": "Choosing next local project action",
        "project.modules.view": "Reading local project modules",
        "project.modules.add": "Preparing local module add",
        "project.modules.modify": "Preparing local module update",
        "project.modules.delete": "Preparing local module removal",
        "project.links.view": "Reading local project links",
        "project.filters.view": "Reading local project filters",
        "project.filters.add": "Preparing local filter add",
        "project.filters.modify": "Preparing local filter update",
        "project.filters.delete": "Preparing local filter removal",
        "project.error_handlers.view": "Reading local error handlers",
        "project.error_handlers.add": "Preparing local error-handler add",
        "project.error_handlers.modify": "Preparing local error-handler update",
        "project.error_handlers.delete": (
            "Preparing local error-handler removal"
        ),
        "linter.quarantine.write": "Writing linter quarantine record",
        "linter.rule.next": "Leasing local linter rule candidate",
        "linter.rule.inspect": "Inspecting local linter rule candidate",
        "linter.rule.implement": "Validating local linter rule implementation",
        "linter.rule.merge_canonical": "Preparing local linter canonical merge",
        "linter.rule.reject_invalid": (
            "Preparing local linter invalid rejection"
        ),
        "linter.rule.edit": "Validating local linter rule edit",
        "linter.rule.status": "Reading local linter rule editor status",
        "linter.rule.rollback": "Preparing local linter rule rollback",
        "backlog.add": "Recording local backlog item",
        "backlog.list": "Reading local backlog",
        "backlog.end": "Closing local backlog item",
    }.get(tool.name)
    if invoking_text is not None:
        return invoking_text
    return "Reading Make data" if tool.read_only else "Writing local MCP data"


def _tool_invoked_text(tool: McpToolDefinition) -> str:
    """Return compact completion status text for one tool."""
    invoked_text = {
        "mcp.session.start": "Local session intent prepared",
        "catalog.index": "Local catalog indexes read",
        "catalog.search": "Local catalog searched",
        "catalog.inspect": "Local catalog entity inspected",
        "catalog.modify": "Local catalog state updated",
        "catalog.node.modify": "Local catalog node updated",
        "catalog.edge.propose": "Local catalog edge proposal recorded",
        "catalog.edge.apply": "Local catalog edge applied",
        "catalog.review.add": "Local catalog review item recorded",
        "project.search": "Local project metadata searched",
        "project.draft.stage": "Local project draft stage prepared",
        "project.draft.import": "Local project artifact stage prepared",
        "project.create": "Local project creation prepared",
        "project.health": "Local project health read",
        "project.view": "Local project graph read",
        "project.edit": "Local project edit prepared",
        "project.verify": "Local project verified",
        "project.capabilities.inspect": "Local capability metadata inspected",
        "project.make": "Make artifact preview prepared",
        "project.package.inspect": "Local package section inspected",
        "project.next": "Next local project action selected",
        "project.modules.view": "Local project modules read",
        "project.modules.add": "Local module add prepared",
        "project.modules.modify": "Local module update prepared",
        "project.modules.delete": "Local module removal prepared",
        "project.links.view": "Local project links read",
        "project.filters.view": "Local project filters read",
        "project.filters.add": "Local filter add prepared",
        "project.filters.modify": "Local filter update prepared",
        "project.filters.delete": "Local filter removal prepared",
        "project.error_handlers.view": "Local error handlers read",
        "project.error_handlers.add": "Local error-handler add prepared",
        "project.error_handlers.modify": "Local error-handler update prepared",
        "project.error_handlers.delete": "Local error-handler removal prepared",
        "linter.quarantine.write": "Linter quarantine record written",
        "linter.rule.next": "Local linter rule candidate leased",
        "linter.rule.inspect": "Local linter rule candidate inspected",
        "linter.rule.implement": "Local linter rule implementation validated",
        "linter.rule.merge_canonical": "Local linter canonical merge prepared",
        "linter.rule.reject_invalid": "Local linter invalid rejection prepared",
        "linter.rule.edit": "Local linter rule edit validated",
        "linter.rule.status": "Local linter rule editor status read",
        "linter.rule.rollback": "Local linter rule rollback prepared",
        "backlog.add": "Local backlog item recorded",
        "backlog.list": "Local backlog read",
        "backlog.end": "Local backlog item closed",
    }.get(tool.name)
    if invoked_text is not None:
        return invoked_text
    return "Read complete" if tool.read_only else "Local MCP data written"


def _scope_required_result(
    challenge: str, required_scope: McpOauthScope
) -> JsonObject:
    """Return a tool-level MCP OAuth challenge for insufficient scopes."""
    return {
        "content": [
            {
                "type": "text",
                "text": f"Authorization scope required: {required_scope}.",
            }
        ],
        "_meta": {
            "mcp/www_authenticate": [challenge],
            "mcp/error_code": "oauth_insufficient_scope",
            "mcp/required_scope": required_scope,
        },
        "isError": True,
    }


def _oauth_error(
    error: str, error_code: str, *, detail: str | None = None
) -> JsonObject:
    """Return one stable OAuth HTTP error payload."""
    payload: JsonObject = {"error": error, "error_code": error_code}
    if detail is not None:
        payload["detail"] = detail
    return payload


def _oauth_authorization_error_code(error: str) -> str:
    """Return a stable OAuth authorization error code for one message."""
    if error == "Unknown OAuth client.":
        return "oauth_client_unknown"
    if error == "Redirect URI is not registered for this OAuth client.":
        return "oauth_redirect_uri_mismatch"
    return "oauth_authorization_request_invalid"


def _oauth_token_error_code(error: str) -> str:
    """Return a stable OAuth token endpoint error code for one message."""
    if error == "Expired OAuth authorization code.":
        return "oauth_code_expired"
    if error == "Invalid OAuth PKCE verifier.":
        return "oauth_pkce_verifier_invalid"
    return "oauth_code_invalid"


def _www_authenticate_challenge(
    public_base_url: str,
    *,
    scope: str = OAUTH_SCOPE,
    error_description: str = "You need to login to continue",
) -> str:
    """Return the bearer challenge ChatGPT uses to trigger OAuth linking."""
    return (
        'Bearer resource_metadata="'
        f"{public_base_url}/.well-known/oauth-protected-resource"
        f'", scope="{scope}", error="insufficient_scope", '
        f'error_description="{error_description}"'
    )


def _tool_title(tool_name: str) -> str:
    """Return a compact display title for one MCP tool."""
    titles = {
        "mcp.session.start": "Start Local Session",
        "catalog.index": "Read Catalog Index",
        "catalog.search": "Search Local Catalog",
        "catalog.inspect": "Inspect Local Catalog",
        "catalog.modify": "Modify Local Catalog",
        "catalog.node.modify": "Modify Catalog Node",
        "catalog.edge.propose": "Propose Catalog Edge",
        "catalog.edge.apply": "Apply Catalog Edge",
        "catalog.review.add": "Add Catalog Review",
        "project.search": "Search Local Projects",
        "project.draft.stage": "Stage Local Project Draft",
        "project.draft.import": "Stage Local Project Artifact",
        "project.create": "Create Local Project",
        "project.health": "Read Local Project Health",
        "project.view": "View Local Project Graph",
        "project.edit": "Edit Local Project",
        "project.verify": "Verify Local Project",
        "project.capabilities.inspect": "Inspect Local Capabilities",
        "project.make": "Preview Make Artifact",
        "project.package.inspect": "Inspect Package Section",
        "project.next": "Select Next Project Action",
        "project.modules.view": "View Local Modules",
        "project.modules.add": "Add Local Module",
        "project.modules.modify": "Modify Local Module",
        "project.modules.delete": "Preview Module Removal",
        "project.links.view": "View Local Links",
        "project.filters.view": "View Local Filters",
        "project.filters.add": "Add Local Filter",
        "project.filters.modify": "Modify Local Filter",
        "project.filters.delete": "Preview Filter Removal",
        "project.error_handlers.view": "View Local Error Handlers",
        "project.error_handlers.add": "Add Local Error Handler",
        "project.error_handlers.modify": "Modify Local Error Handler",
        "project.error_handlers.delete": "Preview Error Handler Removal",
        "backlog.add": "Record Local Backlog Item",
        "backlog.list": "Read Local Backlog",
        "backlog.end": "Close Local Backlog Item",
    }
    if tool_name in titles:
        return titles[tool_name]
    return tool_name.replace(".", " ").replace("_", " ").title()


def _json_rpc_result(request_id: object, result: JsonObject) -> JsonObject:
    """Return one JSON-RPC success response."""
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _json_rpc_error(request_id: object, code: int, message: str) -> JsonObject:
    """Return one JSON-RPC error response."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _first_query_value(
    query: Mapping[str, list[str]],
    key: str,
    *,
    trim: bool = True,
) -> str | None:
    """Return one query/form value."""
    values = query.get(key)
    if not values:
        return None
    value = values[0].strip() if trim else values[0]
    return value or None


def _requested_oauth_scopes(
    scope_text: str | None,
) -> tuple[McpOauthScope, ...]:
    """Return the computed result for the caller."""
    if scope_text is None:
        return OAUTH_SCOPES
    return _oauth_scope_tuple(tuple(scope_text.split()))


def _oauth_scope_tuple(values: tuple[object, ...]) -> tuple[McpOauthScope, ...]:
    """Return a deterministic non-empty supported OAuth scope tuple.

    Raises:
        TypeError: When a scope value is not a string.
        ValueError: When a scope value is not supported.
    """
    scopes: list[McpOauthScope] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            message = OAUTH_UNSUPPORTED_SCOPE_ERROR
            raise TypeError(message)
        scope = value.strip()
        if not scope:
            continue
        if scope not in OAUTH_SCOPES:
            message = OAUTH_UNSUPPORTED_SCOPE_ERROR
            raise ValueError(message)
        if scope in seen:
            continue
        seen.add(scope)
        scopes.append(scope)
    return tuple(scopes) or OAUTH_SCOPES


def _oauth_scope_text(scopes: tuple[McpOauthScope, ...]) -> str:
    """Return one space-delimited OAuth scope string."""
    return " ".join(scopes)


def _oauth_redirect_uri_tuple(value: object) -> tuple[str, ...]:
    """Return validated OAuth redirect URIs from a JSON member.

    Raises:
        TypeError: If any redirect URI entry is not a string.
    """
    if not isinstance(value, list):
        return ()
    redirect_uris: list[str] = []
    for item in cast("list[object]", value):
        if not isinstance(item, str):
            message = "Redirect URI entries must be strings."
            raise TypeError(message)
        redirect_uri = item.strip()
        _validate_oauth_redirect_uri(redirect_uri)
        redirect_uris.append(redirect_uri)
    return tuple(redirect_uris)


def _validate_oauth_redirect_uri(redirect_uri: str) -> None:
    """Validate one OAuth redirect URI before it can receive authorization.

    codes.

    Raises:
    ValueError: If the redirect URI is not approved for the local MCP OAuth
    flow.
    """
    if not redirect_uri:
        message = "Redirect URI must not be empty."
        raise ValueError(message)
    if any(char.isspace() or char in {'"', "\\"} for char in redirect_uri):
        message = "Redirect URI contains unsafe characters."
        raise ValueError(message)
    if "*" in redirect_uri:
        message = "Redirect URI must not contain wildcards."
        raise ValueError(message)
    parsed = urlparse(redirect_uri)
    scheme = parsed.scheme.casefold()
    if not scheme:
        message = "Redirect URI must be absolute."
        raise ValueError(message)
    hostname = _redirect_uri_hostname(parsed)
    if parsed.username is not None or parsed.password is not None:
        message = "Redirect URI must not include credentials."
        raise ValueError(message)
    if parsed.fragment:
        message = "Redirect URI must not include a fragment."
        raise ValueError(message)
    _validate_oauth_redirect_scheme(
        parsed=parsed,
        redirect_uri=redirect_uri,
        scheme=scheme,
        hostname=hostname,
    )


def _validate_oauth_redirect_scheme(
    *,
    parsed: ParseResult,
    redirect_uri: str,
    scheme: str,
    hostname: str | None,
) -> None:
    """Validate an OAuth redirect URI scheme.

    Raises:
        ValueError: If the URI scheme or scheme-specific authority is unsafe.
    """
    if scheme == "https":
        _require_redirect_uri_host(hostname)
        if _is_approved_oauth_https_redirect(
            parsed=parsed,
            redirect_uri=redirect_uri,
            hostname=hostname,
        ) or _is_loopback_redirect_host(hostname):
            return
        message = "HTTPS redirect URI host is not approved for this OAuth flow."
        raise ValueError(message)
    if scheme == "http":
        _require_redirect_uri_host(hostname)
        if _is_loopback_redirect_host(hostname):
            return
        message = "HTTP redirect URI must use localhost or a loopback IP."
        raise ValueError(message)
    if scheme in APPROVED_OAUTH_CUSTOM_REDIRECT_SCHEMES:
        if parsed.netloc or parsed.path:
            return
        message = "Custom-scheme redirect URI must include a callback target."
        raise ValueError(message)
    message = "Redirect URI scheme is not allowed."
    raise ValueError(message)


def _is_approved_oauth_https_redirect(
    *,
    parsed: ParseResult,
    redirect_uri: str,
    hostname: str | None,
) -> bool:
    """Return if an HTTPS redirect is owned by an approved OAuth client host."""
    if redirect_uri in APPROVED_OAUTH_HTTPS_REDIRECT_URIS:
        return True
    if hostname is None:
        return False
    normalized_hostname = hostname.rstrip(".").casefold()
    return (
        normalized_hostname in APPROVED_OAUTH_HTTPS_REDIRECT_HOSTS
        and bool(parsed.path)
        and parsed.path != "/"
    )


def _redirect_uri_hostname(parsed: ParseResult) -> str | None:
    """Return the parsed hostname, validating malformed authorities and ports.

    Raises:
        ValueError: If the URI authority or port is malformed.
    """
    try:
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError as exc:
        message = "Redirect URI is malformed."
        raise ValueError(message) from exc
    return hostname


def _require_redirect_uri_host(hostname: str | None) -> None:
    """Require a URI host for HTTP-family redirect URIs.

    Raises:
        ValueError: If the URI does not include a host.
    """
    if hostname is None:
        message = "Redirect URI must include a host."
        raise ValueError(message)


def _is_loopback_redirect_host(hostname: str | None) -> bool:
    """Return whether a redirect URI host is localhost or a loopback IP."""
    if hostname is None:
        return False
    normalized = hostname.casefold().rstrip(".")
    if normalized == "localhost":
        return True
    return any(
        candidate.is_loopback for candidate in host_ip_candidates(normalized)
    )


def _required_text(payload: Mapping[str, object], key: str) -> str:
    """Return one required text member.

    Raises:
        ValueError: If the required text is absent or blank.
    """
    value = _optional_text(payload.get(key))
    if value is None:
        message = f"Missing required MCP parameter: {key}"
        raise ValueError(message)
    return value


def _optional_text(value: object) -> str | None:
    """Return text when the value is a non-blank string."""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _object_or_empty(value: object) -> JsonObject:
    """Return an object value or an empty object.

    Raises:
        TypeError: If the provided value is not a JSON object.
    """
    if value is None:
        return {}
    if not isinstance(value, dict):
        message = "Expected an object value."
        raise TypeError(message)
    return {
        str(key): item
        for key, item in cast("Mapping[object, object]", value).items()
    }


def _epoch_seconds() -> int:
    """Return current Unix time in seconds."""
    return int(time.time())
