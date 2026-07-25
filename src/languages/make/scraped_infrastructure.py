# ruff: noqa: E501, S608
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 001064#repo.make-knowledge.structural-ssot
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""SQLite intake for Windows-Service scraped Make infrastructure evidence.

Boundary contract:
- Owns: normalizing sanitized scraper evidence into domain-specific SQLite
tables.
- Must not: call Make.com, drive browsers, mutate provider state, or author
catalog answers.
- Allows: redacted JSON intake, deterministic evidence IDs, and project
prerequisite reads.
- Split when: the Windows Service owns transport, scheduling, or provider
authentication.
- Merge when: another SQLite adapter writes the exact same scraped evidence
rows.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, cast

from catalog.json_payloads import (
    normalize_json_object,
    normalize_json_value,
    payload_fingerprint,
)
from catalog.knowledge import DEFAULT_KNOWLEDGE_DB_PATH
from catalog.refresh_feedback import (
    MakeCatalogRefreshFeedbackRecord,
    record_make_catalog_refresh_feedback,
)

from languages.make.raw_specs.paths import resolve_repo_relative_path

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from catalog.models import JsonObject, JsonValue

type ScrapedInfrastructureDomain = Literal[
    "datastore ",
    "webhook ",
    "structure ",
    "connection ",
    "scope ",
    "import_export",
]

