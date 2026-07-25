# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001041#repo.make-scraper.raw-spec-refresh-policy
# - 001064#repo.make-knowledge.structural-ssot
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""SQLite-backed Make raw-spec persistence.

Boundary contract:
- Owns: raw-spec payload and manifest rows in the Pancakes SQLite SSOT.
- Must not: fetch live Make services, compile catalogs, or own service
scheduling.
- Allows: direct SQLite writes and legacy-free payload loading.
- Split when: source-document import or Make API pagination state becomes
separate.
- Merge when: another module writes the same raw-spec SQLite tables.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, NamedTuple, cast

from languages.make.raw_specs.manifest import (
    build_raw_spec_manifest_for_store,
    canonical_json_bytes,
)
from languages.make.raw_specs.models import (
    JsonObject,
    RawSpecManifest,
    RawSpecRecord,
    RawSpecSanitizationStatus,
    RawSpecSourceMetadata,
    RawSpecSourceType,
    RawSpecSyncReport,
)
from languages.make.raw_specs.parser import parse_make_raw_spec
from languages.make.raw_specs.paths import safe_path_token

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from languages.make.raw_specs.config import MakeScraperConfig
    from languages.make.raw_specs.models import MakeRawSpecSource

RAW_SPEC_SQLITE_DIR: Final = "sqlite:make_raw_spec_payloads"
RAW_SPEC_SQLITE_MANIFEST_PATH: Final = "sqlite:make_raw_spec_manifest_records"
RAW_SPEC_UPDATE_REVIEW_TABLE: Final = "make_raw_spec_update_reviews"
RAW_SPEC_UPDATE_REVIEW_PENDING_STATUS: Final = "pending_review"
RAW_SPEC_UPDATE_KIND_NEW: Final = "new_raw_spec"
RAW_SPEC_UPDATE_KIND_CHANGED: Final = "changed_raw_spec"
RAW_SPEC_UPDATE_KIND_REMOVED: Final = "removed_raw_spec"
RAW_SPEC_UPDATE_REVIEW_SURFACES: Final[tuple[str, ...]] = (
    "raw_spec ",
    "catalog ",
    "semantics ",
    "native_semantics ",
    "module_projectors ",
    "blueprint_roundtrip",
)
SQLITE_BUSY_TIMEOUT_MILLISECONDS: Final = 2_147_483_647
SQLITE_BUSY_TIMEOUT_SECONDS: Final = SQLITE_BUSY_TIMEOUT_MILLISECONDS / 1000
type SqliteRow = tuple[object, ...]


class RawSpecSqliteBundle(NamedTuple):
    """Current raw-spec manifest plus payloads loaded from SQLite."""

    manifest: RawSpecManifest
    payloads_by_ref: dict[str, JsonObject]


class CurrentRawSpecRow(NamedTuple):
    """Current raw-spec row identity needed for temporal updates."""

    fingerprint: str
    sha256: str
    valid_from: str


class RawSpecUpdateReviewDraft(NamedTuple):
    """Pending downstream review opened by a raw-spec data change."""

    app_slug: str
    app_version: str
    app_label: str
    update_kind: str
    source_sha256: str
    previous_sha256: str
    previous_valid_from: str
    source_ref: str
    valid_from: str


