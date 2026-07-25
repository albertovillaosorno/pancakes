# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001064#repo.make-knowledge.structural-ssot
# - 001055#repo.mcp.required-tool-surface
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""SQLite-backed MCP backlog tools.

Boundary contract:
- Owns: MCP backlog add, list, and end operations against the Make knowledge
SQLite SSOT.
- Must not: author catalog semantic answers, create JSON ledgers, or call
providers.
- Allows: compact local backlog partitions for catalog, linter, quarantine,
projects, and service
  update work.
- Split when: a backlog domain gains its own workflow state machine.
- Merge when: another module writes the same mcp_backlog_entries table.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, cast

from catalog.knowledge import (
    DEFAULT_KNOWLEDGE_DB_PATH,
    build_knowledge_store,
    connect_catalog_plan_ssot,
    knowledge_store_status,
)
from languages.make.raw_specs.paths import resolve_repo_relative_path

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from catalog.knowledge import KnowledgeStoreStatusReport

    from mcp.models import JsonObject

BACKLOG_TABLE_NAME: Final = "mcp_backlog_entries"
DEFAULT_BACKLOG_LIMIT: Final = 20
MAX_BACKLOG_LIMIT: Final = 100
DEFAULT_BACKLOG_PRIORITY: Final = 100
MIN_BACKLOG_PRIORITY: Final = 0
MAX_BACKLOG_PRIORITY: Final = 1000
MAX_BACKLOG_TITLE_LENGTH: Final = 240
MAX_BACKLOG_TEXT_LENGTH: Final = 512
GENERATED_ENTRY_ID_HEX_LENGTH: Final = 16
GENERATED_ENTRY_ID_PREFIX: Final = "mcp-backlog"
VALID_BACKLOG_DOMAINS: Final[frozenset[str]] = frozenset(
    (
        "catalog ",
        "linter ",
        "projects ",
        "quarantine ",
        "windows-service",
    )
)
BACKLOG_DOMAIN_ALIASES: Final[dict[str, str]] = {
    "project": "projects ",
    "windows_service": "windows-service ",
    "windowsservice": "windows-service ",
    "windows service": "windows-service",
}
VALID_BACKLOG_STATUSES: Final[frozenset[str]] = frozenset(("open", "ended"))
VALID_BACKLOG_LIST_STATUSES: Final[frozenset[str]] = frozenset(
    ("all", *VALID_BACKLOG_STATUSES)
)
REBUILDABLE_KNOWLEDGE_STATUSES: Final[frozenset[str]] = frozenset(
    (
        "empty_database ",
        "missing_database",
    )
)
BACKLOG_SCHEMA_SQL: Final = """
CREATE TABLE IF NOT EXISTS mcp_backlog_entries (
  entry_id TEXT PRIMARY KEY,
  domain TEXT NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  priority INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mcp_backlog_entries_status
  ON mcp_backlog_entries (status, priority, domain);

CREATE INDEX IF NOT EXISTS idx_mcp_backlog_entries_priority_updated
  ON mcp_backlog_entries (priority, updated_at_utc, entry_id);

CREATE INDEX IF NOT EXISTS idx_mcp_backlog_entries_domain_status_priority
  ON mcp_backlog_entries (domain, status, priority, updated_at_utc, entry_id);
"""