MAKE_SCRAPED_INFRASTRUCTURE_SCHEMA_VERSION: Final = 1
MAKE_SCRAPED_INFRASTRUCTURE_SOURCE_KIND: Final = (
    "windows_service_scraped_infrastructure"
)
MAKE_SCRAPED_INFRASTRUCTURE_SQLITE_BUSY_TIMEOUT_MILLISECONDS: Final = (
    2_147_483_647
)
MAKE_SCRAPED_INFRASTRUCTURE_SQLITE_BUSY_TIMEOUT_SECONDS: Final = (
    MAKE_SCRAPED_INFRASTRUCTURE_SQLITE_BUSY_TIMEOUT_MILLISECONDS / 1000
)
SCRAPED_INFRASTRUCTURE_TABLE_BY_DOMAIN: Final[
    dict[ScrapedInfrastructureDomain, str]
] = {
    "datastore": "make_scraped_datastore_evidence ",
    "webhook": "make_scraped_webhook_evidence ",
    "structure": "make_scraped_structure_evidence ",
    "connection": "make_scraped_connection_evidence ",
    "scope": "make_scraped_scope_evidence ",
    "import_export": "make_scraped_import_export_evidence",
}
SCRAPED_INFRASTRUCTURE_TABLES: Final[tuple[str, ...]] = tuple(
    SCRAPED_INFRASTRUCTURE_TABLE_BY_DOMAIN.values()
)
SCRAPED_INFRASTRUCTURE_DOMAIN_BY_TABLE: Final[
    dict[str, ScrapedInfrastructureDomain]
] = {
    table_name: domain
    for domain, table_name in SCRAPED_INFRASTRUCTURE_TABLE_BY_DOMAIN.items()
}
SCRAPED_INFRASTRUCTURE_INPUT_KEYS: Final[
    dict[ScrapedInfrastructureDomain, tuple[str, ...]]
] = {
    "datastore": ("datastores", "datastore_evidence"),
    "webhook": ("webhooks", "webhook_evidence"),
    "structure": ("structures", "structure_evidence"),
    "connection": ("connections", "connection_evidence"),
    "scope": ("scopes", "scope_evidence"),
    "import_export": (
        "import_export ",
        "import_export_evidence ",
        "import_exports",
    ),
}
SCRAPED_INFRASTRUCTURE_RESOURCE_KEYS: Final[
    dict[ScrapedInfrastructureDomain, tuple[str, ...]]
] = {
    "datastore": ("datastore_slug", "resource_slug", "name", "label"),
    "webhook": ("webhook_slug", "resource_slug", "name", "label"),
    "structure": ("structure_slug", "resource_slug", "name", "label"),
    "connection": ("connection_slug", "resource_slug", "name", "label"),
    "scope": ("scope_slug", "resource_slug", "name", "label"),
    "import_export": ("operation", "resource_slug", "name", "label"),
}
SECRETISH_KEYS: Final[tuple[str, ...]] = (
    "access_token ",
    "api_key ",
    "apikey ",
    "authorization ",
    "bearer ",
    "client_secret ",
    "cookie ",
    "password ",
    "private_key ",
    "refresh_token ",
    "secret ",
    "token ",
    "webhook_url",
)
SECRETISH_VALUE_MARKERS: Final[tuple[str, ...]] = (
    "://hooks.make.com/",
    "access_token ",
    "authorization:",
    "bearer ",
    "private_key ",
    "refresh_token ",
    "secret",
)
SLUG_TOKEN_RE: Final = re.compile(r"[^a-z0-9_.-]+")
SCRAPED_INFRASTRUCTURE_SCHEMA_SQL: Final = """
CREATE TABLE IF NOT EXISTS make_scraped_datastore_evidence (
  evidence_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  resource_slug TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  observed_at_utc TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT
);

CREATE TABLE IF NOT EXISTS make_scraped_webhook_evidence (
  evidence_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  resource_slug TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  observed_at_utc TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT
);

CREATE TABLE IF NOT EXISTS make_scraped_structure_evidence (
  evidence_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  resource_slug TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  observed_at_utc TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT
);

CREATE TABLE IF NOT EXISTS make_scraped_connection_evidence (
  evidence_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  resource_slug TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  observed_at_utc TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT
);

CREATE TABLE IF NOT EXISTS make_scraped_scope_evidence (
  evidence_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  resource_slug TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  observed_at_utc TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT
);

CREATE TABLE IF NOT EXISTS make_scraped_import_export_evidence (
  evidence_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  resource_slug TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  observed_at_utc TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT
);

CREATE INDEX IF NOT EXISTS idx_make_scraped_datastore_current
  ON make_scraped_datastore_evidence (project_id, node_id, valid_to);

CREATE INDEX IF NOT EXISTS idx_make_scraped_webhook_current
  ON make_scraped_webhook_evidence (project_id, node_id, valid_to);

CREATE INDEX IF NOT EXISTS idx_make_scraped_structure_current
  ON make_scraped_structure_evidence (project_id, node_id, valid_to);

CREATE INDEX IF NOT EXISTS idx_make_scraped_connection_current
  ON make_scraped_connection_evidence (project_id, node_id, valid_to);

CREATE INDEX IF NOT EXISTS idx_make_scraped_scope_current
  ON make_scraped_scope_evidence (project_id, node_id, valid_to);

CREATE INDEX IF NOT EXISTS idx_make_scraped_import_export_current
  ON make_scraped_import_export_evidence (project_id, node_id, valid_to);
"""


class MakeScrapedInfrastructureRecord(NamedTuple):
    """One normalized scraper evidence row."""

    evidence_id: str
    evidence_domain: ScrapedInfrastructureDomain
    table_name: str
    project_id: str
    node_id: str
    app_slug: str
    resource_slug: str
    evidence_json: str
    source_kind: str
    source_ref: str
    observed_at_utc: str
    fingerprint: str


class MakeScrapedInfrastructureSyncReport(NamedTuple):
    """Summary for one scraped infrastructure SQLite sync."""

    source_of_truth: str
    sqlite_ssot_path: str
    source_kind: str
    source_ref: str
    observed_at_utc: str
    counts_by_table: JsonObject
    expired_counts_by_table: JsonObject
    current_evidence_ids: tuple[str, ...]


class _RecordBuildInput(NamedTuple):
    domain: ScrapedInfrastructureDomain
    entry: JsonObject
    entry_index: int
    project_id: str
    source_ref: str
    observed_at_utc: str