def sync_raw_specs_to_sqlite(
    *,
    config: MakeScraperConfig,
    source: MakeRawSpecSource,
    source_metadata: RawSpecSourceMetadata,
    generated_at_utc: str | None = None,
    merge_existing: bool = False,
) -> RawSpecSyncReport:
    """Persist raw specs from an injected source directly into SQLite.

    Returns:
        The sync report for the SQLite-backed refresh.

    Raises:
        RuntimeError: If fetching or storing one app raw spec fails.
    """
    generated_at = generated_at_utc or datetime.now(UTC).isoformat()
    targets = tuple(
        sorted(
            source.list_app_versions(),
            key=lambda item: (item.app_slug, item.app_version),
        )
    )
    updated_records: list[RawSpecRecord] = []
    updated_payloads: dict[str, JsonObject] = {}
    for target in targets:
        try:
            payload = source.fetch_app_spec(target)
            record = raw_spec_record_from_payload(
                payload=payload,
                source_metadata=source_metadata,
            )
            if _skip_empty_authorized_api_record(
                record=record,
                source_metadata=source_metadata,
            ):
                continue
            updated_records.append(record)
            updated_payloads[record.relative_path] = payload
        except (sqlite3.Error, RuntimeError, TypeError, ValueError) as exc:
            message = (
                "Raw spec sync failed for "
                f"app_slug={target.app_slug!r} "
                f"app_version={target.app_version!r}: {exc}"
            )
            raise RuntimeError(message) from exc

    database_path = config.resolved_sqlite_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = _connect_database(database_path)
    try:
        ensure_raw_spec_sqlite_schema(connection)
        manifest_records, payloads_by_ref = _merged_sqlite_records(
            connection=connection,
            updated_records=tuple(updated_records),
            updated_payloads=updated_payloads,
            merge_existing=merge_existing,
        )
        manifest = build_raw_spec_manifest_for_store(
            raw_spec_dir=RAW_SPEC_SQLITE_DIR,
            records=manifest_records,
            generated_at_utc=generated_at,
        )
        persist_sqlite_raw_spec_bundle(
            connection=connection,
            bundle=RawSpecSqliteBundle(
                manifest=manifest, payloads_by_ref=payloads_by_ref
            ),
        )
        connection.commit()
    except (OSError, RuntimeError, sqlite3.Error, TypeError, ValueError) as exc:
        connection.rollback()
        message = f"Raw spec SQLite sync failed: {exc}"
        raise RuntimeError(message) from exc
    finally:
        connection.close()
        _cleanup_raw_spec_temp_dir(config)

    return RawSpecSyncReport(
        raw_spec_dir=manifest.raw_spec_dir,
        manifest_path=RAW_SPEC_SQLITE_MANIFEST_PATH,
        targets_seen=len(targets),
        files_written=len(updated_records),
        manifest_sha256=manifest.manifest_sha256,
        source_metadata=source_metadata,
        records=manifest.records,
    )


def _cleanup_raw_spec_temp_dir(config: MakeScraperConfig) -> None:
    """Delete temp raw-spec JSON files after SQLite ingest finishes."""
    raw_spec_dir = config.resolved_raw_spec_dir()
    if "temp/raw-specs-json" not in raw_spec_dir.as_posix():
        return
    shutil.rmtree(raw_spec_dir, ignore_errors=True)


def raw_spec_record_from_payload(
    *,
    payload: JsonObject,
    source_metadata: RawSpecSourceMetadata,
) -> RawSpecRecord:
    """Return the computed result for the caller."""
    parsed = parse_make_raw_spec(payload)
    payload_bytes = canonical_json_bytes(payload)
    module_kinds = tuple(
        sorted({module.module_kind for module in parsed.modules})
    )
    return RawSpecRecord(
        app_slug=parsed.app_slug,
        app_version=parsed.app_version,
        app_label=parsed.app_label,
        latest=parsed.latest,
        manifest_version=parsed.manifest_version,
        source_metadata=source_metadata,
        relative_path=sqlite_raw_spec_relative_path(
            parsed.app_slug, parsed.app_version
        ),
        sha256=hashlib.sha256(payload_bytes).hexdigest(),
        size_bytes=len(payload_bytes),
        module_count=len(parsed.modules),
        module_kinds=module_kinds,
    )


def sqlite_raw_spec_relative_path(app_slug: str, app_version: str) -> str:
    """Return the stable SQLite source ref for one raw spec."""
    return (
        f"{RAW_SPEC_SQLITE_DIR}/"
        f"{safe_path_token(app_slug)}__{safe_path_token(app_version)}"
    )


def is_sqlite_raw_spec_ref(relative_path: str) -> bool:
    """Return whether a raw-spec ref points at the SQLite payload table."""
    return relative_path.startswith(f"{RAW_SPEC_SQLITE_DIR}/")


