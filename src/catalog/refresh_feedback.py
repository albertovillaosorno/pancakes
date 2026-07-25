# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001064#repo.make-knowledge.structural-ssot
# - 001055#repo.mcp.required-tool-surface
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""SQLite feedback records for catalog refresh and iteration intelligence.

Boundary contract:
- Owns: deterministic backlog/quarantine signals caused by refreshed Make
evidence.
- Must not: author semantic catalog answers, call providers, or create
JSON/Markdown ledgers.
- Allows: SQLite SSOT writes that prioritize development-only catalog work
review.
- Split when: refresh feedback becomes a scheduled service or needs provider
transport.
- Merge when: another module writes the same catalog refresh feedback records.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, NamedTuple, cast

from languages.make.raw_specs.paths import resolve_repo_relative_path

from catalog.json_payloads import normalize_json_object
from catalog.knowledge import DEFAULT_KNOWLEDGE_DB_PATH

if TYPE_CHECKING:
    from pathlib import Path

    from catalog.models import JsonObject

CATALOG_REFRESH_FEEDBACK_SOURCE_KIND: Final = "make_catalog_refresh_feedback"
CATALOG_REFRESH_BACKLOG_DOMAIN: Final = "catalog"
CATALOG_REFRESH_BACKLOG_STATUS: Final = "open"
CATALOG_REFRESH_QUARANTINE_KIND: Final = (
    "refresh_delta_requires_semantic_review"
)
CATALOG_REFRESH_SQLITE_BUSY_TIMEOUT_MS: Final = 2_147_483_647
CATALOG_REFRESH_SQLITE_TIMEOUT_SECONDS: Final = (
    CATALOG_REFRESH_SQLITE_BUSY_TIMEOUT_MS / 1000
)
MIN_REFRESH_FEEDBACK_PRIORITY: Final = 1
MAX_REFRESH_FEEDBACK_PRIORITY: Final = 100
MAX_REFRESH_FEEDBACK_TITLE_CHARS: Final = 240
MCP_BACKLOG_SCHEMA_SQL: Final = """
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
CATALOG_PLAN_QUARANTINE_SCHEMA_SQL: Final = """
CREATE TABLE IF NOT EXISTS catalog_plan_quarantine_records (
  quarantine_id TEXT PRIMARY KEY,
  unit_number INTEGER,
  unit_id TEXT,
  quarantine_kind TEXT NOT NULL,
  reason TEXT NOT NULL,
  evidence_gap_json TEXT NOT NULL,
  retry_policy_json TEXT NOT NULL,
  priority INTEGER NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  resolved_at_utc TEXT
);
"""


class MakeCatalogRefreshFeedbackRecord(NamedTuple):
    """One deterministic catalog refresh feedback signal."""

    feedback_key: str
    title: str
    priority: int
    evidence_kind: str
    source_ref: str
    payload: JsonObject
    unit_number: int | None


class MakeCatalogRefreshFeedbackReport(NamedTuple):
    """Summary for one catalog refresh feedback write."""

    source_of_truth: str
    sqlite_ssot_path: str
    source_kind: str
    observed_at_utc: str
    backlog_entry_ids: tuple[str, ...]
    quarantine_record_ids: tuple[str, ...]
    semantic_answer_rows_written: int


def record_make_catalog_refresh_feedback_for_repo(
    *,
    repo_root: Path,
    records: tuple[MakeCatalogRefreshFeedbackRecord, ...],
    observed_at_utc: str | None = None,
) -> MakeCatalogRefreshFeedbackReport:
    """Record refresh feedback in the repository-local SQLite SSOT.

    Returns:
        The SQLite write report for backlog and optional retry-priority
        quarantine rows.
    """
    database_path = resolve_repo_relative_path(
        repo_root, DEFAULT_KNOWLEDGE_DB_PATH
    )
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(
        database_path, timeout=CATALOG_REFRESH_SQLITE_TIMEOUT_SECONDS
    )
    try:
        _ = connection.execute(
            f"PRAGMA busy_timeout = {CATALOG_REFRESH_SQLITE_BUSY_TIMEOUT_MS}"
        )
        with connection:
            return record_make_catalog_refresh_feedback(
                connection=connection,
                records=records,
                observed_at_utc=observed_at_utc or _utc_now(),
            )
    finally:
        connection.close()


def record_make_catalog_refresh_feedback(
    *,
    connection: sqlite3.Connection,
    records: tuple[MakeCatalogRefreshFeedbackRecord, ...],
    observed_at_utc: str,
) -> MakeCatalogRefreshFeedbackReport:
    """Record Make catalog refresh feedback using an open SQLite transaction.

    Returns:
        The SQLite write report for backlog and optional retry-priority
        quarantine rows.
    """
    _ensure_refresh_feedback_schema(connection)
    observed_at = _required_text(observed_at_utc, field_name="observed_at_utc")
    backlog_entry_ids: list[str] = []
    quarantine_record_ids: list[str] = []
    for record in records:
        normalized = _normalized_record(record)
        entry_id = _backlog_entry_id(normalized)
        _upsert_backlog_entry(
            connection=connection,
            record=normalized,
            entry_id=entry_id,
            observed_at_utc=observed_at,
        )
        backlog_entry_ids.append(entry_id)
        if normalized.unit_number is not None:
            quarantine_record_ids.append(
                _upsert_quarantine_record(
                    connection=connection,
                    record=normalized,
                    entry_id=entry_id,
                    observed_at_utc=observed_at,
                )
            )
    return MakeCatalogRefreshFeedbackReport(
        source_of_truth="sqlite",
        sqlite_ssot_path=DEFAULT_KNOWLEDGE_DB_PATH.as_posix(),
        source_kind=CATALOG_REFRESH_FEEDBACK_SOURCE_KIND,
        observed_at_utc=observed_at,
        backlog_entry_ids=tuple(backlog_entry_ids),
        quarantine_record_ids=tuple(quarantine_record_ids),
        semantic_answer_rows_written=0,
    )


def _ensure_refresh_feedback_schema(connection: sqlite3.Connection) -> None:
    _ = connection.executescript(MCP_BACKLOG_SCHEMA_SQL)
    _ = connection.executescript(CATALOG_PLAN_QUARANTINE_SCHEMA_SQL)


def _normalized_record(
    record: MakeCatalogRefreshFeedbackRecord,
) -> MakeCatalogRefreshFeedbackRecord:
    feedback_key = _safe_key(record.feedback_key, field_name="feedback_key")
    title = _bounded_text(
        record.title,
        field_name="title",
        max_chars=MAX_REFRESH_FEEDBACK_TITLE_CHARS,
    )
    evidence_kind = _safe_key(record.evidence_kind, field_name="evidence_kind")
    source_ref = _required_text(record.source_ref, field_name="source_ref")
    priority = _priority(record.priority)
    unit_number = _optional_unit_number(record.unit_number)
    payload = normalize_json_object(
        {
            **record.payload,
            "codex_manual_catalog_authoring_allowed": True,
            "semantic_worker": "operator_approved_catalog_worker ",
            "retry_prompt_contract": "Catalog Work ",
            "tool_flow": "catalog.next_unit -> catalog.save_unit",
            "sqlite_ssot": True,
        }
    )
    return MakeCatalogRefreshFeedbackRecord(
        feedback_key=feedback_key,
        title=title,
        priority=priority,
        evidence_kind=evidence_kind,
        source_ref=source_ref,
        payload=payload,
        unit_number=unit_number,
    )


def _upsert_backlog_entry(
    *,
    connection: sqlite3.Connection,
    record: MakeCatalogRefreshFeedbackRecord,
    entry_id: str,
    observed_at_utc: str,
) -> None:
    payload_json = _feedback_payload_json(record=record)
    _ = connection.execute(
        """
        INSERT INTO mcp_backlog_entries (
          entry_id, domain, title, status, priority, payload_json, source_kind,
          source_ref,
          created_at_utc, updated_at_utc
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
            CATALOG_REFRESH_BACKLOG_DOMAIN,
            record.title,
            CATALOG_REFRESH_BACKLOG_STATUS,
            record.priority,
            payload_json,
            CATALOG_REFRESH_FEEDBACK_SOURCE_KIND,
            record.source_ref,
            observed_at_utc,
            observed_at_utc,
        ),
    )