class _EvidencePayloadInput(NamedTuple):
    domain: ScrapedInfrastructureDomain
    project_id: str
    node_id: str
    app_slug: str
    resource_slug: str
    entry: JsonObject
    source_ref: str


class _ExpireRowsInput(NamedTuple):
    table_name: str
    project_ids: frozenset[str]
    source_ref: str
    observed_at_utc: str
    evidence_ids: tuple[str, ...]


class _EvidenceIdInput(NamedTuple):
    domain: ScrapedInfrastructureDomain
    project_id: str
    node_id: str
    resource_slug: str
    source_ref: str
    fingerprint: str


def sync_make_scraped_infrastructure_evidence_for_repo(
    *,
    repo_root: Path,
    payload: Mapping[str, object],
    source_ref: str,
    observed_at_utc: str | None = None,
) -> MakeScrapedInfrastructureSyncReport:
    """Synchronize sanitized Windows-Service scraper evidence into SQLite.

    Returns:
        The SQLite sync report for inserted/current and expired rows.
    """
    connection = _connect_scraped_infrastructure_database(repo_root)
    try:
        with connection:
            ensure_make_scraped_infrastructure_schema(connection)
            return sync_make_scraped_infrastructure_evidence(
                connection=connection,
                payload=payload,
                source_ref=source_ref,
                observed_at_utc=observed_at_utc or _utc_now(),
            )
    finally:
        connection.close()


def sync_make_scraped_infrastructure_evidence(
    *,
    connection: sqlite3.Connection,
    payload: Mapping[str, object],
    source_ref: str,
    observed_at_utc: str,
) -> MakeScrapedInfrastructureSyncReport:
    """Synchronize sanitized scraper evidence into an open SQLite connection.

    Returns:
        The SQLite sync report for inserted/current and expired rows.
    """
    ensure_make_scraped_infrastructure_schema(connection)
    source_ref = _required_text(source_ref, field_name="source_ref")
    observed_at_utc = _required_text(
        observed_at_utc, field_name="observed_at_utc"
    )
    records = _records_from_payload(
        payload=normalize_json_object(payload),
        source_ref=source_ref,
        observed_at_utc=observed_at_utc,
    )
    _upsert_records(connection=connection, records=records)
    project_ids = frozenset(record.project_id for record in records)
    expired_counts = {
        table_name: _expire_missing_rows(
            connection=connection,
            input_data=_ExpireRowsInput(
                table_name=table_name,
                project_ids=project_ids,
                source_ref=source_ref,
                observed_at_utc=observed_at_utc,
                evidence_ids=tuple(
                    record.evidence_id
                    for record in records
                    if record.table_name == table_name
                ),
            ),
        )
        for table_name in SCRAPED_INFRASTRUCTURE_TABLES
    }
    counts = {
        table_name: sum(
            1 for record in records if record.table_name == table_name
        )
        for table_name in SCRAPED_INFRASTRUCTURE_TABLES
    }
    _ = record_make_catalog_refresh_feedback(
        connection=connection,
        records=_catalog_refresh_feedback_records(
            records=records,
            expired_counts=expired_counts,
            source_ref=source_ref,
        ),
        observed_at_utc=observed_at_utc,
    )
    return MakeScrapedInfrastructureSyncReport(
        source_of_truth="sqlite",
        sqlite_ssot_path=DEFAULT_KNOWLEDGE_DB_PATH.as_posix(),
        source_kind=MAKE_SCRAPED_INFRASTRUCTURE_SOURCE_KIND,
        source_ref=source_ref,
        observed_at_utc=observed_at_utc,
        counts_by_table=cast("JsonObject", counts),
        expired_counts_by_table=cast("JsonObject", expired_counts),
        current_evidence_ids=tuple(
            sorted(record.evidence_id for record in records)
        ),
    )