def ensure_raw_spec_sqlite_schema(connection: sqlite3.Connection) -> None:
    """Ensure the raw-spec subset of the Pancakes SQLite schema exists."""
    _ = connection.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS snapshot_metadata (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ingest_runs (
          run_id TEXT PRIMARY KEY,
          source_kind TEXT NOT NULL,
          source_ref TEXT NOT NULL,
          generated_at_utc TEXT NOT NULL,
          fingerprint TEXT NOT NULL,
          record_count INTEGER NOT NULL,
          created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS make_raw_spec_payloads (
          app_slug TEXT NOT NULL,
          app_version TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          sha256 TEXT NOT NULL,
          size_bytes INTEGER NOT NULL,
          module_count INTEGER NOT NULL,
          module_kinds_json TEXT NOT NULL,
          source_type TEXT NOT NULL,
          is_truncated INTEGER NOT NULL,
          truncation_reason TEXT NOT NULL,
          sanitization_status TEXT NOT NULL,
          source_kind TEXT NOT NULL,
          source_ref TEXT NOT NULL,
          valid_from TEXT NOT NULL,
          valid_to TEXT,
          fingerprint TEXT NOT NULL,
          ingest_run_id TEXT NOT NULL,
          PRIMARY KEY (app_slug, app_version, valid_from)
        );

        CREATE TABLE IF NOT EXISTS make_raw_spec_manifest_records (
          app_slug TEXT NOT NULL,
          app_version TEXT NOT NULL,
          app_label TEXT NOT NULL,
          latest INTEGER NOT NULL,
          manifest_version INTEGER NOT NULL,
          relative_path TEXT NOT NULL,
          sha256 TEXT NOT NULL,
          size_bytes INTEGER NOT NULL,
          module_count INTEGER NOT NULL,
          module_kinds_json TEXT NOT NULL,
          source_metadata_json TEXT NOT NULL,
          manifest_sha256 TEXT NOT NULL,
          generated_at_utc TEXT NOT NULL,
          raw_spec_dir TEXT NOT NULL,
          source_kind TEXT NOT NULL,
          source_ref TEXT NOT NULL,
          valid_from TEXT NOT NULL,
          valid_to TEXT,
          fingerprint TEXT NOT NULL,
          ingest_run_id TEXT NOT NULL,
          PRIMARY KEY (app_slug, app_version, valid_from)
        );

        CREATE TABLE IF NOT EXISTS make_raw_spec_update_reviews (
          review_id TEXT PRIMARY KEY,
          app_slug TEXT NOT NULL,
          app_version TEXT NOT NULL,
          app_label TEXT NOT NULL,
          update_kind TEXT NOT NULL,
          review_status TEXT NOT NULL,
          review_surfaces_json TEXT NOT NULL,
          source_sha256 TEXT NOT NULL,
          previous_sha256 TEXT NOT NULL,
          previous_valid_from TEXT NOT NULL,
          source_kind TEXT NOT NULL,
          source_ref TEXT NOT NULL,
          valid_from TEXT NOT NULL,
          valid_to TEXT,
          fingerprint TEXT NOT NULL,
          ingest_run_id TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_make_raw_spec_payloads_current
          ON make_raw_spec_payloads (app_slug, app_version, valid_to);

        CREATE INDEX IF NOT EXISTS idx_make_raw_spec_manifest_records_current
          ON make_raw_spec_manifest_records (
            app_slug, app_version, generated_at_utc, valid_to
          );

        CREATE INDEX IF NOT EXISTS
        idx_make_raw_spec_manifest_records_latest_metadata
          ON make_raw_spec_manifest_records (valid_to, generated_at_utc DESC,
          raw_spec_dir);

        CREATE INDEX IF NOT EXISTS idx_make_raw_spec_update_reviews_pending
          ON make_raw_spec_update_reviews (
            review_status, valid_to, app_slug, app_version, update_kind
          );
        """
    )


def load_sqlite_raw_spec_bundle(
    *,
    database_path: Path,
) -> RawSpecSqliteBundle | None:
    """Load the current raw-spec manifest and payloads from SQLite.

    Returns:
        The current SQLite raw-spec bundle, or None when no SQLite manifest
        exists.
    """
    if not database_path.is_file():
        return None
    connection = _connect_database(database_path)
    try:
        if not _table_exists(connection, "make_raw_spec_manifest_records"):
            return None
        records = _current_manifest_records(connection)
        if not records:
            return None
        generated_at = _current_manifest_generated_at(connection)
        raw_spec_dir = _current_manifest_raw_spec_dir(connection)
        manifest = build_raw_spec_manifest_for_store(
            raw_spec_dir=raw_spec_dir,
            records=records,
            generated_at_utc=generated_at,
        )
        return RawSpecSqliteBundle(
            manifest=manifest,
            payloads_by_ref={
                record.relative_path: load_sqlite_raw_spec_payload(
                    connection=connection,
                    record=record,
                )
                for record in manifest.records
            },
        )
    finally:
        connection.close()


def persist_sqlite_raw_spec_bundle(
    *,
    connection: sqlite3.Connection,
    bundle: RawSpecSqliteBundle,
) -> None:
    """Persist a raw-spec bundle into the current SQLite connection."""
    ensure_raw_spec_sqlite_schema(connection)
    run_id = _fingerprint(
        {
            "source_kind": "raw_spec_sqlite_manifest",
            "manifest_sha256": bundle.manifest.manifest_sha256,
            "generated_at_utc": bundle.manifest.generated_at_utc,
        }
    )
    _ = connection.execute(
        """
        INSERT OR IGNORE INTO ingest_runs (
          run_id, source_kind, source_ref, generated_at_utc, fingerprint,
          record_count
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            "raw_spec_sqlite_manifest",
            RAW_SPEC_SQLITE_MANIFEST_PATH,
            bundle.manifest.generated_at_utc,
            bundle.manifest.manifest_sha256,
            len(bundle.manifest.records),
        ),
    )
    current_keys = {
        (record.app_slug, record.app_version)
        for record in bundle.manifest.records
    }
    for record in bundle.manifest.records:
        payload = bundle.payloads_by_ref[record.relative_path]
        payload_fingerprint = _payload_row_fingerprint(
            record=record, payload=payload
        )
        current_payload = _current_payload_row(
            connection=connection, record=record
        )
        current_manifest = _current_manifest_row(
            connection=connection, record=record
        )
        update_kind: str | None = None
        previous_sha256 = ""
        previous_valid_from = ""
        if current_payload is None:
            update_kind = RAW_SPEC_UPDATE_KIND_NEW
        elif current_payload.fingerprint != payload_fingerprint:
            _reject_same_timestamp_raw_spec_change(
                current_payload=current_payload,
                generated_at_utc=bundle.manifest.generated_at_utc,
                app_slug=record.app_slug,
                app_version=record.app_version,
            )
            update_kind = RAW_SPEC_UPDATE_KIND_CHANGED
            previous_sha256 = current_payload.sha256
            previous_valid_from = current_payload.valid_from
        else:
            _advance_unchanged_current_manifest_row(
                connection=connection,
                current_manifest=current_manifest,
                manifest=bundle.manifest,
                record=record,
                run_id=run_id,
            )
        if update_kind is not None:
            _close_current_payload_row(
                connection=connection,
                app_slug=record.app_slug,
                app_version=record.app_version,
                valid_to=bundle.manifest.generated_at_utc,
            )
            _close_current_manifest_row(
                connection=connection,
                app_slug=record.app_slug,
                app_version=record.app_version,
                valid_to=bundle.manifest.generated_at_utc,
            )
            _close_current_update_reviews(
                connection=connection,
                app_slug=record.app_slug,
                app_version=record.app_version,
                valid_to=bundle.manifest.generated_at_utc,
            )
            _insert_payload_row(
                connection=connection,
                record=record,
                payload=payload,
                valid_from=bundle.manifest.generated_at_utc,
                run_id=run_id,
            )
            _insert_manifest_row(
                connection=connection,
                manifest=bundle.manifest,
                record=record,
                valid_from=bundle.manifest.generated_at_utc,
                run_id=run_id,
            )
            _insert_update_review_row(
                connection=connection,
                review=RawSpecUpdateReviewDraft(
                    app_slug=record.app_slug,
                    app_version=record.app_version,
                    app_label=record.app_label,
                    update_kind=update_kind,
                    source_sha256=record.sha256,
                    previous_sha256=previous_sha256,
                    previous_valid_from=previous_valid_from,
                    source_ref=record.relative_path,
                    valid_from=bundle.manifest.generated_at_utc,
                ),
                run_id=run_id,
            )
    _close_stale_current_rows(
        connection=connection,
        current_keys=current_keys,
        valid_to=bundle.manifest.generated_at_utc,
        run_id=run_id,
    )


def load_sqlite_raw_spec_payload(
    *,
    connection: sqlite3.Connection,
    record: RawSpecRecord,
) -> JsonObject:
    """Load and verify one raw-spec payload from SQLite.

    Returns:
        The verified raw-spec payload.

    Raises:
        FileNotFoundError: If the SQLite payload row is missing.
        TypeError: If the SQLite payload is not a JSON object.
        ValueError: If the payload fingerprint does not match the manifest.
    """
    row = _fetchone(
        connection.execute(
            """
            SELECT payload_json, sha256
            FROM make_raw_spec_payloads
            WHERE app_slug = ?
              AND app_version = ?
              AND valid_to IS NULL
            ORDER BY valid_from DESC
            LIMIT 1
            """,
            (record.app_slug, record.app_version),
        )
    )
    if row is None:
        message = f"SQLite raw spec payload is missing: {record.relative_path}"
        raise FileNotFoundError(message)
    payload_text = str(row[0])
    payload_bytes = payload_text.encode("utf-8")
    digest = hashlib.sha256(payload_bytes).hexdigest()
    expected_sha256 = str(row[1])
    if digest != expected_sha256 or expected_sha256 != record.sha256:
        message = f"SQLite raw spec hash mismatch for {record.relative_path}."
        raise ValueError(message)
    payload = cast("object", json.loads(payload_text))
    if not isinstance(payload, dict):
        message = (
            f"SQLite raw spec {record.relative_path} must contain a JSONobject."
        )
        raise TypeError(message)
    return {
        str(key): value
        for key, value in cast("Mapping[object, object]", payload).items()
    }


def _connect_database(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        database_path, timeout=SQLITE_BUSY_TIMEOUT_SECONDS
    )
    _ = connection.execute(
        f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MILLISECONDS}"
    )
    return connection


def _fetchone(cursor: sqlite3.Cursor) -> SqliteRow | None:
    return cast("SqliteRow | None", cursor.fetchone())


def _fetchall(cursor: sqlite3.Cursor) -> tuple[SqliteRow, ...]:
    return tuple(cast("list[SqliteRow]", cursor.fetchall()))


def _int_cell(row: SqliteRow, index: int) -> int:
    value = row[index]
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    if isinstance(value, bytes):
        return int(value.decode("utf-8"))
    message = f"SQLite column {index} must be integer-compatible."
    raise TypeError(message)


def _merged_sqlite_records(
    *,
    connection: sqlite3.Connection,
    updated_records: tuple[RawSpecRecord, ...],
    updated_payloads: dict[str, JsonObject],
    merge_existing: bool,
) -> tuple[tuple[RawSpecRecord, ...], dict[str, JsonObject]]:
    if not merge_existing:
        return updated_records, dict(updated_payloads)
    current_bundle = _bundle_from_connection(connection)
    if current_bundle is None:
        return updated_records, dict(updated_payloads)
    updated_slugs = {record.app_slug for record in updated_records}
    preserved_records = tuple(
        record
        for record in current_bundle.manifest.records
        if record.app_slug not in updated_slugs
    )
    payloads_by_ref = {
        record.relative_path: current_bundle.payloads_by_ref[
            record.relative_path
        ]
        for record in preserved_records
    }
    payloads_by_ref.update(updated_payloads)
    return (*preserved_records, *updated_records), payloads_by_ref


def _bundle_from_connection(
    connection: sqlite3.Connection,
) -> RawSpecSqliteBundle | None:
    if not _table_exists(connection, "make_raw_spec_manifest_records"):
        return None
    records = _current_manifest_records(connection)
    if not records:
        return None
    manifest = build_raw_spec_manifest_for_store(
        raw_spec_dir=_current_manifest_raw_spec_dir(connection),
        records=records,
        generated_at_utc=_current_manifest_generated_at(connection),
    )
    return RawSpecSqliteBundle(
        manifest=manifest,
        payloads_by_ref={
            record.relative_path: load_sqlite_raw_spec_payload(
                connection=connection,
                record=record,
            )
            for record in manifest.records
        },
    )


def _current_manifest_records(
    connection: sqlite3.Connection,
) -> tuple[RawSpecRecord, ...]:
    rows = _fetchall(
        connection.execute(
            """
            SELECT
              app_slug,
              app_version,
              app_label,
              latest,
              manifest_version,
              relative_path,
              sha256,
              size_bytes,
              module_count,
              module_kinds_json,
              source_metadata_json
            FROM make_raw_spec_manifest_records
            WHERE valid_to IS NULL
            ORDER BY app_slug, app_version
            """
        )
    )
    return tuple(_record_from_row(row) for row in rows)


def _current_manifest_generated_at(connection: sqlite3.Connection) -> str:
    row = _fetchone(
        connection.execute(
            """
            SELECT generated_at_utc
            FROM make_raw_spec_manifest_records
            WHERE valid_to IS NULL
            ORDER BY generated_at_utc DESC
            LIMIT 1
            """
        )
    )
    if row is None:
        message = (
            "SQLite raw spec manifest has no current generation timestamp."
        )
        raise ValueError(message)
    return str(row[0])


def _current_manifest_raw_spec_dir(connection: sqlite3.Connection) -> str:
    row = _fetchone(
        connection.execute(
            """
            SELECT raw_spec_dir
            FROM make_raw_spec_manifest_records
            WHERE valid_to IS NULL
            ORDER BY generated_at_utc DESC
            LIMIT 1
            """
        )
    )
    if row is None:
        message = "SQLite raw spec manifest has no current raw spec dir."
        raise ValueError(message)
    return str(row[0])


def _record_from_row(row: SqliteRow) -> RawSpecRecord:
    metadata = _metadata_from_json(str(row[10]))
    module_kinds = _text_tuple_from_json(str(row[9]))
    return RawSpecRecord(
        app_slug=str(row[0]),
        app_version=str(row[1]),
        app_label=str(row[2]),
        latest=bool(_int_cell(row, 3)),
        manifest_version=_int_cell(row, 4),
        source_metadata=metadata,
        relative_path=str(row[5]),
        sha256=str(row[6]),
        size_bytes=_int_cell(row, 7),
        module_count=_int_cell(row, 8),
        module_kinds=module_kinds,
    )


def _metadata_from_json(payload_text: str) -> RawSpecSourceMetadata:
    payload = cast("object", json.loads(payload_text))
    if not isinstance(payload, dict):
        message = "Raw spec source metadata must be a JSON object."
        raise TypeError(message)
    metadata = cast("Mapping[object, object]", payload)
    source_type = _source_type(str(metadata.get("source_type")))
    sanitization_status = _sanitization_status(
        str(metadata.get("sanitization_status"))
    )
    return RawSpecSourceMetadata(
        source_type=source_type,
        is_truncated=bool(metadata.get("is_truncated")),
        truncation_reason=str(metadata.get("truncation_reason")),
        sanitization_status=sanitization_status,
    )


def _source_type(value: str) -> RawSpecSourceType:
    allowed = {
        "client_authorized_authenticated_api_response ",
        "public_make_docs ",
        "derived_fixture ",
        "third_party_connector_material",
    }
    if value not in allowed:
        message = f"Unknown raw-spec source type: {value}"
        raise ValueError(message)
    return cast("RawSpecSourceType", value)


def _sanitization_status(value: str) -> RawSpecSanitizationStatus:
    allowed = {
        "internal_raw_ignored ",
        "synthetic_fixture ",
        "sanitized_functional_facts",
    }
    if value not in allowed:
        message = f"Unknown raw-spec sanitization status: {value}"
        raise ValueError(message)
    return cast("RawSpecSanitizationStatus", value)


def _text_tuple_from_json(payload_text: str) -> tuple[str, ...]:
    payload = cast("object", json.loads(payload_text))
    if not isinstance(payload, list):
        message = "Expected a JSON string list."
        raise TypeError(message)
    return tuple(str(item) for item in cast("list[object]", payload))


def _current_payload_row(
    *,
    connection: sqlite3.Connection,
    record: RawSpecRecord,
) -> CurrentRawSpecRow | None:
    row = _fetchone(
        connection.execute(
            """
            SELECT fingerprint, sha256, valid_from
            FROM make_raw_spec_payloads
            WHERE app_slug = ?
              AND app_version = ?
              AND valid_to IS NULL
            ORDER BY valid_from DESC
            LIMIT 1
            """,
            (record.app_slug, record.app_version),
        )
    )
    if row is None:
        return None
    return CurrentRawSpecRow(
        fingerprint=str(row[0]),
        sha256=str(row[1]),
        valid_from=str(row[2]),
    )


def _current_manifest_row(
    *,
    connection: sqlite3.Connection,
    record: RawSpecRecord,
) -> CurrentRawSpecRow | None:
    row = _fetchone(
        connection.execute(
            """
            SELECT fingerprint, sha256, valid_from
            FROM make_raw_spec_manifest_records
            WHERE app_slug = ?
              AND app_version = ?
              AND valid_to IS NULL
            ORDER BY valid_from DESC
            LIMIT 1
            """,
            (record.app_slug, record.app_version),
        )
    )
    if row is None:
        return None
    return CurrentRawSpecRow(
        fingerprint=str(row[0]),
        sha256=str(row[1]),
        valid_from=str(row[2]),
    )


def _advance_unchanged_current_manifest_row(
    *,
    connection: sqlite3.Connection,
    current_manifest: CurrentRawSpecRow | None,
    manifest: RawSpecManifest,
    record: RawSpecRecord,
    run_id: str,
) -> None:
    if (
        current_manifest is not None
        and current_manifest.valid_from == manifest.generated_at_utc
    ):
        return
    if current_manifest is not None:
        _close_current_manifest_row(
            connection=connection,
            app_slug=record.app_slug,
            app_version=record.app_version,
            valid_to=manifest.generated_at_utc,
        )
    _insert_manifest_row(
        connection=connection,
        manifest=manifest,
        record=record,
        valid_from=manifest.generated_at_utc,
        run_id=run_id,
    )


def _reject_same_timestamp_raw_spec_change(
    *,
    current_payload: CurrentRawSpecRow,
    generated_at_utc: str,
    app_slug: str,
    app_version: str,
) -> None:
    if current_payload.valid_from != generated_at_utc:
        return
    message = (
        "Changed raw-spec data must use a new generated_at_utc so SQLite "
        "history can retain the prior row: "
        f"app_slug={app_slug!r} app_version={app_version!r} "
        f"generated_at_utc={generated_at_utc!r}"
    )
    raise ValueError(message)


def _payload_row_fingerprint(
    *,
    record: RawSpecRecord,
    payload: JsonObject,
) -> str:
    return _fingerprint(
        {
            "record": _record_payload(record),
            "payload_sha256": hashlib.sha256(
                canonical_json_bytes(payload)
            ).hexdigest(),
        }
    )


def _manifest_record_fingerprint(record: RawSpecRecord) -> str:
    return _fingerprint({"record": _record_payload(record)})


def _insert_payload_row(
    *,
    connection: sqlite3.Connection,
    record: RawSpecRecord,
    payload: JsonObject,
    valid_from: str,
    run_id: str,
) -> None:
    payload_text = canonical_json_bytes(payload).decode("utf-8")
    _ = connection.execute(
        """
        INSERT OR REPLACE INTO make_raw_spec_payloads (
          app_slug,
          app_version,
          payload_json,
          sha256,
          size_bytes,
          module_count,
          module_kinds_json,
          source_type,
          is_truncated,
          truncation_reason,
          sanitization_status,
          source_kind,
          source_ref,
          valid_from,
          valid_to,
          fingerprint,
          ingest_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.app_slug,
            record.app_version,
            payload_text,
            record.sha256,
            record.size_bytes,
            record.module_count,
            _json_text(list(record.module_kinds)),
            record.source_metadata.source_type,
            int(record.source_metadata.is_truncated),
            record.source_metadata.truncation_reason,
            record.source_metadata.sanitization_status,
            "raw_spec_sqlite",
            record.relative_path,
            valid_from,
            None,
            _payload_row_fingerprint(record=record, payload=payload),
            run_id,
        ),
    )


def _insert_manifest_row(
    *,
    connection: sqlite3.Connection,
    manifest: RawSpecManifest,
    record: RawSpecRecord,
    valid_from: str,
    run_id: str,
) -> None:
    _ = connection.execute(
        """
        INSERT OR REPLACE INTO make_raw_spec_manifest_records (
          app_slug,
          app_version,
          app_label,
          latest,
          manifest_version,
          relative_path,
          sha256,
          size_bytes,
          module_count,
          module_kinds_json,
          source_metadata_json,
          manifest_sha256,
          generated_at_utc,
          raw_spec_dir,
          source_kind,
          source_ref,
          valid_from,
          valid_to,
          fingerprint,
          ingest_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.app_slug,
            record.app_version,
            record.app_label,
            int(record.latest),
            record.manifest_version,
            record.relative_path,
            record.sha256,
            record.size_bytes,
            record.module_count,
            _json_text(list(record.module_kinds)),
            _json_text(_source_metadata_payload(record.source_metadata)),
            manifest.manifest_sha256,
            manifest.generated_at_utc,
            manifest.raw_spec_dir,
            "raw_spec_sqlite_manifest",
            RAW_SPEC_SQLITE_MANIFEST_PATH,
            valid_from,
            None,
            _manifest_record_fingerprint(record),
            run_id,
        ),
    )


def _insert_update_review_row(
    *,
    connection: sqlite3.Connection,
    review: RawSpecUpdateReviewDraft,
    run_id: str,
) -> None:
    review_surfaces_json = _json_text(list(RAW_SPEC_UPDATE_REVIEW_SURFACES))
    fingerprint = _fingerprint(
        {
            "app_slug": review.app_slug,
            "app_version": review.app_version,
            "update_kind": review.update_kind,
            "review_status": RAW_SPEC_UPDATE_REVIEW_PENDING_STATUS,
            "source_sha256": review.source_sha256,
            "previous_sha256": review.previous_sha256,
            "previous_valid_from": review.previous_valid_from,
            "review_surfaces": RAW_SPEC_UPDATE_REVIEW_SURFACES,
        }
    )
    _ = connection.execute(
        """
        INSERT OR IGNORE INTO make_raw_spec_update_reviews (
          review_id,
          app_slug,
          app_version,
          app_label,
          update_kind,
          review_status,
          review_surfaces_json,
          source_sha256,
          previous_sha256,
          previous_valid_from,
          source_kind,
          source_ref,
          valid_from,
          valid_to,
          fingerprint,
          ingest_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _fingerprint(
                {
                    "app_slug": review.app_slug,
                    "app_version": review.app_version,
                    "update_kind": review.update_kind,
                    "source_sha256": review.source_sha256,
                    "previous_sha256": review.previous_sha256,
                    "valid_from": review.valid_from,
                }
            ),
            review.app_slug,
            review.app_version,
            review.app_label,
            review.update_kind,
            RAW_SPEC_UPDATE_REVIEW_PENDING_STATUS,
            review_surfaces_json,
            review.source_sha256,
            review.previous_sha256,
            review.previous_valid_from,
            "raw_spec_update_review",
            review.source_ref,
            review.valid_from,
            None,
            fingerprint,
            run_id,
        ),
    )


def _close_current_payload_row(
    *,
    connection: sqlite3.Connection,
    app_slug: str,
    app_version: str,
    valid_to: str,
) -> None:
    _ = connection.execute(
        """
        UPDATE make_raw_spec_payloads
        SET valid_to = ?
        WHERE app_slug = ?
          AND app_version = ?
          AND valid_to IS NULL
        """,
        (valid_to, app_slug, app_version),
    )


def _close_current_manifest_row(
    *,
    connection: sqlite3.Connection,
    app_slug: str,
    app_version: str,
    valid_to: str,
) -> None:
    _ = connection.execute(
        """
        UPDATE make_raw_spec_manifest_records
        SET valid_to = ?
        WHERE app_slug = ?
          AND app_version = ?
          AND valid_to IS NULL
        """,
        (valid_to, app_slug, app_version),
    )


def _close_current_update_reviews(
    *,
    connection: sqlite3.Connection,
    app_slug: str,
    app_version: str,
    valid_to: str,
) -> None:
    _ = connection.execute(
        """
        UPDATE make_raw_spec_update_reviews
        SET valid_to = ?
        WHERE app_slug = ?
          AND app_version = ?
          AND valid_to IS NULL
        """,
        (valid_to, app_slug, app_version),
    )


def _close_stale_current_rows(
    *,
    connection: sqlite3.Connection,
    current_keys: set[tuple[str, str]],
    valid_to: str,
    run_id: str,
) -> None:
    rows = _fetchall(
        connection.execute(
            """
            SELECT app_slug, app_version, app_label, sha256, valid_from,
            relative_path
            FROM make_raw_spec_manifest_records
            WHERE valid_to IS NULL
            """
        )
    )
    stale_rows = tuple(
        row for row in rows if (str(row[0]), str(row[1])) not in current_keys
    )
    for row in stale_rows:
        app_slug = str(row[0])
        app_version = str(row[1])
        _close_current_payload_row(
            connection=connection,
            app_slug=app_slug,
            app_version=app_version,
            valid_to=valid_to,
        )
        _close_current_manifest_row(
            connection=connection,
            app_slug=app_slug,
            app_version=app_version,
            valid_to=valid_to,
        )
        _close_current_update_reviews(
            connection=connection,
            app_slug=app_slug,
            app_version=app_version,
            valid_to=valid_to,
        )
        _insert_update_review_row(
            connection=connection,
            review=RawSpecUpdateReviewDraft(
                app_slug=app_slug,
                app_version=app_version,
                app_label=str(row[2]),
                update_kind=RAW_SPEC_UPDATE_KIND_REMOVED,
                source_sha256="",
                previous_sha256=str(row[3]),
                previous_valid_from=str(row[4]),
                source_ref=str(row[5]),
                valid_from=valid_to,
            ),
            run_id=run_id,
        )


def _skip_empty_authorized_api_record(
    *,
    record: RawSpecRecord,
    source_metadata: RawSpecSourceMetadata,
) -> bool:
    return (
        source_metadata.source_type
        == "client_authorized_authenticated_api_response"
        and record.module_count == 0
    )


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = _fetchone(
        connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        )
    )
    return row is not None


def _record_payload(record: RawSpecRecord) -> JsonObject:
    return {
        "app_slug": record.app_slug,
        "app_version": record.app_version,
        "app_label": record.app_label,
        "latest": record.latest,
        "manifest_version": record.manifest_version,
        "source_metadata": _source_metadata_payload(record.source_metadata),
        "relative_path": record.relative_path,
        "sha256": record.sha256,
        "size_bytes": record.size_bytes,
        "module_count": record.module_count,
        "module_kinds": list(record.module_kinds),
    }


def _source_metadata_payload(metadata: RawSpecSourceMetadata) -> JsonObject:
    return {
        "source_type": metadata.source_type,
        "is_truncated": metadata.is_truncated,
        "truncation_reason": metadata.truncation_reason,
        "sanitization_status": metadata.sanitization_status,
    }


def _fingerprint(payload: JsonObject) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _json_text(payload: object) -> str:
    return json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