def _upsert_quarantine_record(
    *,
    connection: sqlite3.Connection,
    record: MakeCatalogRefreshFeedbackRecord,
    entry_id: str,
    observed_at_utc: str,
) -> str:
    unit_number = _required_unit_number(record.unit_number)
    _assert_catalog_plan_unit_exists(
        connection=connection, unit_number=unit_number
    )
    unit_id = f"{unit_number:06d}"
    quarantine_id = _stable_id("catalog-refresh-feedback", entry_id, unit_id)
    evidence_gap_json = _canonical_json(
        {
            "backlog_entry_id": entry_id,
            "evidence_kind": record.evidence_kind,
            "feedback_key": record.feedback_key,
            "payload": record.payload,
            "unit_id": unit_id,
            "unit_number": unit_number,
        }
    )
    retry_policy_json = _canonical_json(
        {
            "manual_codex_cataloging_allowed": True,
            "retry_worker": "operator_approved_catalog_worker ",
            "retry_tool_flow": "catalog.next_unit -> catalog.save_unit ",
            "retry_prompt_contract": "Catalog Work",
            "priority_source": CATALOG_REFRESH_FEEDBACK_SOURCE_KIND,
            "retry_priority": record.priority,
        }
    )
    _ = connection.execute(
        """
        INSERT INTO catalog_plan_quarantine_records (
          quarantine_id, unit_number, unit_id, quarantine_kind, reason,
          evidence_gap_json,
          retry_policy_json, priority, source_kind, source_ref, status,
          created_at_utc,
          resolved_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        ON CONFLICT(quarantine_id) DO UPDATE SET
          quarantine_kind = excluded.quarantine_kind,
          reason = excluded.reason,
          evidence_gap_json = excluded.evidence_gap_json,
          retry_policy_json = excluded.retry_policy_json,
          priority = excluded.priority,
          source_kind = excluded.source_kind,
          source_ref = excluded.source_ref,
          status = excluded.status,
          created_at_utc = excluded.created_at_utc,
          resolved_at_utc = NULL
        """,
        (
            quarantine_id,
            unit_number,
            unit_id,
            CATALOG_REFRESH_QUARANTINE_KIND,
            record.title,
            evidence_gap_json,
            retry_policy_json,
            record.priority,
            CATALOG_REFRESH_FEEDBACK_SOURCE_KIND,
            record.source_ref,
            "needs_retry",
            observed_at_utc,
        ),
    )
    return quarantine_id