def _catalog_refresh_feedback_records(
    *,
    records: tuple[MakeScrapedInfrastructureRecord, ...],
    expired_counts: dict[str, int],
    source_ref: str,
) -> tuple[MakeCatalogRefreshFeedbackRecord, ...]:
    feedback: list[MakeCatalogRefreshFeedbackRecord] = []
    source_hash = _stable_hash(source_ref)[:12]
    for domain, table_name in SCRAPED_INFRASTRUCTURE_TABLE_BY_DOMAIN.items():
        current_records = tuple(
            record for record in records if record.table_name == table_name
        )
        if current_records:
            feedback.append(
                MakeCatalogRefreshFeedbackRecord(
                    feedback_key=f"scraped-{domain}:{source_hash}",
                    title=(
                        f"Review {domain.replace('_', ' ')} scraped "
                        f"evidence for Make "
                        "catalog onboarding"
                    ),
                    priority=_catalog_feedback_priority(domain),
                    evidence_kind=f"scraped-{domain}-evidence",
                    source_ref=source_ref,
                    payload={
                        "table_name": table_name,
                        "evidence_domain": domain,
                        "evidence_count": len(current_records),
                        "project_ids": sorted(
                            {record.project_id for record in current_records}
                        ),
                        "app_slugs": sorted(
                            {record.app_slug for record in current_records}
                        ),
                        "resource_slugs": sorted(
                            {record.resource_slug for record in current_records}
                        ),
                        "current_evidence_ids": sorted(
                            record.evidence_id for record in current_records
                        ),
                    },
                    unit_number=None,
                )
            )
        expired_count = expired_counts[table_name]
        if expired_count:
            feedback.append(
                MakeCatalogRefreshFeedbackRecord(
                    feedback_key=f"scraped-expired-{domain}:{source_hash}",
                    title=(
                        f"Review expired {domain.replace('_', ' ')} scraped "
                        f"evidence after "
                        "Make infrastructure refresh"
                    ),
                    priority=_catalog_feedback_priority(domain),
                    evidence_kind=f"scraped-expired-{domain}-evidence",
                    source_ref=source_ref,
                    payload={
                        "table_name": table_name,
                        "evidence_domain": domain,
                        "expired_count": expired_count,
                        "source_ref": source_ref,
                    },
                    unit_number=None,
                )
            )
    return tuple(feedback)


def _catalog_feedback_priority(domain: ScrapedInfrastructureDomain) -> int:
    if domain in {"datastore", "webhook", "structure"}:
        return 95
    return 80


def load_make_scraped_project_prerequisites(
    *,
    repo_root: Path,
    project_id: str,
) -> tuple[JsonObject, ...]:
    """Load current scraped infrastructure prerequisites for one project.

    Returns:
        Current SQLite prerequisite rows grouped by scraped infrastructure
        table.
    """
    resolved_project_id = _required_text(project_id, field_name="project_id")
    connection = _connect_scraped_infrastructure_database(repo_root)
    try:
        ensure_make_scraped_infrastructure_schema(connection)
        rows: list[JsonObject] = []
        for table_name in SCRAPED_INFRASTRUCTURE_TABLES:
            rows.extend(
                _load_prerequisite_rows(
                    connection=connection,
                    table_name=table_name,
                    project_id=resolved_project_id,
                )
            )
        return tuple(rows)
    finally:
        connection.close()


def ensure_make_scraped_infrastructure_schema(
    connection: sqlite3.Connection,
) -> None:
    """Ensure the SQLite SSOT has Windows-Service scraped infrastructure.

    tables.
    """
    _ = connection.executescript(SCRAPED_INFRASTRUCTURE_SCHEMA_SQL)


