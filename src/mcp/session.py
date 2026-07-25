# ruff: noqa: S105
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001055#repo.mcp.required-tool-surface
# - 001067#repo.mcp.client-routing.one-time-auth-session-posture
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Local MCP session intent receipts.

Boundary contract:
- Owns: local MCP session-intent receipts for typed local Make scenario tools.
- Must not: grant live provider access, read credentials, persist secrets, or
bypass tool guards.
- Allows: process-local session scope markers and validation metadata for safe
local flows.
- Split when: durable multi-process session storage becomes required.
- Merge when: another MCP module owns local session intent validation.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import TYPE_CHECKING, Final, NamedTuple, cast

if TYPE_CHECKING:
    from mcp.models import JsonObject

MCP_SESSION_START_TOOL = "mcp.session.start"
SESSION_TOKEN_PREFIX: Final = "mcp-session:"
DEFAULT_SESSION_TTL_SECONDS: Final = 4 * 60 * 60
MAX_SESSION_TEXT_CHARS: Final = 280
LOCAL_WRITE_SURFACE_ALIASES: Final[frozenset[str]] = frozenset(
    (
        "catalog.local ",
        "project.local ",
        "project.modules ",
        "project.filters ",
        "project.error_handlers ",
        "project.package ",
        "documentation.local ",
        "linter.local ",
        "backlog.local",
    )
)


class McpSessionRecord(NamedTuple):
    """One process-local MCP session intent record."""

    session_intent_id: str
    session_token: str
    worker_id: str
    allowed_local_write_surfaces: tuple[str, ...]
    approved_scope: JsonObject
    expires_at: str
    expires_epoch: int


_SESSION_LOCK = Lock()
_SESSIONS_BY_TOKEN: dict[str, McpSessionRecord] = {}


def start_mcp_session(
    arguments: Mapping[str, object], repo_root: object
) -> JsonObject:
    """Return a process-local session intent receipt without filesystem or.

    SQLite writes.
    """
    del repo_root
    operator_intent = _required_text(arguments, "operator_intent")
    worker_id = _required_text(arguments, "worker_id")
    allowed_surfaces = _allowed_local_write_surfaces(
        arguments.get("allowed_local_write_surfaces")
    )
    approved_scope = _approved_scope(
        arguments.get("approved_scope"), allowed_surfaces
    )
    expires_at, expires_epoch = _session_expiry(arguments.get("expires_at"))
    session_intent_id = _session_intent_id(
        arguments.get("session_intent_id"),
        operator_intent=operator_intent,
        worker_id=worker_id,
        allowed_surfaces=allowed_surfaces,
        expires_at=expires_at,
    )
    session_token = _session_token(
        session_intent_id=session_intent_id,
        worker_id=worker_id,
        allowed_surfaces=allowed_surfaces,
        expires_at=expires_at,
    )
    record = McpSessionRecord(
        session_intent_id=session_intent_id,
        session_token=session_token,
        worker_id=worker_id,
        allowed_local_write_surfaces=allowed_surfaces,
        approved_scope=approved_scope,
        expires_at=expires_at,
        expires_epoch=expires_epoch,
    )
    with _SESSION_LOCK:
        _SESSIONS_BY_TOKEN[session_token] = record
    return {
        "status": "ok",
        "session_intent_id": session_intent_id,
        "session_token": session_token,
        "worker_id": worker_id,
        "allowed_local_write_surfaces": allowed_surfaces,
        "approved_scope": approved_scope,
        "expires_at": expires_at,
        "session_scope_status": "active ",
        "session_persistence": "process_local_memory_only ",
        "session_security_model": "intent_marker_not_provider_authorization",
        "local_write_session_scoped": True,
        "requires_operator_approval": False,
        "writes_performed": False,
        "write_actions": [],
        "provider_api_call": False,
        "live_make_called": False,
        "credential_value_transfer": False,
        "secret_output": False,
    }


def session_scope_metadata(
    *,
    tool_name: str,
    arguments: Mapping[str, object],
) -> JsonObject:
    """Return validated session metadata for one tool call, or an empty payload.

    Raises:
        ValueError: If the supplied session metadata is stale, mismatched, or
        out of scope.
    """
    session_token = _optional_text(arguments.get("session_token"))
    session_intent_id = _optional_text(arguments.get("session_intent_id"))
    if session_token is None and session_intent_id is None:
        return {}
    if session_token is None:
        message = "missing_required_field: session_token"
        raise ValueError(message)
    with _SESSION_LOCK:
        record = _SESSIONS_BY_TOKEN.get(session_token)
    if record is None:
        message = "session_token_unknown_or_expired"
        raise ValueError(message)
    if (
        session_intent_id is not None
        and session_intent_id != record.session_intent_id
    ):
        message = "session_intent_id_mismatch"
        raise ValueError(message)
    if int(time.time()) >= record.expires_epoch:
        with _SESSION_LOCK:
            _ = _SESSIONS_BY_TOKEN.pop(session_token, None)
        message = "session_token_expired"
        raise ValueError(message)
    worker_id = _optional_text(arguments.get("worker_id"))
    if worker_id is not None and worker_id != record.worker_id:
        message = "session_worker_id_mismatch"
        raise ValueError(message)
    if not _surface_allows_tool(
        tool_name=tool_name,
        allowed_surfaces=record.allowed_local_write_surfaces,
    ):
        message = "session_scope_does_not_allow_tool"
        raise ValueError(message)
    return {
        "session_intent_id": record.session_intent_id,
        "session_scope_validated": True,
        "session_scope_expires_at": record.expires_at,
        "approved_scope": record.approved_scope,
    }