def _assert_catalog_plan_unit_exists(
    *,
    connection: sqlite3.Connection,
    unit_number: int,
) -> None:
    row = cast(
        "tuple[int] | None",
        connection.execute(
            """
            SELECT 1
            FROM catalog_plan_units
            WHERE unit_number = ? AND valid_to IS NULL
            """,
            (unit_number,),
        ).fetchone(),
    )
    if row is None:
        message = (
            f"Catalog refresh feedback references unknown unit_number:"
            f"{unit_number}"
        )
        raise ValueError(message)


def _feedback_payload_json(*, record: MakeCatalogRefreshFeedbackRecord) -> str:
    payload = normalize_json_object(
        {
            "feedback_key": record.feedback_key,
            "evidence_kind": record.evidence_kind,
            "unit_number": record.unit_number,
            "payload": record.payload,
        }
    )
    return _canonical_json(payload)


def _backlog_entry_id(record: MakeCatalogRefreshFeedbackRecord) -> str:
    feedback_hash = _stable_hash(_feedback_payload_json(record=record))[:16]
    return f"catalog-refresh:{record.feedback_key}:{feedback_hash}"


def _stable_id(*parts: str) -> str:
    return ":".join((parts[0], _stable_hash("|".join(parts[1:]))[:24]))


def _safe_key(value: str, *, field_name: str) -> str:
    text = _required_text(value, field_name=field_name).casefold()
    allowed = frozenset("abcdefghijklmnopqrstuvwxyz0123456789._:-")
    if any(char not in allowed for char in text):
        message = (
            f"{field_name} may contain only lowercase letters, digits, dot, "
            f"underscore, "
            "colon, or hyphen."
        )
        raise ValueError(message)
    return text


def _bounded_text(value: str, *, field_name: str, max_chars: int) -> str:
    text = _required_text(value, field_name=field_name)
    if len(text) > max_chars:
        message = f"{field_name} is too long."
        raise ValueError(message)
    return text


def _required_text(value: str, *, field_name: str) -> str:
    text = value.strip()
    if not text:
        message = f"{field_name} must not be empty."
        raise ValueError(message)
    return text


def _priority(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        message = "priority must be an integer."
        raise TypeError(message)
    if (
        not MIN_REFRESH_FEEDBACK_PRIORITY
        <= value
        <= MAX_REFRESH_FEEDBACK_PRIORITY
    ):
        message = (
            f"priority must be between {MIN_REFRESH_FEEDBACK_PRIORITY} "
            f"and {MAX_REFRESH_FEEDBACK_PRIORITY}."
        )
        raise ValueError(message)
    return value


def _optional_unit_number(value: int | None) -> int | None:
    if value is None:
        return None
    return _required_unit_number(value)


def _required_unit_number(value: int | None) -> int:
    if value is None or isinstance(value, bool):
        message = "unit_number must be an integer when present."
        raise TypeError(message)
    if value < 1:
        message = "unit_number must be positive."
        raise ValueError(message)
    return value


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