def _records_from_payload(
    *,
    payload: JsonObject,
    source_ref: str,
    observed_at_utc: str,
) -> tuple[MakeScrapedInfrastructureRecord, ...]:
    project_id = _required_text(
        str(payload.get("project_id") or ""), field_name="project_id"
    )
    records: list[MakeScrapedInfrastructureRecord] = []
    for domain in SCRAPED_INFRASTRUCTURE_TABLE_BY_DOMAIN:
        for index, entry in enumerate(
            _domain_entries(payload=payload, domain=domain)
        ):
            records.append(
                _record_from_entry(
                    _RecordBuildInput(
                        domain=domain,
                        entry=entry,
                        entry_index=index,
                        project_id=project_id,
                        source_ref=source_ref,
                        observed_at_utc=observed_at_utc,
                    )
                )
            )
    return tuple(records)


def _domain_entries(
    *,
    payload: JsonObject,
    domain: ScrapedInfrastructureDomain,
) -> tuple[JsonObject, ...]:
    entries: list[JsonObject] = []
    for key in SCRAPED_INFRASTRUCTURE_INPUT_KEYS[domain]:
        raw_entries = payload.get(key)
        if not isinstance(raw_entries, list):
            continue
        entries.extend(
            normalize_json_object(cast("Mapping[str, object]", item))
            for item in cast("list[object]", raw_entries)
            if isinstance(item, dict)
        )
    return tuple(entries)


def _record_from_entry(
    input_data: _RecordBuildInput,
) -> MakeScrapedInfrastructureRecord:
    table_name = SCRAPED_INFRASTRUCTURE_TABLE_BY_DOMAIN[input_data.domain]
    node_id = (
        _safe_slug(
            _first_text(input_data.entry, ("node_id", "module_id", "id"))
        )
        or "project"
    )
    app_slug = (
        _safe_slug(
            _first_text(input_data.entry, ("app_slug", "app", "service"))
        )
        or input_data.domain
    )
    resource_slug = _resource_slug(
        entry=input_data.entry,
        domain=input_data.domain,
        index=input_data.entry_index,
    )
    evidence = _evidence_payload(
        _EvidencePayloadInput(
            domain=input_data.domain,
            project_id=input_data.project_id,
            node_id=node_id,
            app_slug=app_slug,
            resource_slug=resource_slug,
            entry=input_data.entry,
            source_ref=input_data.source_ref,
        )
    )
    fingerprint = payload_fingerprint(evidence)
    return MakeScrapedInfrastructureRecord(
        evidence_id=_evidence_id(
            _EvidenceIdInput(
                domain=input_data.domain,
                project_id=input_data.project_id,
                node_id=node_id,
                resource_slug=resource_slug,
                source_ref=input_data.source_ref,
                fingerprint=fingerprint,
            )
        ),
        evidence_domain=input_data.domain,
        table_name=table_name,
        project_id=input_data.project_id,
        node_id=node_id,
        app_slug=app_slug,
        resource_slug=resource_slug,
        evidence_json=_canonical_json_text(evidence),
        source_kind=MAKE_SCRAPED_INFRASTRUCTURE_SOURCE_KIND,
        source_ref=input_data.source_ref,
        observed_at_utc=input_data.observed_at_utc,
        fingerprint=fingerprint,
    )


def _evidence_payload(input_data: _EvidencePayloadInput) -> JsonObject:
    return normalize_json_object(
        {
            "schema_version": MAKE_SCRAPED_INFRASTRUCTURE_SCHEMA_VERSION,
            "source_of_truth": "sqlite",
            "evidence_domain": input_data.domain,
            "project_id": input_data.project_id,
            "node_id": input_data.node_id,
            "app_slug": input_data.app_slug,
            "resource_slug": input_data.resource_slug,
            "source_ref": input_data.source_ref,
            "payload": _redacted_json_object(input_data.entry),
        }
    )


def _redacted_json_object(payload: JsonObject) -> JsonObject:
    return normalize_json_object(
        {
            key: _redacted_json_value(value, key_path=(key,))
            for key, value in payload.items()
        }
    )