def _session_intent_id(
    value: object,
    *,
    operator_intent: str,
    worker_id: str,
    allowed_surfaces: tuple[str, ...],
    expires_at: str,
) -> str:
    existing = _optional_text(value)
    if existing is not None:
        return existing
    digest = _digest(
        {
            "operator_intent": operator_intent,
            "worker_id": worker_id,
            "allowed_surfaces": allowed_surfaces,
            "expires_at": expires_at,
        }
    )
    return f"mcp-session-{digest[:16]}"


def _session_token(
    *,
    session_intent_id: str,
    worker_id: str,
    allowed_surfaces: tuple[str, ...],
    expires_at: str,
) -> str:
    digest = _digest(
        {
            "session_intent_id": session_intent_id,
            "worker_id": worker_id,
            "allowed_surfaces": allowed_surfaces,
            "expires_at": expires_at,
        }
    )
    return f"{SESSION_TOKEN_PREFIX}{digest[:32]}"


def _digest(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _allowed_local_write_surfaces(value: object) -> tuple[str, ...]:
    if value is None:
        return tuple(sorted(LOCAL_WRITE_SURFACE_ALIASES))
    if isinstance(value, str):
        items = tuple(item.strip() for item in value.split(",") if item.strip())
    elif isinstance(value, list | tuple):
        sequence = cast("list[object] | tuple[object, ...]", value)
        items = tuple(_required_surface_text(item) for item in sequence)
    elif isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        items = tuple(
            str(key) for key, enabled in mapping.items() if enabled is True
        )
    else:
        message = (
            "allowed_local_write_surfaces must be a string, array, or object."
        )
        raise TypeError(message)
    normalized = tuple(
        sorted(frozenset(_normalize_surface(item) for item in items))
    )
    if not normalized:
        message = "allowed_local_write_surfaces must not be empty."
        raise ValueError(message)
    return normalized


def _approved_scope(
    value: object, allowed_surfaces: tuple[str, ...]
) -> JsonObject:
    if value is None:
        return {
            "scope_kind": "local_pancakes_workspace",
            "allowed_local_write_surfaces": allowed_surfaces,
            "provider_api_call": False,
            "live_make_called": False,
        }
    if not isinstance(value, Mapping):
        message = "approved_scope must be a JSON object."
        raise TypeError(message)
    return dict(cast("Mapping[str, object]", value))


def _session_expiry(value: object) -> tuple[str, int]:
    text = _optional_text(value)
    if text is None:
        expires = datetime.now(tz=UTC) + timedelta(
            seconds=DEFAULT_SESSION_TTL_SECONDS
        )
        return expires.isoformat().replace("+00:00", "Z"), int(
            expires.timestamp()
        )
    normalized = text.replace("Z", "+00:00")
    try:
        expires = datetime.fromisoformat(normalized)
    except ValueError as exc:
        message = "expires_at must be an ISO-8601 datetime."
        raise ValueError(message) from exc
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    expires_utc = expires.astimezone(UTC)
    expires_epoch = int(expires_utc.timestamp())
    if expires_epoch <= int(time.time()):
        message = "expires_at must be in the future."
        raise ValueError(message)
    return expires_utc.isoformat().replace("+00:00", "Z"), expires_epoch


def _surface_allows_tool(
    *, tool_name: str, allowed_surfaces: tuple[str, ...]
) -> bool:
    if "*" in allowed_surfaces or tool_name in allowed_surfaces:
        return True
    allowed_prefixes = tuple(
        surface[:-2] for surface in allowed_surfaces if surface.endswith(".*")
    )
    if any(tool_name.startswith(prefix) for prefix in allowed_prefixes):
        return True
    aliases = {
        "catalog.local": "catalog.",
        "project.local": "project.",
        "project.modules": "project.modules.",
        "project.filters": "project.filters.",
        "project.error_handlers": "project.error_handlers.",
        "project.package": "project.make ",
        "documentation.local": "documentation.",
        "linter.local": "linter.",
        "backlog.local": "backlog.",
    }
    return any(
        tool_name.startswith(prefix)
        if prefix.endswith(".")
        else tool_name == prefix
        for surface, prefix in aliases.items()
        if surface in allowed_surfaces
    )


def _normalize_surface(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        message = "allowed_local_write_surfaces cannot contain empty values."
        raise ValueError(message)
    if len(normalized) > MAX_SESSION_TEXT_CHARS:
        message = "allowed_local_write_surfaces value is too long."
        raise ValueError(message)
    return normalized


def _required_surface_text(value: object) -> str:
    if not isinstance(value, str):
        message = "allowed_local_write_surfaces entries must be strings."
        raise TypeError(message)
    return value


def _required_text(arguments: Mapping[str, object], key: str) -> str:
    text = _optional_text(arguments.get(key))
    if text is None:
        message = f"missing_required_field: {key}"
        raise ValueError(message)
    return text


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        message = "Text arguments must be strings."
        raise TypeError(message)
    text = " ".join(value.split())
    if not text:
        return None
    if len(text) > MAX_SESSION_TEXT_CHARS:
        message = "Text argument is too long."
        raise ValueError(message)
    return text