def add_backlog_entry(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Add or reopen one MCP backlog entry in the SQLite SSOT.

    Returns:
        A compact write receipt for the backlog entry.
    """
    domain = _backlog_domain(_required_text(arguments, "domain"))
    title = _bounded_text(
        _required_text(arguments, "title"), field_name="title"
    )
    payload = _optional_payload(arguments)
    priority = _priority(arguments.get("priority"))
    source_kind = _bounded_text(
        _optional_text(arguments.get("source_kind")) or "mcp",
        field_name="source_kind",
    )
    source_ref = _bounded_text(
        _optional_text(arguments.get("source_ref")) or "backlog.add",
        field_name="source_ref",
    )
    entry_id = _entry_id(
        explicit_entry_id=_optional_text(arguments.get("entry_id")),
        fingerprint_source=(domain, title, payload, source_kind, source_ref),
    )
    payload_json = _canonical_json(payload)
    observed_at_utc = _utc_now()
    status = _ensure_backlog_database(repo_root)
    connection = connect_catalog_plan_ssot(repo_root=repo_root)
    try:
        with connection:
            existing_created_at = _existing_created_at(connection, entry_id)
            created_at_utc = existing_created_at or observed_at_utc
            _ = connection.execute(
                """
                INSERT INTO mcp_backlog_entries (
                  entry_id, domain, title, status, priority, payload_json,
                  source_kind,
                  source_ref, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entry_id) DO UPDATE SET
                  domain = excluded.domain,
                  title = excluded.title,
                  status = excluded.status,
                  priority = excluded.priority,
                  payload_json = excluded.payload_json,
                  source_kind = excluded.source_kind,
                  source_ref = excluded.source_ref,
                  updated_at_utc = excluded.updated_at_utc
                """,
                (
                    entry_id,
                    domain,
                    title,
                    "open",
                    priority,
                    payload_json,
                    source_kind,
                    source_ref,
                    created_at_utc,
                    observed_at_utc,
                ),
            )
    finally:
        connection.close()
    return {
        "status": "recorded",
        "entry_id": entry_id,
        "domain": domain,
        "entry_status": "open",
        "priority": priority,
        "database_path": status.database_path,
        "sqlite_ssot": True,
        "provider_api_call": False,
        "live_make_called": False,
        "payload_sha256": _sha256_text(payload_json),
    }


def list_backlog_entries(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """List compact MCP backlog entries from the SQLite SSOT.

    Returns:
        Counts first, then bounded entry details.
    """
    domain = _optional_backlog_domain(arguments.get("domain"))
    requested_status = _list_status(arguments.get("status"))
    limit = _limit(arguments.get("limit"))
    include_payload = _optional_bool(
        arguments.get("include_payload"), default=False
    )
    status = _ensure_backlog_database(repo_root)
    connection = connect_catalog_plan_ssot(repo_root=repo_root)
    try:
        counts = _backlog_counts(
            connection=connection, domain=domain, status=requested_status
        )
        entries = _backlog_entries(
            connection=connection,
            domain=domain,
            status=requested_status,
            limit=limit,
            include_payload=include_payload,
        )
    finally:
        connection.close()
    hidden_entry_count = max(
        _json_int(counts, "matching_total") - len(entries), 0
    )
    return {
        "status": "ok",
        "database_path": status.database_path,
        "sqlite_ssot": True,
        "provider_api_call": False,
        "live_make_called": False,
        "filters": {
            "domain": domain,
            "status": requested_status,
            "limit": limit,
            "include_payload": include_payload,
        },
        "counts": counts,
        "shown_entry_count": len(entries),
        "hidden_entry_count": hidden_entry_count,
        "entries": entries,
    }


def end_backlog_entry(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Close one MCP backlog entry in the SQLite SSOT.

    Returns:
        A compact closure receipt for the backlog entry.

    Raises:
        ValueError: If the entry id does not exist.
    """
    entry_id = _safe_entry_id(_required_text(arguments, "entry_id"))
    resolution = _bounded_text(
        _optional_text(arguments.get("resolution")) or "Closed by backlog.end.",
        field_name="resolution",
    )
    source_ref = _bounded_text(
        _optional_text(arguments.get("source_ref")) or "backlog.end",
        field_name="source_ref",
    )
    observed_at_utc = _utc_now()
    status = _ensure_backlog_database(repo_root)
    connection = connect_catalog_plan_ssot(repo_root=repo_root)
    try:
        with connection:
            row = cast(
                "Sequence[object] | None",
                connection.execute(
                    """
                    SELECT payload_json
                    FROM mcp_backlog_entries
                    WHERE entry_id = ?
                    """,
                    (entry_id,),
                ).fetchone(),
            )
            if row is None:
                message = f"Unknown backlog entry: {entry_id}"
                raise ValueError(message)
            payload = _payload_from_row(row[0])
            payload["resolution"] = {
                "summary": resolution,
                "source_ref": source_ref,
                "ended_at_utc": observed_at_utc,
            }
            _ = connection.execute(
                """
                UPDATE mcp_backlog_entries
                SET status = ?, payload_json = ?, source_ref = ?, updated_at_utc
                = ?
                WHERE entry_id = ?
                """,
                (
                    "ended",
                    _canonical_json(payload),
                    source_ref,
                    observed_at_utc,
                    entry_id,
                ),
            )
    finally:
        connection.close()
    return {
        "status": "ended",
        "entry_id": entry_id,
        "database_path": status.database_path,
        "sqlite_ssot": True,
        "provider_api_call": False,
        "live_make_called": False,
        "ended_at_utc": observed_at_utc,
    }


def _ensure_backlog_database(repo_root: Path) -> KnowledgeStoreStatusReport:
    """Ensure a backlog-capable SQLite database exists without destructive.

    rebuilds.

    Returns:
        The current knowledge-store status after any safe initial build.

    Raises:
        ValueError: If the database is unavailable or its schema is stale.
    """
    status = knowledge_store_status(repo_root=repo_root)
    if status.status in REBUILDABLE_KNOWLEDGE_STATUSES:
        _ = build_knowledge_store(repo_root=repo_root)
        status = knowledge_store_status(repo_root=repo_root)
    if status.status == "stale_schema":
        commands = ", ".join(status.recommended_commands)
        message = (
            "Make knowledge SQLite schema is stale; refusing backlog writes "
            "until schema "
            f"is rebuilt. Recommended command: {commands}"
        )
        raise ValueError(message)
    if not status.database_available:
        message = f"Make knowledge SQLite is unavailable: {status.status}"
        raise ValueError(message)
    _ensure_backlog_table(repo_root)
    _require_backlog_table(repo_root)
    return status


def _ensure_backlog_table(repo_root: Path) -> None:
    connection = connect_catalog_plan_ssot(repo_root=repo_root)
    try:
        with connection:
            _ensure_backlog_table_sql(connection)
    finally:
        connection.close()


def _ensure_backlog_table_sql(connection: sqlite3.Connection) -> None:
    """Create the MCP backlog runtime-extension table without changing engine.

    schema.
    """
    _ = connection.executescript(BACKLOG_SCHEMA_SQL)


def _require_backlog_table(repo_root: Path) -> None:
    database_path = resolve_repo_relative_path(
        repo_root, DEFAULT_KNOWLEDGE_DB_PATH
    )
    connection = connect_catalog_plan_ssot(repo_root=repo_root)
    try:
        row = cast(
            "Sequence[object] | None",
            connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name = ?
                """,
                (BACKLOG_TABLE_NAME,),
            ).fetchone(),
        )
    finally:
        connection.close()
    if row is None:
        message = f"Backlog table missing from SQLite SSOT: {database_path}"
        raise ValueError(message)


def _backlog_counts(
    *,
    connection: sqlite3.Connection,
    domain: str | None,
    status: str,
) -> JsonObject:
    matching_total = _count_matching_entries(
        connection=connection,
        domain=domain,
        status=status,
    )
    by_status = {
        item_status: _count_matching_entries(
            connection=connection,
            domain=domain,
            status=item_status,
        )
        for item_status in VALID_BACKLOG_STATUSES
    }
    by_domain = _domain_counts(
        connection=connection, domain=domain, status=status
    )
    return {
        "matching_total": matching_total,
        "open": by_status["open"],
        "ended": by_status["ended"],
        "by_domain": by_domain,
    }


def _count_matching_entries(
    *,
    connection: sqlite3.Connection,
    domain: str | None,
    status: str,
) -> int:
    row = cast(
        "Sequence[object] | None",
        connection.execute(
            """
            SELECT COUNT(*)
            FROM mcp_backlog_entries
            WHERE (? IS NULL OR domain = ?)
              AND (? = 'all' OR status = ?)
            """,
            (domain, domain, status, status),
        ).fetchone(),
    )
    if row is None:
        return 0
    return _int_cell(row[0])


def _domain_counts(
    *,
    connection: sqlite3.Connection,
    domain: str | None,
    status: str,
) -> list[JsonObject]:
    rows = cast(
        "list[Sequence[object]]",
        connection.execute(
            """
            SELECT domain, status, COUNT(*) AS count
            FROM mcp_backlog_entries
            WHERE (? IS NULL OR domain = ?)
              AND (? = 'all' OR status = ?)
            GROUP BY domain, status
            ORDER BY domain, status
            """,
            (domain, domain, status, status),
        ).fetchall(),
    )
    by_domain: dict[str, dict[str, int]] = {}
    for row in rows:
        row_domain = str(row[0])
        row_status = str(row[1])
        row_count = _int_cell(row[2])
        current = by_domain.setdefault(row_domain, {"open": 0, "ended": 0})
        current[row_status] = row_count
    return [
        {
            "domain": row_domain,
            "open": counts["open"],
            "ended": counts["ended"],
            "total": counts["open"] + counts["ended"],
        }
        for row_domain, counts in sorted(by_domain.items())
    ]


def _backlog_entries(
    *,
    connection: sqlite3.Connection,
    domain: str | None,
    status: str,
    limit: int,
    include_payload: bool,
) -> list[JsonObject]:
    rows = cast(
        "list[Sequence[object]]",
        connection.execute(
            """
            SELECT entry_id, domain, title, status, priority, payload_json,
            source_kind,
                   source_ref, created_at_utc, updated_at_utc
            FROM mcp_backlog_entries
            WHERE (? IS NULL OR domain = ?)
              AND (? = 'all' OR status = ?)
            ORDER BY status, priority, updated_at_utc, entry_id
            LIMIT ?
            """,
            (domain, domain, status, status, limit),
        ).fetchall(),
    )
    return [
        _backlog_entry_payload(row=row, include_payload=include_payload)
        for row in rows
    ]


def _backlog_entry_payload(
    *, row: Sequence[object], include_payload: bool
) -> JsonObject:
    entry: JsonObject = {
        "entry_id": str(row[0]),
        "domain": str(row[1]),
        "title": str(row[2]),
        "status": str(row[3]),
        "priority": _int_cell(row[4]),
        "source_kind": str(row[6]),
        "source_ref": str(row[7]),
        "created_at_utc": str(row[8]),
        "updated_at_utc": str(row[9]),
    }
    payload = _payload_from_row(row[5])
    if include_payload:
        entry["payload"] = payload
    else:
        entry["payload_keys"] = sorted(payload)
    return entry


def _json_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    return _int_cell(value)


def _int_cell(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        message = "Expected an integer SQLite cell."
        raise TypeError(message)
    return value


def _existing_created_at(
    connection: sqlite3.Connection, entry_id: str
) -> str | None:
    row = cast(
        "Sequence[object] | None",
        connection.execute(
            """
            SELECT created_at_utc
            FROM mcp_backlog_entries
            WHERE entry_id = ?
            """,
            (entry_id,),
        ).fetchone(),
    )
    return None if row is None else str(row[0])


def _optional_payload(arguments: Mapping[str, object]) -> JsonObject:
    payload_json = _optional_text(arguments.get("payload_json"))
    if payload_json is None:
        return {}
    parsed = cast("object", json.loads(payload_json))
    if not isinstance(parsed, dict):
        message = "payload_json must decode to a JSON object."
        raise TypeError(message)
    return {
        str(key): value
        for key, value in cast("Mapping[object, object]", parsed).items()
    }


def _payload_from_row(value: object) -> JsonObject:
    if not isinstance(value, str):
        message = "Backlog payload_json is not text."
        raise TypeError(message)
    parsed = cast("object", json.loads(value))
    if not isinstance(parsed, dict):
        message = "Backlog payload_json did not decode to an object."
        raise TypeError(message)
    return {
        str(key): item
        for key, item in cast("Mapping[object, object]", parsed).items()
    }


def _entry_id(
    *,
    explicit_entry_id: str | None,
    fingerprint_source: object,
) -> str:
    if explicit_entry_id is not None:
        return _safe_entry_id(explicit_entry_id)
    fingerprint = _stable_fingerprint(fingerprint_source)
    prefix = fingerprint[:GENERATED_ENTRY_ID_HEX_LENGTH]
    return f"{GENERATED_ENTRY_ID_PREFIX}-{prefix}"


def _safe_entry_id(value: str) -> str:
    normalized = value.strip().casefold()
    if not normalized:
        message = "entry_id must not be empty."
        raise ValueError(message)
    if len(normalized) > MAX_BACKLOG_TEXT_LENGTH:
        message = "entry_id is too long."
        raise ValueError(message)
    allowed = frozenset("abcdefghijklmnopqrstuvwxyz0123456789._:-")
    if any(char not in allowed for char in normalized):
        message = (
            "entry_id may contain only lowercase letters, digits, dot, "
            "underscore, "
            "colon, or hyphen."
        )
        raise ValueError(message)
    return normalized


def _backlog_domain(value: str) -> str:
    normalized = " ".join(value.strip().casefold().replace("_", " ").split())
    domain = BACKLOG_DOMAIN_ALIASES.get(
        normalized, normalized.replace(" ", "-")
    )
    if domain not in VALID_BACKLOG_DOMAINS:
        allowed = ", ".join(sorted(VALID_BACKLOG_DOMAINS))
        message = (
            f"Unknown backlog domain {value!r}; expected one of: {allowed}."
        )
        raise ValueError(message)
    return domain


def _optional_backlog_domain(value: object) -> str | None:
    text = _optional_text(value)
    return None if text is None else _backlog_domain(text)


def _list_status(value: object) -> str:
    status = (_optional_text(value) or "open").casefold()
    if status not in VALID_BACKLOG_LIST_STATUSES:
        allowed = ", ".join(sorted(VALID_BACKLOG_LIST_STATUSES))
        message = (
            f"Unknown backlog status {status!r}; expected one of: {allowed}."
        )
        raise ValueError(message)
    return status


def _priority(value: object) -> int:
    if value is None:
        return DEFAULT_BACKLOG_PRIORITY
    if isinstance(value, bool) or not isinstance(value, int):
        message = "priority must be an integer."
        raise TypeError(message)
    if not MIN_BACKLOG_PRIORITY <= value <= MAX_BACKLOG_PRIORITY:
        message = (
            f"priority must be between {MIN_BACKLOG_PRIORITY} and"
            f"{MAX_BACKLOG_PRIORITY}."
        )
        raise ValueError(message)
    return value


def _limit(value: object) -> int:
    if value is None:
        return DEFAULT_BACKLOG_LIMIT
    if isinstance(value, bool) or not isinstance(value, int):
        message = "limit must be an integer."
        raise TypeError(message)
    if value < 1:
        message = "limit must be at least 1."
        raise ValueError(message)
    return min(value, MAX_BACKLOG_LIMIT)


def _optional_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    message = "Optional Boolean value must be a Boolean."
    raise TypeError(message)


def _required_text(arguments: Mapping[str, object], key: str) -> str:
    value = arguments.get(key)
    text = _optional_text(value)
    if text is None:
        message = f"Missing required argument: {key}"
        raise ValueError(message)
    return text


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        message = "Text arguments must be strings."
        raise TypeError(message)
    text = value.strip()
    return text or None


def _bounded_text(value: str, *, field_name: str) -> str:
    if len(value) > MAX_BACKLOG_TITLE_LENGTH and field_name == "title":
        message = f"{field_name} is too long."
        raise ValueError(message)
    if len(value) > MAX_BACKLOG_TEXT_LENGTH:
        message = f"{field_name} is too long."
        raise ValueError(message)
    return value


def _canonical_json(payload: JsonObject) -> str:
    return json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )


def _stable_fingerprint(value: object) -> str:
    return _sha256_text(
        json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