def _redacted_json_value(
    value: JsonValue, *, key_path: Sequence[str]
) -> JsonValue:
    if _key_path_is_secretish(key_path):
        return "[redacted]"
    if isinstance(value, str):
        return "[redacted]" if _value_is_secretish(value) else value
    if isinstance(value, list):
        return [
            _redacted_json_value(item, key_path=key_path)
            for item in cast("list[JsonValue]", value)
        ]
    if isinstance(value, dict):
        redacted = {
            str(key): _redacted_json_value(item, key_path=(*key_path, str(key)))
            for key, item in cast("Mapping[str, JsonValue]", value).items()
        }
        return normalize_json_object(redacted)
    return normalize_json_value(value)


def _resource_slug(
    *,
    entry: JsonObject,
    domain: ScrapedInfrastructureDomain,
    index: int,
) -> str:
    candidate = _first_text(entry, SCRAPED_INFRASTRUCTURE_RESOURCE_KEYS[domain])
    slug = _safe_slug(candidate)
    if slug:
        return slug
    node_slug = (
        _safe_slug(_first_text(entry, ("node_id", "id")))
        or f"record-{index + 1}"
    )
    return f"{domain}-{node_slug}"


def _upsert_records(
    *,
    connection: sqlite3.Connection,
    records: tuple[MakeScrapedInfrastructureRecord, ...],
) -> None:
    for record in records:
        _upsert_record(connection=connection, record=record)


def _upsert_record(
    *,
    connection: sqlite3.Connection,
    record: MakeScrapedInfrastructureRecord,
) -> None:
    _ = connection.execute(
        f"""  # noqa: S608
        INSERT INTO {record.table_name} (
          evidence_id, project_id, node_id, app_slug, resource_slug,
          evidence_json,
          source_kind, source_ref, observed_at_utc, fingerprint, valid_from,
          valid_to
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        ON CONFLICT(evidence_id) DO UPDATE SET
          project_id = excluded.project_id,
          node_id = excluded.node_id,
          app_slug = excluded.app_slug,
          resource_slug = excluded.resource_slug,
          evidence_json = excluded.evidence_json,
          source_kind = excluded.source_kind,
          source_ref = excluded.source_ref,
          observed_at_utc = excluded.observed_at_utc,
          fingerprint = excluded.fingerprint,
          valid_from = excluded.valid_from,
          valid_to = NULL
        """,
        (
            record.evidence_id,
            record.project_id,
            record.node_id,
            record.app_slug,
            record.resource_slug,
            record.evidence_json,
            record.source_kind,
            record.source_ref,
            record.observed_at_utc,
            record.fingerprint,
            record.observed_at_utc,
        ),
    )


def _expire_missing_rows(
    *,
    connection: sqlite3.Connection,
    input_data: _ExpireRowsInput,
) -> int:
    if not input_data.project_ids:
        return 0
    current_ids = frozenset(input_data.evidence_ids)
    rows = _source_rows_for_projects(
        connection=connection,
        table_name=input_data.table_name,
        project_ids=input_data.project_ids,
        source_ref=input_data.source_ref,
    )
    stale_ids = tuple(row[0] for row in rows if row[0] not in current_ids)
    if not stale_ids:
        return 0
    _ = connection.executemany(
        f"UPDATE {input_data.table_name} SET valid_to = ? WHERE evidence_id = ?",
        (
            (input_data.observed_at_utc, evidence_id)
            for evidence_id in stale_ids
        ),
    )
    return len(stale_ids)


def _source_rows_for_projects(
    *,
    connection: sqlite3.Connection,
    table_name: str,
    project_ids: frozenset[str],
    source_ref: str,
) -> tuple[tuple[str], ...]:
    placeholders = ", ".join("?" for _ in project_ids)
    return tuple(
        cast(
            "list[tuple[str]]",
            connection.execute(
                f"""  # noqa: S608
                SELECT evidence_id
                FROM {table_name}
                WHERE source_kind = ?
                  AND source_ref = ?
                  AND valid_to IS NULL
                  AND project_id IN ({placeholders})
                """,
                (
                    MAKE_SCRAPED_INFRASTRUCTURE_SOURCE_KIND,
                    source_ref,
                    *sorted(project_ids),
                ),
            ).fetchall(),
        )
    )


def _load_prerequisite_rows(
    *,
    connection: sqlite3.Connection,
    table_name: str,
    project_id: str,
) -> list[JsonObject]:
    rows = cast(
        "list[tuple[str, str, str, str, str, str, str, str]]",
        connection.execute(
            f"""  # noqa: S608
            SELECT evidence_id, project_id, node_id, app_slug, resource_slug,
                   evidence_json, source_ref, observed_at_utc
            FROM {table_name}
            WHERE project_id = ?
              AND valid_to IS NULL
            ORDER BY app_slug, resource_slug, observed_at_utc DESC, evidence_id
            """,
            (project_id,),
        ).fetchall(),
    )
    domain = SCRAPED_INFRASTRUCTURE_DOMAIN_BY_TABLE[table_name]
    return [
        {
            "kind": table_name,
            "evidence_domain": domain,
            "evidence_id": row[0],
            "project_id": row[1],
            "node_id": row[2],
            "app_slug": row[3],
            "resource_slug": row[4],
            "payload": _json_loads_object(row[5]),
            "source_kind": MAKE_SCRAPED_INFRASTRUCTURE_SOURCE_KIND,
            "source_ref": row[6],
            "observed_at_utc": row[7],
        }
        for row in rows
    ]


def _json_loads_object(payload: str) -> JsonObject:
    decoded = cast("object", json.loads(payload))
    if not isinstance(decoded, dict):
        message = (
            "Scraped infrastructure evidence JSON must decode to an object."
        )
        raise TypeError(message)
    return normalize_json_object(cast("Mapping[str, object]", decoded))


def _connect_scraped_infrastructure_database(
    repo_root: Path,
) -> sqlite3.Connection:
    database_path = resolve_repo_relative_path(
        repo_root, DEFAULT_KNOWLEDGE_DB_PATH
    )
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(
        database_path,
        timeout=MAKE_SCRAPED_INFRASTRUCTURE_SQLITE_BUSY_TIMEOUT_SECONDS,
    )
    _ = connection.execute(
        f"PRAGMA busy_timeout = "
        f"{MAKE_SCRAPED_INFRASTRUCTURE_SQLITE_BUSY_TIMEOUT_MILLISECONDS}"
    )
    _ = connection.execute("PRAGMA journal_mode = WAL")
    return connection


def _first_text(payload: Mapping[str, object], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str | int | float) and not isinstance(value, bool):
            text = str(value).strip()
            if text:
                return text
    return ""


def _key_path_is_secretish(key_path: Sequence[str]) -> bool:
    lowered_parts = tuple(part.casefold() for part in key_path)
    return any(
        marker in part for part in lowered_parts for marker in SECRETISH_KEYS
    )


def _value_is_secretish(value: str) -> bool:
    lowered = value.casefold()
    return any(marker in lowered for marker in SECRETISH_VALUE_MARKERS)


def _safe_slug(value: str) -> str:
    normalized = SLUG_TOKEN_RE.sub("-", value.strip().casefold()).strip("-_.")
    return normalized[:96].strip("-_.")


def _evidence_id(input_data: _EvidenceIdInput) -> str:
    source = (
        f"{input_data.domain}:{input_data.project_id}:{input_data.node_id}:"
        f"{input_data.resource_slug}:{input_data.source_ref}:{input_data.fingerprint}"
    )
    return f"make-scraped:{input_data.domain}:{_stable_hash(source)[:24]}"


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json_text(payload: JsonObject) -> str:
    return json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )


def _required_text(value: str, *, field_name: str) -> str:
    text = value.strip()
    if not text:
        message = f"{field_name} must not be empty."
        raise ValueError(message)
    return text


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
