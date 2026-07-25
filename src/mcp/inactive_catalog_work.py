# ruff: noqa: E501, ERA001, PLR0913, S608
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001055#repo.mcp.required-tool-surface
# - 001064#repo.make-knowledge.structural-ssot
# - docs/adr/catalog-semantic-graph-preview-policy.md
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end
# LARGE-FILE:
# owner: pancakes-mcp
# reason: Owns the active catalog lease/save contract and SQLite state
# transition logic.
# split: Move lease handle shaping and raw-spec packet summaries into focused
# catalog modules.
# validation: pancakes.mcp.smoke plus focused MCP catalog work contract tests.
# review: Operator-requested Catalog Intelligence concurrency and safety-block
# repair.
# pyright: reportAny=false

"""Lease-based catalog work implementation for local semantic catalog fill.

Boundary contract:
- Owns: catalog unit leasing, lease-token save validation, local semantic output
indexing, and
  progress receipts.
- Must not: call providers, call live Make.com, transfer credentials, expose raw
SQL as the
  worker surface, or implicitly create a fresh catalog run from raw specs.
- Allows: active MCP executor imports for the bounded `catalog.work.next` and
  `catalog.work.save` tools.
- Split when: catalog workers become a dedicated service or scheduler process.
- Merge when: another active catalog worker module owns the same lease/save
workflow.
"""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import closing
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Final, NamedTuple, cast

from catalog.knowledge import (
    CATALOG_UNIT_NOTE_SURFACES,
    DEFAULT_KNOWLEDGE_DB_PATH,
)
from catalog.knowledge.catalog_plan_ssot import connect_catalog_plan_ssot
from catalog.knowledge.catalog_quality_reset import (
    CATALOG_CONTROL_SURFACE_SOURCE_PREFIX,
    CATALOG_RESET_STRATEGY,
    DEFAULT_CATALOG_RESET_RUN_ID,
    DEFAULT_CATALOG_RESET_SOURCE_REF,
    catalog_control_surface_payload,
    catalog_reset_units_from_raw_specs,
    start_catalog_quality_reset_run_in_transaction,
)
from catalog.knowledge.schema import read_engine_schema_sql
from catalog.value_index import require_catalog_work_output_canonical_values

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from mcp.models import JsonObject

CATALOG_WORK_PROMPT_CONTRACT: Final = "Catalog Intelligence"
CATALOG_WORK_PROMPT_ALIASES: Final[tuple[str, ...]] = ("Catalog Work",)
CATALOG_WORK_LEGACY_DEFAULT_RUN_IDS: Final[tuple[str, ...]] = (
    "catalog-run-hard-reset-v2",
)
CATALOG_WORK_LEGACY_RESET_STRATEGY: Final = "hard_semantic_reset"
CATALOG_WORK_LEASE_SECONDS: Final = 60 * 60
CATALOG_WORK_AVERAGE_RAW_SPEC_PAYLOAD_BYTES: Final = 111_836
CATALOG_WORK_DEFAULT_PAYLOAD_BUDGET_BYTES: Final = 350_000
CATALOG_WORK_MAX_PAYLOAD_BUDGET_BYTES: Final = 350_000
CATALOG_WORK_MIN_PAYLOAD_BUDGET_BYTES: Final = 1_024
CATALOG_WORK_ESTIMATED_TOKEN_BYTE_DIVISOR: Final = 4
CATALOG_WORK_RESPONSE_OVERHEAD_RESERVE_BYTES: Final = 48_000
CATALOG_WORK_QUEUED_CANDIDATE_SCAN_LIMIT: Final = 96
CATALOG_WORK_STATUS_QUEUED: Final = "queued"
CATALOG_WORK_STATUS_WORKING: Final = "working"
CATALOG_WORK_STATUS_COMPLETED: Final = "completed"
CATALOG_WORK_LEASEABLE_STATUSES: Final = frozenset(
    (
        CATALOG_WORK_STATUS_QUEUED,
        CATALOG_WORK_STATUS_WORKING,
        CATALOG_WORK_STATUS_COMPLETED,
    )
)
CATALOG_WORK_RUN_ID_TABLES: Final[tuple[str, ...]] = (
    "catalog_legacy_semantic_archives ",
    "catalog_module_intelligence_metadata ",
    "catalog_unit_notes ",
    "catalog_unit_outputs ",
    "catalog_units",
)
CATALOG_WORK_LEGACY_RUN_TEXT_COLUMNS: Final[tuple[tuple[str, str], ...]] = (
    ("catalog_modification_events", "payload_json"),
    ("catalog_modification_events", "source_ref"),
    ("catalog_modification_events", "target_id"),
    ("catalog_module_intelligence_metadata", "source_ref"),
    ("catalog_review_records", "source_ref"),
    ("catalog_unit_outputs", "output_json"),
    ("catalog_unit_outputs", "source_ref"),
    ("entity_edges", "ingest_run_id"),
    ("entity_edges", "payload_json"),
    ("entity_edges", "source_ref"),
    ("entity_nodes", "ingest_run_id"),
    ("entity_nodes", "payload_json"),
    ("entity_nodes", "source_ref"),
    ("mcp_backlog_entries", "source_ref"),
)
SQLITE_IDENTIFIER_PATTERN: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CATALOG_WORK_VALIDATION_DEFAULT: Final = "valid"
CATALOG_WORK_COVERAGE_DEFAULT: Final = "complete"
CATALOG_WORK_SAVE_TOOL_NAME: Final = "catalog.work.save"
CATALOG_WORK_NEXT_TOOL_NAME: Final = "catalog.work.next"
CATALOG_WORK_LEASE_HANDLE_FIELD: Final = "lease_handle"
CATALOG_WORK_LEGACY_LEASE_FIELD: Final = "lease_" + "token"
CATALOG_WORK_SOURCE_PACKET_MODE_FIELD: Final = "source_packet_mode"
CATALOG_WORK_SOURCE_PACKET_MODE_SUMMARY: Final = "summary"
CATALOG_WORK_SOURCE_PACKET_MODE_COMPLETE: Final = "complete"
CATALOG_WORK_SOURCE_PACKET_MODES: Final = frozenset(
    (
        CATALOG_WORK_SOURCE_PACKET_MODE_SUMMARY,
        CATALOG_WORK_SOURCE_PACKET_MODE_COMPLETE,
    )
)
CATALOG_WORK_SOURCE_KIND: Final = "mcp_catalog_work"
CATALOG_WORK_SEMANTIC_WORKER: Final = "operator_approved_catalog_worker"
CATALOG_WORK_INITIALIZE_IF_MISSING_FIELD: Final = "initialize_if_missing"
CATALOG_WORK_GRAPH_DOMAIN: Final = "catalog"
CATALOG_WORK_GRAPH_INGEST_RUN_ID_PREFIX: Final = "catalog-work-save"
CATALOG_WORK_SECRET_MARKER_PATTERN_TEXT: Final = "{api_part}{credential_part}".format(
    api_part=r"(APIKey|api[_ -]?key|apikey|access[_ -]?key|access[_ -]?token|",
    credential_part=(
        r"auth[_ -]?token|bearer[_ -]?token|bearer|refresh[_"
        r"-]?token|secret|password)"
    ),
)
CATALOG_WORK_SECRET_MARKER_PATTERN: Final = re.compile(
    CATALOG_WORK_SECRET_MARKER_PATTERN_TEXT,
    re.IGNORECASE,
)
MAX_WORKER_ID_CHARS: Final = 96
MAX_SOURCE_REF_CHARS: Final = 512
MAX_NOTE_TEXT_CHARS: Final = 2_000
MAX_OUTPUT_BYTES: Final = 262_144
MAX_SOURCE_PACKET_SUMMARY_CHARS: Final = 360
TEXT_ARGUMENT_ALLOWED_CHARS: Final[frozenset[str]] = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-/@- "
)
SMALL_PROMPT_COUNT_PAYLOAD_HINT_MAX: Final = 500
CATALOG_WORK_REQUIRED_ARRAY_FIELDS: Final[tuple[str, ...]] = (
    "app_family_aliases ",
    "module_roles ",
    "setup_dependencies ",
    "workflow_edges ",
    "module_semantics ",
    "capability_semantics ",
    "graph_nodes ",
    "graph_edges ",
    "quarantine",
)
CATALOG_WORK_REQUIRED_COVERAGE_BOOLEANS: Final[tuple[str, ...]] = (
    "semantic_output ",
    "graph_output ",
    "credential_value_transfer ",
    "provider_api_call ",
    "live_make_called",
)


class CatalogWorkSaveUnit(NamedTuple):
    """One validated unit save inside a leased catalog work batch."""

    unit_id: str
    output_json: JsonObject
    output_text: str
    output_sha256: str
    validation_status: str
    coverage_status: str
    notes: dict[str, str]


class CatalogSavedGraphNode(NamedTuple):
    """One graph node derived from a saved catalog output."""

    node_id: str
    entity_kind: str
    canonical_label: str
    payload_text: str
    source_ref: str
    fingerprint: str


class CatalogSavedGraphEdge(NamedTuple):
    """One graph edge derived from a saved catalog output."""

    edge_id: str
    edge_kind: str
    from_node_id: str
    to_node_id: str
    payload_text: str
    source_ref: str
    fingerprint: str


class CatalogModuleIntelligenceMetadata(NamedTuple):
    """Optional module-level intelligence extracted from saved catalog.

    output.
    """

    run_id: str
    unit_id: str
    module_id: str
    input_schema_json: str | None
    output_schema_json: str | None
    field_constraints_json: str | None
    error_rate_percentage: float | None
    api_rate_limit_rpm: int | None
    avg_execution_time_ms: int | None
    common_error_codes_json: str | None
    auth_type: str | None
    required_scopes_json: str | None
    token_refresh_supported: int | None
    output_cardinality: str | None
    requires_iterator: int | None
    suggested_control_structures_json: str | None
    operation_cost_multiplier: float | None
    batch_processing_supported: int | None
    cheaper_alternative_module_id: str | None
    evidence_status: str
    source_ref: str
    fingerprint: str


class DerivedModuleIntelligenceMetadata(NamedTuple):
    """Metadata fields that can be derived from explicit rows or raw-spec.

    evidence.
    """

    input_schema_json: str | None
    output_schema_json: str | None
    field_constraints_json: str | None
    output_cardinality: str | None
    requires_iterator: int | None
    suggested_control_structures_json: str | None


class CatalogSelectedWorkUnit(NamedTuple):
    """One selected row and its exact serialized worker-unit payload size."""

    row: sqlite3.Row
    payload: JsonObject
    payload_size_bytes: int


class CatalogLeasedPayload(NamedTuple):
    """All data needed to render a catalog work lease response."""

    run_id: str
    worker_id: str
    lease_token: str
    lease_expires_at: str
    payload_budget: CatalogWorkPayloadBudget
    selected_units: tuple[CatalogSelectedWorkUnit, ...]
    progress: JsonObject
    lease_replay: bool


def catalog_work_next(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Lease the next active canonical catalog batch.

    Returns:
        A lease-backed batch payload when the canonical catalog run is active.

    Raises:
        ValueError: If no active canonical catalog run can be prepared.
    """
    with closing(connect_catalog_plan_ssot(repo_root=repo_root)) as connection:
        reset_ready = _ensure_active_reset_run_if_raw_specs_exist(
            connection=connection,
            initialize_if_missing=_optional_bool(
                arguments.get(CATALOG_WORK_INITIALIZE_IF_MISSING_FIELD)
            ),
        )
        if not reset_ready:
            message = (
                "No active canonical catalog run exists. Refusing to "
                "implicitly initialize "
                "a fresh worker queue from raw specs; run the explicit "
                "catalog.knowledge "
                "reset command or call catalog.work.next with "
                "initialize_if_missing=true "
                "only when a new empty catalog run is operator-approved."
            )
            raise ValueError(message)

        worker_id = _required_worker_id(arguments)
        source_packet_mode = _source_packet_mode(
            arguments.get(CATALOG_WORK_SOURCE_PACKET_MODE_FIELD)
        )
        payload_budget = _payload_budget(arguments.get("payload_budget_bytes"))
        now = _utc_now()
        lease_expires_at = _utc_after(seconds=CATALOG_WORK_LEASE_SECONDS)
        _ = connection.execute("BEGIN IMMEDIATE")
        try:
            _reclaim_expired_leases(connection=connection, observed_at_utc=now)
            run_id = _active_run_id(connection)
            _repair_stranded_units(
                connection=connection, run_id=run_id, observed_at_utc=now
            )
            active_units = _active_units_for_worker(
                connection=connection,
                run_id=run_id,
                worker_id=worker_id,
                observed_at_utc=now,
                source_packet_mode=source_packet_mode,
            )
            if active_units:
                lease_token = _active_batch_lease_token(active_units)
                lease_expires_at = _row_text(
                    active_units[0].row, "lease_expires_at_utc"
                )
                progress = _progress_payload(
                    connection=connection, run_id=run_id
                )
                connection.commit()
                return _leased_payload(
                    CatalogLeasedPayload(
                        run_id=run_id,
                        worker_id=worker_id,
                        lease_token=lease_token,
                        lease_expires_at=lease_expires_at,
                        payload_budget=payload_budget,
                        selected_units=active_units,
                        progress=progress,
                        lease_replay=True,
                    )
                )
            candidate_rows = _queued_unit_rows(
                connection=connection,
                run_id=run_id,
            )
            selected_units = _select_payload_budget_units(
                rows=candidate_rows,
                payload_budget_bytes=payload_budget.bytes,
                source_packet_mode=source_packet_mode,
            )
            if not selected_units:
                progress = _progress_payload(
                    connection=connection, run_id=run_id
                )
                connection.commit()
                return _complete_payload(
                    run_id=run_id,
                    worker_id=worker_id,
                    payload_budget=payload_budget,
                    progress=progress,
                )

            unit_ids = tuple(
                _row_text(selected.row, "unit_id")
                for selected in selected_units
            )
            lease_token = _stable_id(
                "catalog-work-lease", run_id, worker_id, now, unit_ids
            )
            _lease_selected_units(
                connection=connection,
                run_id=run_id,
                unit_ids=unit_ids,
                worker_id=worker_id,
                lease_token=lease_token,
                locked_at_utc=now,
                lease_expires_at_utc=lease_expires_at,
            )
            progress = _progress_payload(connection=connection, run_id=run_id)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

    return _leased_payload(
        CatalogLeasedPayload(
            run_id=run_id,
            worker_id=worker_id,
            lease_token=lease_token,
            lease_expires_at=lease_expires_at,
            payload_budget=payload_budget,
            selected_units=selected_units,
            progress=progress,
            lease_replay=False,
        )
    )


def catalog_work_save(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Save one active canonical catalog lease.

    Returns:
        A write receipt after validating the worker id and lease token.

    Raises:
    ValueError: If there is no active canonical catalog run or the lease is
    invalid.
    """
    with closing(connect_catalog_plan_ssot(repo_root=repo_root)) as connection:
        _ = connection.executescript(read_engine_schema_sql())
        if not _has_active_reset_run(connection):
            message = (
                "No active canonical catalog run exists for "
                "catalog.work.save; call "
                "catalog.work.next to lease reset work, or use "
                "catalog.save_unit for the "
                "explicit legacy catalog-plan loop."
            )
            raise ValueError(message)

        worker_id = _required_worker_id(arguments)
        lease_token = _required_lease_handle(arguments)
        saves = _work_save_units(arguments)
        now = _utc_now()
        _ = connection.execute("BEGIN IMMEDIATE")
        try:
            leased_rows = _leased_rows_for_save(
                connection=connection,
                worker_id=worker_id,
                lease_token=lease_token,
                observed_at_utc=now,
            )
            leased_unit_ids = tuple(
                _row_text(row, "unit_id") for row in leased_rows
            )
            save_unit_ids = tuple(save.unit_id for save in saves)
            _reject_incomplete_batch_save(
                leased_unit_ids=leased_unit_ids,
                save_unit_ids=save_unit_ids,
            )
            run_id = _row_text(leased_rows[0], "run_id")
            _insert_unit_outputs(
                connection=connection,
                run_id=run_id,
                worker_id=worker_id,
                lease_token=lease_token,
                saves=saves,
                observed_at_utc=now,
            )
            _index_saved_graph_outputs(
                connection=connection,
                run_id=run_id,
                saves=saves,
                observed_at_utc=now,
            )
            _index_module_intelligence_metadata(
                connection=connection,
                run_id=run_id,
                saves=saves,
                observed_at_utc=now,
            )
            _update_unit_notes(
                connection=connection,
                run_id=run_id,
                saves=saves,
                observed_at_utc=now,
            )
            _complete_leased_units(
                connection=connection,
                run_id=run_id,
                saves=saves,
                observed_at_utc=now,
            )
            progress = _progress_payload(connection=connection, run_id=run_id)
            next_unit_id = _next_queued_unit_id(
                connection=connection, run_id=run_id
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

    return {
        "status": "saved ",
        "response_kind": "catalog_work_save",
        "database_path": DEFAULT_KNOWLEDGE_DB_PATH.as_posix(),
        "sqlite_ssot": True,
        "run_id": run_id,
        "worker_id": worker_id,
        "lease_handle": lease_token,
        "saved_unit_ids": list(save_unit_ids),
        "saved_unit_count": len(save_unit_ids),
        "next_unit_id": next_unit_id,
        "ledger_kind": "sqlite_ssot",
        "ledger_status": CATALOG_WORK_STATUS_COMPLETED,
        "progress": progress,
        "development_only": True,
        "semantic_worker": CATALOG_WORK_SEMANTIC_WORKER,
        "codex_catalog_authoring_allowed": True,
        "cursor_advanced": True,
        "writes_performed": True,
        "write_actions": [
            "save_catalog_unit_outputs ",
            "index_saved_graph_outputs ",
            "index_module_intelligence_metadata ",
            "complete_catalog_units",
        ],
        "live_make_called": False,
        "provider_api_call": False,
        "credential_value_transfer": False,
        "secret_output": False,
        "legacy_lease_input_supported": True,
    }


def _has_active_reset_run(connection: sqlite3.Connection) -> bool:
    if not _sqlite_table_exists(
        connection=connection, table_name="catalog_runs"
    ):
        return False
    row = connection.execute(
        """
        SELECT run_id
        FROM catalog_runs
        WHERE run_status = 'active'
        ORDER BY created_at_utc DESC, run_id
        LIMIT 1
        """
    ).fetchone()
    return row is not None


def _active_default_reset_run_is_current(
    connection: sqlite3.Connection,
) -> bool:
    if not _sqlite_table_exists(
        connection=connection, table_name="catalog_runs"
    ):
        return False
    row = connection.execute(
        """
        SELECT run_id
        FROM catalog_runs
        WHERE run_status = 'active'
          AND run_id = ?
        LIMIT 1
        """,
        (DEFAULT_CATALOG_RESET_RUN_ID,),
    ).fetchone()
    if row is None:
        return False
    operation_batch = connection.execute(
        """
        SELECT unit_id
        FROM catalog_units
        WHERE run_id = ?
          AND unit_type = 'operation_batch'
        LIMIT 1
        """,
        (DEFAULT_CATALOG_RESET_RUN_ID,),
    ).fetchone()
    return operation_batch is not None


class CatalogWorkPayloadBudget(NamedTuple):
    """Normalized worker payload budget and the request interpretation."""

    bytes: int
    request_payload: JsonObject


def _ensure_active_reset_run_if_raw_specs_exist(
    *,
    connection: sqlite3.Connection,
    initialize_if_missing: bool,
) -> bool:
    """Ensure raw-spec SQLite data is backed by the active canonical catalog.

    run.

    Returns:
        True when a reset-run queue is ready for leasing, otherwise false.
    """
    if not _sqlite_table_exists(
        connection=connection,
        table_name="make_raw_spec_manifest_records",
    ):
        return _has_active_reset_run(connection)
    if _active_default_reset_run_is_current(connection):
        return True
    _ = connection.executescript(read_engine_schema_sql())
    _ = connection.execute("BEGIN IMMEDIATE")
    try:
        _ = connection.execute("PRAGMA defer_foreign_keys = ON")
        _migrate_legacy_default_catalog_identity(connection)
        reset_ready = _active_default_reset_run_is_current(connection)
        if not reset_ready and not initialize_if_missing:
            reset_ready = _has_active_reset_run(connection)
        if not reset_ready and initialize_if_missing:
            units = catalog_reset_units_from_raw_specs(connection=connection)
            if units:
                now = _utc_now()
                _ = start_catalog_quality_reset_run_in_transaction(
                    connection=connection,
                    run_id=DEFAULT_CATALOG_RESET_RUN_ID,
                    units=units,
                    source_ref=DEFAULT_CATALOG_RESET_SOURCE_REF,
                    observed_at_utc=now,
                )
                reset_ready = True
            else:
                reset_ready = _has_active_reset_run(connection)
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    return reset_ready


def _migrate_legacy_default_catalog_identity(
    connection: sqlite3.Connection,
) -> None:
    """Rename the old default catalog run to the canonical catalog identity.

    in-place.
    """
    if not _sqlite_table_exists(
        connection=connection, table_name="catalog_runs"
    ):
        return
    default_row = connection.execute(
        """
        SELECT 1
        FROM catalog_runs
        WHERE run_id = ?
        LIMIT 1
        """,
        (DEFAULT_CATALOG_RESET_RUN_ID,),
    ).fetchone()
    if default_row is not None:
        _ = connection.execute(
            """
            UPDATE catalog_runs
            SET reset_strategy = ?
            WHERE run_id = ?
              AND reset_strategy = ?
            """,
            (
                CATALOG_RESET_STRATEGY,
                DEFAULT_CATALOG_RESET_RUN_ID,
                CATALOG_WORK_LEGACY_RESET_STRATEGY,
            ),
        )
        return

    for legacy_run_id in CATALOG_WORK_LEGACY_DEFAULT_RUN_IDS:
        legacy_row = connection.execute(
            """
            SELECT 1
            FROM catalog_runs
            WHERE run_id = ?
            LIMIT 1
            """,
            (legacy_run_id,),
        ).fetchone()
        if legacy_row is None:
            continue
        for table_name in CATALOG_WORK_RUN_ID_TABLES:
            if _table_has_column(
                connection=connection,
                table_name=table_name,
                column_name="run_id",
            ):
                table = _safe_identifier(table_name)
                _ = connection.execute(
                    f"""  # noqa: S608
                    UPDATE {table}
                    SET run_id = ?
                    WHERE run_id = ?
                    """,
                    (DEFAULT_CATALOG_RESET_RUN_ID, legacy_run_id),
                )
        _ = connection.execute(
            """
            UPDATE catalog_runs
            SET run_id = ?,
                reset_strategy = ?
            WHERE run_id = ?
            """,
            (
                DEFAULT_CATALOG_RESET_RUN_ID,
                CATALOG_RESET_STRATEGY,
                legacy_run_id,
            ),
        )
        for table_name, column_name in CATALOG_WORK_LEGACY_RUN_TEXT_COLUMNS:
            _replace_text_if_column(
                connection=connection,
                table_name=table_name,
                column_name=column_name,
                old_value=legacy_run_id,
                new_value=DEFAULT_CATALOG_RESET_RUN_ID,
            )
        return


def _active_run_id(connection: sqlite3.Connection) -> str:
    row = connection.execute(
        """
        SELECT run_id
        FROM catalog_runs
        WHERE run_status = 'active'
        ORDER BY created_at_utc DESC, run_id
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        message = "No active canonical catalog run exists."
        raise ValueError(message)
    return _row_text(cast("sqlite3.Row", row), "run_id")


def _queued_unit_rows(
    *,
    connection: sqlite3.Connection,
    run_id: str,
) -> tuple[sqlite3.Row, ...]:
    rows = connection.execute(
        """
        WITH queued_units AS (
          SELECT
            run_id,
            unit_id,
            unit_type,
            priority_band,
            priority_order,
            source_ref,
            source_hash,
            source_size_bytes,
            complexity_score,
            status,
            attempt_count,
            validation_status,
            coverage_status
          FROM catalog_units
          WHERE run_id = ?
            AND status = ?
          ORDER BY priority_order, unit_id
          LIMIT ?
        )
        SELECT
          queued_units.run_id,
          queued_units.unit_id,
          queued_units.unit_type,
          queued_units.priority_band,
          queued_units.priority_order,
          queued_units.source_ref,
          queued_units.source_hash,
          queued_units.source_size_bytes,
          queued_units.complexity_score,
          queued_units.status,
          queued_units.attempt_count,
          queued_units.validation_status,
          queued_units.coverage_status,
          manifests.app_slug,
          manifests.app_version,
          manifests.app_label,
          manifests.latest,
          manifests.module_count,
          manifests.module_kinds_json,
          manifests.source_metadata_json,
          payloads.source_type AS payload_source_type,
          payloads.is_truncated AS payload_is_truncated,
          payloads.truncation_reason AS payload_truncation_reason,
          payloads.sanitization_status AS payload_sanitization_status,
          payloads.payload_json AS payload_json
        FROM queued_units
        LEFT JOIN make_raw_spec_manifest_records AS manifests
          ON (
            queued_units.source_ref = (
              'sqlite:make_raw_spec_payloads/' || manifests.app_slug ||
              '__' || manifests.app_version
            )
            OR queued_units.source_ref LIKE (
              'sqlite:make_raw_spec_payloads/' || manifests.app_slug || '__' ||
              manifests.app_version || '#%'
            )
          )
         AND manifests.valid_to IS NULL
        LEFT JOIN make_raw_spec_payloads AS payloads
          ON payloads.app_slug = manifests.app_slug
         AND payloads.app_version = manifests.app_version
         AND payloads.valid_to IS NULL
        ORDER BY queued_units.priority_order, queued_units.unit_id
        """,
        (
            run_id,
            CATALOG_WORK_STATUS_QUEUED,
            CATALOG_WORK_QUEUED_CANDIDATE_SCAN_LIMIT,
        ),
    ).fetchall()
    return tuple(cast("sqlite3.Row", row) for row in rows)


def _active_units_for_worker(
    *,
    connection: sqlite3.Connection,
    run_id: str,
    worker_id: str,
    observed_at_utc: str,
    source_packet_mode: str,
) -> tuple[CatalogSelectedWorkUnit, ...]:
    rows = connection.execute(
        """
        SELECT
          units.run_id,
          units.unit_id,
          units.unit_type,
          units.priority_band,
          units.priority_order,
          units.source_ref,
          units.source_hash,
          units.source_size_bytes,
          units.complexity_score,
          units.status,
          units.attempt_count,
          units.validation_status,
          units.coverage_status,
          units.lease_token,
          units.lease_expires_at_utc,
          manifests.app_slug,
          manifests.app_version,
          manifests.app_label,
          manifests.latest,
          manifests.module_count,
          manifests.module_kinds_json,
          manifests.source_metadata_json,
          payloads.source_type AS payload_source_type,
          payloads.is_truncated AS payload_is_truncated,
          payloads.truncation_reason AS payload_truncation_reason,
          payloads.sanitization_status AS payload_sanitization_status,
          payloads.payload_json AS payload_json
        FROM catalog_units AS units
        LEFT JOIN make_raw_spec_manifest_records AS manifests
          ON (
            units.source_ref = (
              'sqlite:make_raw_spec_payloads/' || manifests.app_slug ||
              '__' || manifests.app_version
            )
            OR units.source_ref LIKE (
              'sqlite:make_raw_spec_payloads/' || manifests.app_slug || '__' ||
              manifests.app_version || '#%'
            )
          )
         AND manifests.valid_to IS NULL
        LEFT JOIN make_raw_spec_payloads AS payloads
          ON payloads.app_slug = manifests.app_slug
         AND payloads.app_version = manifests.app_version
         AND payloads.valid_to IS NULL
        WHERE units.run_id = ?
          AND units.status = ?
          AND units.locked_by = ?
          AND units.lease_expires_at_utc > ?
        ORDER BY units.priority_order, units.unit_id
        """,
        (run_id, CATALOG_WORK_STATUS_WORKING, worker_id, observed_at_utc),
    ).fetchall()
    return tuple(
        _selected_existing_active_unit(
            cast("sqlite3.Row", row),
            source_packet_mode=source_packet_mode,
        )
        for row in rows
    )


def _selected_existing_active_unit(
    row: sqlite3.Row,
    *,
    source_packet_mode: str,
) -> CatalogSelectedWorkUnit:
    payload = _unit_payload(
        row,
        existing_active_lease=True,
        source_packet_mode=source_packet_mode,
    )
    return CatalogSelectedWorkUnit(
        row=row,
        payload=payload,
        payload_size_bytes=_serialized_payload_size(payload),
    )


def _active_batch_lease_token(
    active_units: tuple[CatalogSelectedWorkUnit, ...],
) -> str:
    lease_tokens = {
        _row_text(selected.row, "lease_token")
        for selected in active_units
        if _row_text(selected.row, "lease_token")
    }
    if len(lease_tokens) != 1:
        message = "Active catalog worker batch has inconsistent lease tokens."
        raise ValueError(message)
    return next(iter(lease_tokens))


def _select_payload_budget_units(
    *,
    rows: Sequence[sqlite3.Row],
    payload_budget_bytes: int,
    source_packet_mode: str,
) -> tuple[CatalogSelectedWorkUnit, ...]:
    selected: list[CatalogSelectedWorkUnit] = []
    total_size = 0
    unit_payload_budget = _unit_payload_budget_bytes(payload_budget_bytes)
    for row in rows:
        unit_payload = _unit_payload(row, source_packet_mode=source_packet_mode)
        unit_payload_size = _serialized_payload_size(unit_payload)
        selected_unit = CatalogSelectedWorkUnit(
            row=row,
            payload=unit_payload,
            payload_size_bytes=unit_payload_size,
        )
        if not selected:
            selected.append(selected_unit)
            total_size += unit_payload_size
            if unit_payload_size >= unit_payload_budget:
                break
            continue
        if total_size + unit_payload_size > unit_payload_budget:
            break
        selected.append(selected_unit)
        total_size += unit_payload_size
    return tuple(selected)


def _unit_payload_budget_bytes(payload_budget_bytes: int) -> int:
    if payload_budget_bytes <= (
        CATALOG_WORK_RESPONSE_OVERHEAD_RESERVE_BYTES
        + CATALOG_WORK_MIN_PAYLOAD_BUDGET_BYTES
    ):
        return payload_budget_bytes
    return payload_budget_bytes - CATALOG_WORK_RESPONSE_OVERHEAD_RESERVE_BYTES


def _serialized_payload_size(payload: Mapping[str, object]) -> int:
    return len(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _lease_selected_units(
    *,
    connection: sqlite3.Connection,
    run_id: str,
    unit_ids: tuple[str, ...],
    worker_id: str,
    lease_token: str,
    locked_at_utc: str,
    lease_expires_at_utc: str,
) -> None:
    _ = connection.executemany(
        """
        UPDATE catalog_units
        SET status = ?,
            locked_by = ?,
            locked_at_utc = ?,
            lease_expires_at_utc = ?,
            lease_token = ?,
            attempt_count = attempt_count + 1,
            updated_at_utc = ?
        WHERE run_id = ?
          AND unit_id = ?
          AND status = ?
        """,
        [
            (
                CATALOG_WORK_STATUS_WORKING,
                worker_id,
                locked_at_utc,
                lease_expires_at_utc,
                lease_token,
                locked_at_utc,
                run_id,
                unit_id,
                CATALOG_WORK_STATUS_QUEUED,
            )
            for unit_id in unit_ids
        ],
    )


def _reclaim_expired_leases(
    *,
    connection: sqlite3.Connection,
    observed_at_utc: str,
) -> None:
    _ = connection.execute(
        """
        UPDATE catalog_units
        SET status = ?,
            locked_by = NULL,
            locked_at_utc = NULL,
            lease_expires_at_utc = NULL,
            lease_token = NULL,
            updated_at_utc = ?
        WHERE status = ?
          AND lease_expires_at_utc IS NOT NULL
          AND lease_expires_at_utc <= ?
        """,
        (
            CATALOG_WORK_STATUS_QUEUED,
            observed_at_utc,
            CATALOG_WORK_STATUS_WORKING,
            observed_at_utc,
        ),
    )


def _repair_stranded_units(
    *,
    connection: sqlite3.Connection,
    run_id: str,
    observed_at_utc: str,
) -> None:
    """Recover units stranded outside the canonical lease statuses.

    Workers can only lease queued rows. If a failed or manual status update
    leaves a unit in a
    non-canonical status without an output, make it queueable again. If an
    output exists, the unit
    is already semantically saved and should count as completed.
    """
    _ = connection.execute(
        """
        UPDATE catalog_units
        SET status = ?,
            locked_by = NULL,
            locked_at_utc = NULL,
            lease_expires_at_utc = NULL,
            lease_token = NULL,
            completed_at_utc = COALESCE(
              completed_at_utc,
              (
                SELECT outputs.created_at_utc
                FROM catalog_unit_outputs AS outputs
                WHERE outputs.run_id = catalog_units.run_id
                  AND outputs.unit_id = catalog_units.unit_id
                ORDER BY outputs.created_at_utc DESC
                LIMIT 1
              ),
              ?
            ),
            validation_status = COALESCE(
              (
                SELECT outputs.validation_status
                FROM catalog_unit_outputs AS outputs
                WHERE outputs.run_id = catalog_units.run_id
                  AND outputs.unit_id = catalog_units.unit_id
                ORDER BY outputs.created_at_utc DESC
                LIMIT 1
              ),
              validation_status
            ),
            coverage_status = ?,
            updated_at_utc = ?
        WHERE run_id = ?
          AND status <> ?
          AND EXISTS (
            SELECT 1
            FROM catalog_unit_outputs AS outputs
            WHERE outputs.run_id = catalog_units.run_id
              AND outputs.unit_id = catalog_units.unit_id
          )
        """,
        (
            CATALOG_WORK_STATUS_COMPLETED,
            observed_at_utc,
            CATALOG_WORK_COVERAGE_DEFAULT,
            observed_at_utc,
            run_id,
            CATALOG_WORK_STATUS_COMPLETED,
        ),
    )
    _ = connection.execute(
        """
        UPDATE catalog_units
        SET status = ?,
            locked_by = NULL,
            locked_at_utc = NULL,
            lease_expires_at_utc = NULL,
            lease_token = NULL,
            validation_status = 'pending',
            coverage_status = 'missing',
            updated_at_utc = ?
        WHERE run_id = ?
          AND status NOT IN (?, ?, ?)
          AND NOT EXISTS (
            SELECT 1
            FROM catalog_unit_outputs AS outputs
            WHERE outputs.run_id = catalog_units.run_id
              AND outputs.unit_id = catalog_units.unit_id
          )
        """,
        (
            CATALOG_WORK_STATUS_QUEUED,
            observed_at_utc,
            run_id,
            *sorted(CATALOG_WORK_LEASEABLE_STATUSES),
        ),
    )


def _leased_rows_for_save(
    *,
    connection: sqlite3.Connection,
    worker_id: str,
    lease_token: str,
    observed_at_utc: str,
) -> tuple[sqlite3.Row, ...]:
    if lease_token == worker_id:
        message = (
            "lease_handle_mismatch: lease_handle must be the opaque handle "
            "returned by "
            "catalog.work.next, not the worker_id."
        )
        raise ValueError(message)
    rows = tuple(
        cast("sqlite3.Row", row)
        for row in connection.execute(
            """
            SELECT run_id, unit_id, lease_expires_at_utc
            FROM catalog_units
            WHERE status = ?
              AND locked_by = ?
              AND lease_token = ?
            ORDER BY priority_order, unit_id
            """,
            (CATALOG_WORK_STATUS_WORKING, worker_id, lease_token),
        ).fetchall()
    )
    if not rows:
        worker_rows = connection.execute(
            """
            SELECT unit_id
            FROM catalog_units
            WHERE status = ?
              AND locked_by = ?
            LIMIT 1
            """,
            (CATALOG_WORK_STATUS_WORKING, worker_id),
        ).fetchone()
        token_rows = connection.execute(
            """
            SELECT unit_id
            FROM catalog_units
            WHERE status = ?
              AND lease_token = ?
            LIMIT 1
            """,
            (CATALOG_WORK_STATUS_WORKING, lease_token),
        ).fetchone()
        if worker_rows is not None:
            message = (
                "lease_handle_mismatch: lease_handle does not match worker_id "
                "active batch."
            )
            raise ValueError(message)
        if token_rows is not None:
            message = (
                "worker_id_mismatch: worker_id does not match lease_handle "
                "active batch."
            )
            raise ValueError(message)
        message = (
            "active_lease_not_found: worker_id and lease_handle do not match "
            "an active lease."
        )
        raise ValueError(message)
    expired = tuple(
        row
        for row in rows
        if _row_text(row, "lease_expires_at_utc") <= observed_at_utc
    )
    if expired:
        message = (
            "lease_expired: the matching lease has expired; call "
            "catalog.work.next again."
        )
        raise ValueError(message)
    return rows


def _reject_incomplete_batch_save(
    *,
    leased_unit_ids: tuple[str, ...],
    save_unit_ids: tuple[str, ...],
) -> None:
    if sorted(leased_unit_ids) == sorted(save_unit_ids):
        return
    leased = set(leased_unit_ids)
    saved = set(save_unit_ids)
    unexpected_units = sorted(saved - leased)
    if unexpected_units:
        message = f"unit_not_in_active_batch: {unexpected_units[0]}"
        raise ValueError(message)
    missing_units = sorted(leased - saved)
    message = f"incomplete_batch_save: missing_units={missing_units}"
    raise ValueError(message)


def _work_save_units(
    arguments: Mapping[str, object],
) -> tuple[CatalogWorkSaveUnit, ...]:
    answers_json = arguments.get("answers_json")
    if answers_json is not None:
        payload = _json_object_argument(answers_json, field_name="answers_json")
        raw_units = payload.get("units")
        if not isinstance(raw_units, list) or not raw_units:
            message = "answers_json.units must be a non-empty array."
            raise ValueError(message)
        return tuple(
            _save_unit_from_payload(
                _json_object_argument(item, field_name="answers_json.units")
            )
            for item in cast("list[object]", raw_units)
        )

    unit_id = _required_text(arguments, "unit_id")
    answer_json = _json_object_argument(
        arguments.get("answer_json"), field_name="answer_json"
    )
    merged_answer = dict(answer_json)
    _ = merged_answer.setdefault("unit_id", unit_id)
    return (_save_unit_from_payload(merged_answer),)


def _save_unit_from_payload(
    payload: Mapping[str, object],
) -> CatalogWorkSaveUnit:
    unit_id = _required_mapping_text(payload, "unit_id")
    output_json = _json_object_argument(
        payload.get("output_json", payload),
        field_name="output_json",
    )
    _validate_semantic_graph_output(output_json)
    require_catalog_work_output_canonical_values(output_json)
    output_text = json.dumps(
        output_json, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
    output_size = len(output_text.encode("utf-8"))
    if output_size > MAX_OUTPUT_BYTES:
        message = f"Catalog work output is capped at {MAX_OUTPUT_BYTES} bytes."
        raise ValueError(message)
    validation_status = _optional_mapping_text(
        payload, "validation_status"
    ) or (CATALOG_WORK_VALIDATION_DEFAULT)
    coverage_status = _optional_mapping_text(payload, "coverage_status") or (
        CATALOG_WORK_COVERAGE_DEFAULT
    )
    notes = _notes_from_payload(payload.get("notes"))
    return CatalogWorkSaveUnit(
        unit_id=unit_id,
        output_json=output_json,
        output_text=output_text,
        output_sha256=_sha256_text(output_text),
        validation_status=validation_status,
        coverage_status=coverage_status,
        notes=notes,
    )


def validate_catalog_work_save_unit_for_preview(
    payload: Mapping[str, object],
) -> CatalogWorkSaveUnit:
    """Validate one semantic output with the same checks used by.

    catalog.work.save.

    Returns:
        The normalized save unit used by the atomic catalog work save path.
    """
    return _save_unit_from_payload(payload)


def _validate_semantic_graph_output(output_json: Mapping[str, object]) -> None:
    summary = output_json.get("semantic_summary")
    if not isinstance(summary, str) or not summary.strip():
        message = "missing_required_field: semantic_summary"
        raise ValueError(message)
    for field_name in CATALOG_WORK_REQUIRED_ARRAY_FIELDS:
        value = output_json.get(field_name)
        if value is None:
            message = f"missing_required_field: {field_name}"
            raise ValueError(message)
        if not isinstance(value, list):
            message = f"invalid_required_field: {field_name}"
            raise TypeError(message)
        if field_name in {"graph_nodes", "graph_edges"} and not value:
            message = f"empty_graph_output: {field_name}"
            raise ValueError(message)
    coverage = output_json.get("coverage")
    if not isinstance(coverage, dict):
        message = "missing_required_field: coverage"
        raise TypeError(message)
    for field_name in CATALOG_WORK_REQUIRED_COVERAGE_BOOLEANS:
        value = cast("Mapping[object, object]", coverage).get(field_name)
        if value is None:
            message = f"missing_required_field: coverage.{field_name}"
            raise ValueError(message)
        if not isinstance(value, bool):
            message = f"invalid_required_field: coverage.{field_name}"
            raise TypeError(message)


def _notes_from_payload(value: object) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        message = "notes must be a JSON object keyed by catalog note surface."
        raise TypeError(message)
    notes: dict[str, str] = {}
    for raw_key, raw_value in cast("Mapping[object, object]", value).items():
        note_surface = str(raw_key)
        if note_surface not in CATALOG_UNIT_NOTE_SURFACES:
            allowed = ", ".join(CATALOG_UNIT_NOTE_SURFACES)
            message = (
                f"Unknown catalog note surface {note_surface!r}; expected one "
                f"of: {allowed}."
            )
            raise ValueError(message)
        if not isinstance(raw_value, str):
            message = f"Catalog note {note_surface!r} must be text."
            raise TypeError(message)
        note_text = raw_value.strip()
        if len(note_text) > MAX_NOTE_TEXT_CHARS:
            message = f"Catalog note {note_surface!r} is too long."
            raise ValueError(message)
        notes[note_surface] = note_text
    return notes


def _insert_unit_outputs(
    *,
    connection: sqlite3.Connection,
    run_id: str,
    worker_id: str,
    lease_token: str,
    saves: tuple[CatalogWorkSaveUnit, ...],
    observed_at_utc: str,
) -> None:
    _ = connection.executemany(
        """
        INSERT OR REPLACE INTO catalog_unit_outputs (
          run_id, unit_id, lease_token, worker_id, output_json, output_sha256,
        validation_status, saved_by_tool, created_at_utc, source_kind,
        source_ref,
          fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                run_id,
                save.unit_id,
                lease_token,
                worker_id,
                save.output_text,
                save.output_sha256,
                save.validation_status,
                CATALOG_WORK_SAVE_TOOL_NAME,
                observed_at_utc,
                CATALOG_WORK_SOURCE_KIND,
                f"sqlite:catalog_unit_outputs/{run_id}/{save.unit_id}",
                _stable_id(
                    "catalog-unit-output",
                    run_id,
                    save.unit_id,
                    save.output_sha256,
                ),
            )
            for save in saves
        ],
    )


def _index_saved_graph_outputs(
    *,
    connection: sqlite3.Connection,
    run_id: str,
    saves: tuple[CatalogWorkSaveUnit, ...],
    observed_at_utc: str,
) -> None:
    """Materialize saved semantic graph arrays into typed graph lookup.

    tables.
    """
    nodes = tuple(
        node
        for save in saves
        for node in _saved_graph_nodes(run_id=run_id, save=save)
    )
    edges = tuple(
        edge
        for save in saves
        for edge in _saved_graph_edges(run_id=run_id, save=save)
    )
    ingest_run_id = _graph_ingest_run_id(run_id)
    if nodes:
        _expire_saved_graph_nodes(
            connection=connection,
            nodes=nodes,
            ingest_run_id=ingest_run_id,
            observed_at_utc=observed_at_utc,
        )
        _insert_saved_graph_nodes(
            connection=connection,
            nodes=nodes,
            ingest_run_id=ingest_run_id,
            observed_at_utc=observed_at_utc,
        )
    if edges:
        _expire_saved_graph_edges(
            connection=connection,
            edges=edges,
            ingest_run_id=ingest_run_id,
            observed_at_utc=observed_at_utc,
        )
        _insert_saved_graph_edges(
            connection=connection,
            edges=edges,
            ingest_run_id=ingest_run_id,
            observed_at_utc=observed_at_utc,
        )


def _catalog_output_source_ref(
    run_id: str, unit_id: str, section: str, index: int
) -> str:
    """Return a catalog output source reference.

    Returns:
        The SQLite-backed source reference.
    """
    return f"sqlite:catalog_unit_outputs/{run_id}/{unit_id}#{section}/{index}"


def _catalog_work_edge_id(
    run_id: str, unit_id: str, index: int, payload_text: str
) -> str:
    """Return a stable catalog-work edge id.

    Returns:
        The generated edge id.
    """
    return (
        f"catalog-work-edge:{_stable_id(run_id, unit_id, index, payload_text)}"
    )


def _saved_graph_nodes(
    *,
    run_id: str,
    save: CatalogWorkSaveUnit,
) -> tuple[CatalogSavedGraphNode, ...]:
    value = save.output_json.get("graph_nodes")
    if not isinstance(value, list):
        return ()
    nodes: list[CatalogSavedGraphNode] = []
    for index, item in enumerate(cast("list[object]", value)):
        if not isinstance(item, dict):
            continue
        node = {
            str(item_key): item_value
            for item_key, item_value in cast(
                "Mapping[object, object]", item
            ).items()
        }
        node_id = _optional_mapping_text(node, "node_id")
        if node_id is None:
            continue
        entity_kind = (
            _optional_mapping_text(node, "entity_kind")
            or _optional_mapping_text(node, "node_kind")
            or "catalog_semantic_node"
        )
        canonical_label = (
            _optional_mapping_text(node, "canonical_label")
            or _optional_mapping_text(node, "label")
            or node_id
        )
        payload_text = _stable_json_text(
            {
                **node,
                "run_id": run_id,
                "unit_id": save.unit_id,
            }
        )
        source_ref = _catalog_output_source_ref(
            run_id, save.unit_id, "graph_nodes", index
        )
        nodes.append(
            CatalogSavedGraphNode(
                node_id=node_id,
                entity_kind=entity_kind,
                canonical_label=canonical_label,
                payload_text=payload_text,
                source_ref=source_ref,
                fingerprint=_stable_id(
                    "catalog-work-graph-node", node_id, payload_text
                ),
            )
        )
    return tuple(nodes)


def _saved_graph_edges(
    *,
    run_id: str,
    save: CatalogWorkSaveUnit,
) -> tuple[CatalogSavedGraphEdge, ...]:
    value = save.output_json.get("graph_edges")
    if not isinstance(value, list):
        return ()
    edges: list[CatalogSavedGraphEdge] = []
    for index, item in enumerate(cast("list[object]", value)):
        if not isinstance(item, dict):
            continue
        edge = {
            str(item_key): item_value
            for item_key, item_value in cast(
                "Mapping[object, object]", item
            ).items()
        }
        from_node_id = _optional_mapping_text(edge, "from_node_id")
        to_node_id = _optional_mapping_text(edge, "to_node_id")
        if from_node_id is None or to_node_id is None:
            continue
        edge_kind = (
            _optional_mapping_text(edge, "edge_kind")
            or _optional_mapping_text(edge, "kind")
            or "catalog_semantic_edge"
        )
        payload_text = _stable_json_text(
            {
                **edge,
                "run_id": run_id,
                "unit_id": save.unit_id,
            }
        )
        edge_id = _optional_mapping_text(
            edge, "edge_id"
        ) or _catalog_work_edge_id(run_id, save.unit_id, index, payload_text)
        source_ref = _catalog_output_source_ref(
            run_id, save.unit_id, "graph_edges", index
        )
        edges.append(
            CatalogSavedGraphEdge(
                edge_id=edge_id,
                edge_kind=edge_kind,
                from_node_id=from_node_id,
                to_node_id=to_node_id,
                payload_text=payload_text,
                source_ref=source_ref,
                fingerprint=_stable_id(
                    "catalog-work-graph-edge", edge_id, payload_text
                ),
            )
        )
    return tuple(edges)


def _expire_saved_graph_nodes(
    *,
    connection: sqlite3.Connection,
    nodes: tuple[CatalogSavedGraphNode, ...],
    ingest_run_id: str,
    observed_at_utc: str,
) -> None:
    _ = connection.executemany(
        """
        UPDATE entity_nodes
        SET valid_to = ?
        WHERE domain = ?
          AND source_kind = ?
          AND ingest_run_id = ?
          AND node_id = ?
          AND valid_to IS NULL
        """,
        [
            (
                observed_at_utc,
                CATALOG_WORK_GRAPH_DOMAIN,
                CATALOG_WORK_SOURCE_KIND,
                ingest_run_id,
                node.node_id,
            )
            for node in nodes
        ],
    )


def _insert_saved_graph_nodes(
    *,
    connection: sqlite3.Connection,
    nodes: tuple[CatalogSavedGraphNode, ...],
    ingest_run_id: str,
    observed_at_utc: str,
) -> None:
    _ = connection.executemany(
        """
        INSERT OR REPLACE INTO entity_nodes (
        node_id, domain, entity_kind, canonical_label, payload_json,
        source_kind,
          source_ref, valid_from, valid_to, fingerprint, ingest_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
        """,
        [
            (
                node.node_id,
                CATALOG_WORK_GRAPH_DOMAIN,
                node.entity_kind,
                node.canonical_label,
                node.payload_text,
                CATALOG_WORK_SOURCE_KIND,
                node.source_ref,
                observed_at_utc,
                node.fingerprint,
                ingest_run_id,
            )
            for node in nodes
        ],
    )


def _expire_saved_graph_edges(
    *,
    connection: sqlite3.Connection,
    edges: tuple[CatalogSavedGraphEdge, ...],
    ingest_run_id: str,
    observed_at_utc: str,
) -> None:
    _ = connection.executemany(
        """
        UPDATE entity_edges
        SET valid_to = ?
        WHERE domain = ?
          AND source_kind = ?
          AND ingest_run_id = ?
          AND edge_id = ?
          AND valid_to IS NULL
        """,
        [
            (
                observed_at_utc,
                CATALOG_WORK_GRAPH_DOMAIN,
                CATALOG_WORK_SOURCE_KIND,
                ingest_run_id,
                edge.edge_id,
            )
            for edge in edges
        ],
    )


def _insert_saved_graph_edges(
    *,
    connection: sqlite3.Connection,
    edges: tuple[CatalogSavedGraphEdge, ...],
    ingest_run_id: str,
    observed_at_utc: str,
) -> None:
    _ = connection.executemany(
        """
        INSERT OR REPLACE INTO entity_edges (
        edge_id, domain, edge_kind, from_node_id, to_node_id, payload_json,
        source_kind,
          source_ref, valid_from, valid_to, fingerprint, ingest_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
        """,
        [
            (
                edge.edge_id,
                CATALOG_WORK_GRAPH_DOMAIN,
                edge.edge_kind,
                edge.from_node_id,
                edge.to_node_id,
                edge.payload_text,
                CATALOG_WORK_SOURCE_KIND,
                edge.source_ref,
                observed_at_utc,
                edge.fingerprint,
                ingest_run_id,
            )
            for edge in edges
        ],
    )


def _index_module_intelligence_metadata(
    *,
    connection: sqlite3.Connection,
    run_id: str,
    saves: tuple[CatalogWorkSaveUnit, ...],
    observed_at_utc: str,
) -> None:
    rows = tuple(
        metadata
        for save in saves
        for metadata in _module_intelligence_metadata(
            run_id=run_id,
            save=save,
            observed_at_utc=observed_at_utc,
        )
    )
    if not rows:
        return
    _ = connection.executemany(
        """
        INSERT OR REPLACE INTO catalog_module_intelligence_metadata (
          run_id, unit_id, module_id, input_schema_json, output_schema_json,
          field_constraints_json, error_rate_percentage, api_rate_limit_rpm,
        avg_execution_time_ms, common_error_codes_json, auth_type,
        required_scopes_json,
          token_refresh_supported, output_cardinality, requires_iterator,
          suggested_control_structures_json, operation_cost_multiplier,
        batch_processing_supported, cheaper_alternative_module_id,
        evidence_status,
          source_kind, source_ref, created_at_utc, valid_to, fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
        ?, ?, NULL, ?)
        """,
        [
            (
                row.run_id,
                row.unit_id,
                row.module_id,
                row.input_schema_json,
                row.output_schema_json,
                row.field_constraints_json,
                row.error_rate_percentage,
                row.api_rate_limit_rpm,
                row.avg_execution_time_ms,
                row.common_error_codes_json,
                row.auth_type,
                row.required_scopes_json,
                row.token_refresh_supported,
                row.output_cardinality,
                row.requires_iterator,
                row.suggested_control_structures_json,
                row.operation_cost_multiplier,
                row.batch_processing_supported,
                row.cheaper_alternative_module_id,
                row.evidence_status,
                CATALOG_WORK_SOURCE_KIND,
                row.source_ref,
                observed_at_utc,
                row.fingerprint,
            )
            for row in rows
        ],
    )


def _module_intelligence_metadata(
    *,
    run_id: str,
    save: CatalogWorkSaveUnit,
    observed_at_utc: str,
) -> tuple[CatalogModuleIntelligenceMetadata, ...]:
    value = save.output_json.get("module_semantics")
    if not isinstance(value, list):
        return ()
    rows: list[CatalogModuleIntelligenceMetadata] = []
    for index, item in enumerate(cast("list[object]", value)):
        if not isinstance(item, dict):
            continue
        metadata = {
            str(item_key): item_value
            for item_key, item_value in cast(
                "Mapping[object, object]", item
            ).items()
        }
        module_id = _optional_mapping_text(metadata, "module_id")
        if module_id is None:
            continue
        source_ref = (
            f"sqlite:catalog_unit_outputs/{run_id}/{save.unit_id}"
            f"#module_semantics/{index}"
        )
        derived_metadata = derive_module_intelligence_metadata(metadata)
        row = CatalogModuleIntelligenceMetadata(
            run_id=run_id,
            unit_id=save.unit_id,
            module_id=module_id,
            input_schema_json=derived_metadata.input_schema_json,
            output_schema_json=derived_metadata.output_schema_json,
            field_constraints_json=derived_metadata.field_constraints_json,
            error_rate_percentage=_optional_mapping_float(
                metadata, "error_rate_percentage"
            ),
            api_rate_limit_rpm=_optional_mapping_int(
                metadata, "api_rate_limit_rpm"
            ),
            avg_execution_time_ms=_optional_mapping_int(
                metadata, "avg_execution_time_ms"
            ),
            common_error_codes_json=_optional_json_value_text(
                metadata,
                "common_error_codes ",
                "common_error_codes_json",
            ),
            auth_type=_optional_mapping_text(metadata, "auth_type"),
            required_scopes_json=_optional_json_value_text(
                metadata,
                "required_scopes ",
                "required_scopes_json",
            ),
            token_refresh_supported=_optional_mapping_bool_int(
                metadata,
                "token_refresh_supported",
            ),
            output_cardinality=derived_metadata.output_cardinality,
            requires_iterator=derived_metadata.requires_iterator,
            suggested_control_structures_json=derived_metadata.suggested_control_structures_json,
            operation_cost_multiplier=_optional_mapping_float(
                metadata,
                "operation_cost_multiplier",
            ),
            batch_processing_supported=_optional_mapping_bool_int(
                metadata,
                "batch_processing_supported",
            ),
            cheaper_alternative_module_id=_optional_mapping_text(
                metadata,
                "cheaper_alternative_module_id",
            ),
            evidence_status=(
                _optional_mapping_text(metadata, "evidence_status")
                or _module_intelligence_evidence_status(metadata)
            ),
            source_ref=source_ref,
            fingerprint=_stable_id(
                "catalog-module-intelligence",
                run_id,
                save.unit_id,
                module_id,
                index,
                observed_at_utc,
            ),
        )
        rows.append(row)
    return tuple(rows)


def derive_module_intelligence_metadata(
    metadata: Mapping[str, object],
) -> DerivedModuleIntelligenceMetadata:
    """Derive supported module intelligence metadata from explicit or raw-spec.

    evidence.

    Returns:
    Structural module metadata derivable without live provider calls or
    telemetry guesses.
    """
    return DerivedModuleIntelligenceMetadata(
        input_schema_json=_module_input_schema_json(metadata),
        output_schema_json=_module_output_schema_json(metadata),
        field_constraints_json=_module_field_constraints_json(metadata),
        output_cardinality=_module_output_cardinality(metadata),
        requires_iterator=_module_requires_iterator(metadata),
        suggested_control_structures_json=_module_control_structures_json(
            metadata
        ),
    )


def _module_input_schema_json(metadata: Mapping[str, object]) -> str | None:
    explicit = _optional_json_value_text(
        metadata, "input_schema", "input_schema_json"
    )
    if explicit is not None:
        return explicit
    schema = _raw_spec_schema(
        metadata, keys=("parameters", "expect", "expect_schema")
    )
    return _stable_json_text(schema) if schema else None


def _module_output_schema_json(metadata: Mapping[str, object]) -> str | None:
    explicit = _optional_json_value_text(
        metadata, "output_schema", "output_schema_json"
    )
    if explicit is not None:
        return explicit
    schema = _raw_spec_schema(
        metadata, keys=("interface", "output", "output_schema")
    )
    return _stable_json_text(schema) if schema else None


def _module_field_constraints_json(
    metadata: Mapping[str, object],
) -> str | None:
    explicit = _optional_json_value_text(
        metadata, "field_constraints", "field_constraints_json"
    )
    if explicit is not None:
        return explicit
    constraints = _raw_spec_field_constraints(metadata)
    return _stable_json_value_text(constraints) if constraints else None


def _module_output_cardinality(metadata: Mapping[str, object]) -> str | None:
    explicit = _optional_mapping_text(metadata, "output_cardinality")
    if explicit is not None:
        return explicit
    module_id = _optional_mapping_text(metadata, "module_id") or ""
    operation = _raw_spec_operation(metadata)
    operation_kind = _optional_mapping_text(
        operation, "type"
    ) or _optional_mapping_text(
        operation,
        "module_kind",
    )
    identity = f"{module_id} {operation_kind or ''}".casefold()
    if any(
        marker in identity
        for marker in (":trigger:", ":search:", "trigger", "search")
    ):
        return "multi_bundle"
    if any(marker in identity for marker in (":action:", "action")):
        return "single_bundle"
    return None


def _module_requires_iterator(metadata: Mapping[str, object]) -> int | None:
    explicit = _optional_mapping_bool_int(metadata, "requires_iterator")
    if explicit is not None:
        return explicit
    cardinality = _module_output_cardinality(metadata)
    if cardinality == "multi_bundle":
        return 1
    if cardinality == "single_bundle":
        return 0
    return None


def _module_control_structures_json(
    metadata: Mapping[str, object],
) -> str | None:
    explicit = _optional_json_value_text(
        metadata,
        "suggested_control_structures ",
        "suggested_control_structures_json",
    )
    if explicit is not None:
        return explicit
    requires_iterator = _module_requires_iterator(metadata)
    if requires_iterator is None:
        return None
    structures = ["iterator"] if requires_iterator else ["filter"]
    return _stable_json_value_text(structures)


def _raw_spec_schema(
    metadata: Mapping[str, object],
    *,
    keys: tuple[str, ...],
) -> JsonObject:
    operation = _raw_spec_operation(metadata)
    fields: list[JsonObject] = []
    for key in keys:
        fields.extend(_raw_spec_fields(operation.get(key)))
    return {
        str(field["name"]): {
            key: value
            for key, value in field.items()
            if key != "name" and value is not None
        }
        for field in fields
        if _optional_mapping_text(field, "name") is not None
    }


def _raw_spec_field_constraints(
    metadata: Mapping[str, object],
) -> list[JsonObject]:
    constraints: list[JsonObject] = []
    for field in _raw_spec_fields(
        _raw_spec_operation(metadata).get("parameters")
    ):
        name = _optional_mapping_text(field, "name")
        if name is None:
            continue
        if field.get("required") is True:
            constraints.append({"path": name, "constraint": "required"})
        if any(
            field.get(key) is not None for key in ("enum", "options", "choices")
        ):
            constraints.append({"path": name, "constraint": "finite_options"})
    return constraints


def _raw_spec_operation(metadata: Mapping[str, object]) -> Mapping[str, object]:
    for key in ("raw_spec_operation", "raw_spec", "operation"):
        value = metadata.get(key)
        if isinstance(value, dict):
            return cast("Mapping[str, object]", value)
    return {}


def _raw_spec_fields(value: object) -> list[JsonObject]:
    if isinstance(value, list):
        return [
            _raw_spec_field_payload(cast("Mapping[str, object]", item))
            for item in cast("list[object]", value)
            if isinstance(item, dict)
        ]
    if isinstance(value, dict):
        mapping = cast("Mapping[str, object]", value)
        if _optional_mapping_text(mapping, "name") is not None:
            return [_raw_spec_field_payload(mapping)]
        fields: list[JsonObject] = []
        for key, item in mapping.items():
            if isinstance(item, dict):
                field = _raw_spec_field_payload(
                    cast("Mapping[str, object]", item)
                )
                if field.get("name") is None:
                    field["name"] = key
                fields.append(field)
        return fields
    return []


def _raw_spec_field_payload(field: Mapping[str, object]) -> JsonObject:
    return {
        "name": _optional_mapping_text(field, "name"),
        "type": _optional_mapping_text(field, "type"),
        "label": _optional_mapping_text(field, "label"),
        "required": field.get("required")
        if isinstance(field.get("required"), bool)
        else None,
        "enum": field.get("enum")
        if isinstance(field.get("enum"), list)
        else None,
        "options": field.get("options")
        if isinstance(field.get("options"), list)
        else None,
        "choices": field.get("choices")
        if isinstance(field.get("choices"), list)
        else None,
    }


def _module_intelligence_evidence_status(metadata: Mapping[str, object]) -> str:
    if any(
        key in metadata
        for key in ("raw_spec_operation", "raw_spec", "operation")
    ):
        return "raw_spec_evidence"
    evidence_keys = (
        "input_schema ",
        "input_schema_json ",
        "output_schema ",
        "output_schema_json ",
        "field_constraints ",
        "field_constraints_json ",
        "error_rate_percentage ",
        "api_rate_limit_rpm ",
        "avg_execution_time_ms ",
        "common_error_codes ",
        "common_error_codes_json ",
        "auth_type ",
        "required_scopes ",
        "required_scopes_json ",
        "token_refresh_supported ",
        "output_cardinality ",
        "requires_iterator ",
        "suggested_control_structures ",
        "suggested_control_structures_json ",
        "operation_cost_multiplier ",
        "batch_processing_supported ",
        "cheaper_alternative_module_id ",
        "raw_spec_operation ",
        "raw_spec ",
        "operation",
    )
    if any(key in metadata for key in evidence_keys):
        return "provided_by_catalog_worker"
    return "unknown"


def _graph_ingest_run_id(run_id: str) -> str:
    return f"{CATALOG_WORK_GRAPH_INGEST_RUN_ID_PREFIX}:{run_id}"


def _stable_json_text(payload: Mapping[str, object]) -> str:
    return json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )


def _stable_json_value_text(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )


def _update_unit_notes(
    *,
    connection: sqlite3.Connection,
    run_id: str,
    saves: tuple[CatalogWorkSaveUnit, ...],
    observed_at_utc: str,
) -> None:
    rows = [
        (
            note_text,
            "present" if note_text else "missing",
            observed_at_utc,
            run_id,
            save.unit_id,
            note_surface,
        )
        for save in saves
        for note_surface, note_text in save.notes.items()
    ]
    if not rows:
        return
    _ = connection.executemany(
        """
        UPDATE catalog_unit_notes
        SET note_text = ?,
            note_status = ?,
            updated_at_utc = ?
        WHERE run_id = ?
          AND unit_id = ?
          AND note_surface = ?
        """,
        rows,
    )


def _complete_leased_units(
    *,
    connection: sqlite3.Connection,
    run_id: str,
    saves: tuple[CatalogWorkSaveUnit, ...],
    observed_at_utc: str,
) -> None:
    _ = connection.executemany(
        """
        UPDATE catalog_units
        SET status = ?,
            locked_by = NULL,
            locked_at_utc = NULL,
            lease_expires_at_utc = NULL,
            lease_token = NULL,
            completed_at_utc = ?,
            validation_status = ?,
            coverage_status = ?,
            updated_at_utc = ?
        WHERE run_id = ?
          AND unit_id = ?
        """,
        [
            (
                CATALOG_WORK_STATUS_COMPLETED,
                observed_at_utc,
                save.validation_status,
                save.coverage_status,
                observed_at_utc,
                run_id,
                save.unit_id,
            )
            for save in saves
        ],
    )


def _next_queued_unit_id(
    *, connection: sqlite3.Connection, run_id: str
) -> str | None:
    row = connection.execute(
        """
        SELECT unit_id
        FROM catalog_units
        WHERE run_id = ?
          AND status = ?
        ORDER BY priority_order, unit_id
        LIMIT 1
        """,
        (run_id, CATALOG_WORK_STATUS_QUEUED),
    ).fetchone()
    return (
        None if row is None else _row_text(cast("sqlite3.Row", row), "unit_id")
    )


def _progress_payload(
    *, connection: sqlite3.Connection, run_id: str
) -> JsonObject:
    row = connection.execute(
        """
        SELECT
          total_unit_count,
          completed_unit_count,
          total_complexity_score,
          completed_complexity_score,
          incomplete_unit_count,
          unit_count_progress_ratio,
          weighted_progress_ratio,
          coverage_status
        FROM catalog_run_progress
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()
    if row is None:
        return {
            "run_id": run_id,
            "coverage_status": "unknown",
            "catalog_usable": True,
        }
    typed = cast("sqlite3.Row", row)
    coverage_status = _row_text(typed, "coverage_status")
    total_unit_count = _row_int(typed, "total_unit_count")
    completed_unit_count = _row_int(typed, "completed_unit_count")
    legacy_baseline = _legacy_semantic_baseline_payload(
        connection=connection,
        run_id=run_id,
        active_work_unit_count=total_unit_count,
    )
    return {
        "run_id": run_id,
        "total_unit_count": total_unit_count,
        "active_work_unit_count": total_unit_count,
        "completed_unit_count": completed_unit_count,
        "total_complexity_score": _row_int(typed, "total_complexity_score"),
        "completed_complexity_score": _row_int(
            typed, "completed_complexity_score"
        ),
        "incomplete_unit_count": _row_int(typed, "incomplete_unit_count"),
        "unit_count_progress_ratio": float(typed["unit_count_progress_ratio"]),
        "weighted_progress_ratio": float(typed["weighted_progress_ratio"]),
        "coverage_status": coverage_status,
        "catalog_usable": coverage_status
        in {"complete", "incomplete_non_blocking"},
        "active_unit_granularity": "leaseable_complete_source_units",
        "legacy_semantic_unit_baseline": legacy_baseline,
        "active_unit_source_surfaces": {
            "complete_raw_app_version_specs": True,
            "raw_spec_manifest_records": True,
            "raw_spec_payloads": True,
            "module_operation_fields_inside_raw_specs": True,
            "control_surfaces_first_class_units": list(
                CATALOG_UNIT_NOTE_SURFACES
            ),
            "manifest_and_control_surfaces_not_module_only": True,
        },
        "semantic_graph_output_contract": {
            "semantic_output_per_active_unit": True,
            "graph_output_per_active_unit": True,
            "graph_outputs_expand_answer_payload_not_lease_unit_count": True,
        },
    }


def _legacy_semantic_baseline_payload(
    *,
    connection: sqlite3.Connection,
    run_id: str,
    active_work_unit_count: int,
) -> JsonObject:
    row = connection.execute(
        """
        SELECT legacy_unit_count, legacy_answer_count, obsolete_status
        FROM catalog_legacy_semantic_archives
        WHERE run_id = ?
        ORDER BY archived_at_utc DESC
        LIMIT 1
        """,
        (run_id,),
    ).fetchone()
    if row is None:
        return {
            "legacy_unit_count": 0,
            "legacy_answer_count": 0,
            "obsolete_status": "none",
            "counts_are_comparable": False,
            "active_work_units_less_than_legacy_baseline": False,
            "relationship": "no_legacy_semantic_baseline",
        }
    typed = cast("sqlite3.Row", row)
    legacy_unit_count = _row_int(typed, "legacy_unit_count")
    if legacy_unit_count == 0:
        return {
            "legacy_unit_count": 0,
            "legacy_answer_count": _row_int(typed, "legacy_answer_count"),
            "obsolete_status": "none",
            "counts_are_comparable": False,
            "active_work_units_less_than_legacy_baseline": False,
            "relationship": "no_legacy_semantic_baseline",
        }
    active_less_than_legacy = active_work_unit_count < legacy_unit_count
    return {
        "legacy_unit_count": legacy_unit_count,
        "legacy_answer_count": _row_int(typed, "legacy_answer_count"),
        "obsolete_status": _row_text(typed, "obsolete_status"),
        "counts_are_comparable": False,
        "active_work_units_less_than_legacy_baseline": active_less_than_legacy,
        "relationship": (
            "active_work_units_are_quality_batches_not_legacy_semantic_units"
            if active_less_than_legacy
            else "active_work_units_cover_or_exceed_legacy_semantic_unit_count"
        ),
        "quality_guard": (
            "A lower active work-unit count is allowed only because each "
            "leased unit requires "
            "both semantic and graph output while preserving complete "
            "source payloads."
        ),
    }


def _payload_budget_policy_payload() -> JsonObject:
    return {
        "average_raw_spec_payload_bytes_observed_once": (
            CATALOG_WORK_AVERAGE_RAW_SPEC_PAYLOAD_BYTES
        ),
        "quality_batch_budget_bytes": CATALOG_WORK_DEFAULT_PAYLOAD_BUDGET_BYTES,
        "server_payload_ceiling_bytes": CATALOG_WORK_MAX_PAYLOAD_BUDGET_BYTES,
        "response_overhead_reserve_bytes": (
            CATALOG_WORK_RESPONSE_OVERHEAD_RESERVE_BYTES
        ),
        "estimated_token_budget": (
            CATALOG_WORK_DEFAULT_PAYLOAD_BUDGET_BYTES
            // CATALOG_WORK_ESTIMATED_TOKEN_BYTE_DIVISOR
        ),
        "token_budget_heuristic": (
            "estimated_tokens = ceil(serialized_payload_bytes / 4)"
        ),
        "whole_app_specs_are_fragmented_for_quality": True,
        "default_source_packet_mode": CATALOG_WORK_SOURCE_PACKET_MODE_SUMMARY,
        "complete_source_packets_available_on_request": True,
        "safety_shaped_source_packets_prevent_platform_blocks": True,
        "oversized_complete_operation_is_sent_alone_when_requested": True,
        "quality_floor": (
            "Maximize complete units inside the server budget, but never "
            "lower semantic or graph "
            "quality to increase batch count."
        ),
    }


def _leased_payload(lease: CatalogLeasedPayload) -> JsonObject:
    units = [selected.payload for selected in lease.selected_units]
    return {
        "status": "leased ",
        "response_kind": "catalog_work_next",
        "database_path": DEFAULT_KNOWLEDGE_DB_PATH.as_posix(),
        "sqlite_ssot": True,
        "run_id": lease.run_id,
        "worker_id": lease.worker_id,
        "lease_handle": lease.lease_token,
        "lease_expires_at_utc": lease.lease_expires_at,
        "payload_budget_bytes": lease.payload_budget.bytes,
        "payload_budget_request": lease.payload_budget.request_payload,
        "payload_budget_policy": _payload_budget_policy_payload(),
        "server_payload_ceiling_bytes": CATALOG_WORK_MAX_PAYLOAD_BUDGET_BYTES,
        "server_payload_ceiling_enforced": True,
        "worker_prompt_contract": CATALOG_WORK_PROMPT_CONTRACT,
        "canonical_prompt_trigger": CATALOG_WORK_PROMPT_CONTRACT,
        "accepted_prompt_aliases": list(CATALOG_WORK_PROMPT_ALIASES),
        "worker_instructions": _worker_instructions(),
        "batch_unit_count": len(units),
        "batch_source_size_bytes": sum(
            _json_int(unit, "source_size_bytes") for unit in units
        ),
        "batch_unit_payload_bytes": sum(
            selected.payload_size_bytes for selected in lease.selected_units
        ),
        "batch_complexity_score": sum(
            _json_int(unit, "complexity_score") for unit in units
        ),
        "units": units,
        "one_active_batch_per_worker": True,
        "lease_replay": lease.lease_replay,
        "active_batch_replayed": lease.lease_replay,
        "lease_contract": {
            "save_tool": CATALOG_WORK_SAVE_TOOL_NAME,
            "requires_worker_id": True,
            "requires_lease_handle": True,
            "wrong_worker_or_handle_rejected": True,
            "expired_leases_reclaimable": True,
            "repeat_next_with_same_worker_replays_active_batch": True,
            "legacy_lease_input_supported": True,
        },
        "save_payload_contract": _save_payload_contract(),
        "progress": lease.progress,
        "development_only": True,
        "semantic_worker": CATALOG_WORK_SEMANTIC_WORKER,
        "codex_catalog_authoring_allowed": True,
        "cursor_advanced": not lease.lease_replay,
        "writes_performed": not lease.lease_replay,
        "write_actions": [] if lease.lease_replay else ["lease_catalog_units"],
        "live_make_called": False,
        "provider_api_call": False,
        "credential_value_transfer": False,
        "secret_output": False,
        "parallel_worker_contract": _parallel_worker_contract(),
    }


def _save_payload_contract() -> JsonObject:
    return {
        "preferred_shape": "answers_json.units",
        "batch_shape": {
            "worker_id": "<stable worker_id used for catalog.work.next>",
            "lease_handle": "<lease handle returned by catalog.work.next>",
            "answers_json": {
                "units": [
                    {
                        "unit_id": "<leased unit_id>",
                        "output_json": (
                            "<catalog_intelligence_answer_v1 object>"
                        ),
                    }
                ]
            },
        },
        "save_exactly_all_leased_units": True,
        "single_unit_answer_json_allowed_only_for_single_unit_leases": True,
        "required_unit_fields": ["unit_id", "output_json"],
        "required_save_fields": ["worker_id", "lease_handle", "answers_json"],
        "required_output_fields": [
            "semantic_summary",
            *CATALOG_WORK_REQUIRED_ARRAY_FIELDS,
            "coverage",
        ],
        "coverage_object_required": True,
        "coverage_required_booleans": list(
            CATALOG_WORK_REQUIRED_COVERAGE_BOOLEANS
        ),
        "minimum_output_shape": {
            "schema_version": "catalog_intelligence_answer_v1 ",
            "run_id": "<run_id>",
            "unit_id": "<unit_id>",
            "unit_type": "<unit_type>",
            "source_ref": "<source_ref>",
            "source_hash": "<source_hash>",
            "semantic_summary": "<dense semantic summary>",
            "coverage": {
                "status": "<coverage status>",
                "semantic_output": True,
                "graph_output": True,
                "credential_value_transfer": False,
                "provider_api_call": False,
                "live_make_called": False,
            },
            "module_semantics": [],
            "capability_semantics": [],
            "graph_nodes": [
                {
                    "node_id": "<stable node id>",
                    "entity_kind": "<canonical graph entity kind>",
                    "canonical_label": "<searchable label>",
                    "inference_status": "source_backed_or_inferred",
                }
            ],
            "graph_edges": [
                {
                    "edge_id": "<stable edge id>",
                    "edge_kind": "<canonical graph edge kind>",
                    "from_node_id": "<stable node id>",
                    "to_node_id": "<stable node id>",
                    "inference_status": "source_backed_or_inferred",
                }
            ],
            "quarantine": [],
            "evidence": {},
            "control_surfaces": {},
            "validation": {},
        },
        "quality_floor": (
            "Take the asymmetric search-intelligence bet: save dense "
            "semantic and graph "
            "metadata for each complete leased unit. Aggressively infer "
            "useful graph nodes, "
            "edges, dependencies, capabilities, risks, and workflow "
            "surfaces when local "
            "evidence supports the direction. Label inferred graph records "
            "as inferred. "
            "Never save empty or minimalist graph_nodes or graph_edges."
        ),
        "preview_before_save": {
            "tool": "catalog.semantic.preview ",
            "graph_lookup_tool": "catalog.graph.search",
            "purpose": (
                "Check graph density, disconnected edges, and preview query "
                "matches."
            ),
        },
        "atomicity": {
            "save_entire_leased_batch": True,
            "partial_leased_batch_saves_rejected": True,
        },
    }


def _parallel_worker_contract() -> JsonObject:
    return {
        "many_workers_supported": True,
        "stable_worker_id_required": True,
        "one_active_batch_per_worker": True,
        "same_worker_replays_active_batch": True,
        "different_workers_lease_different_queued_units": True,
        "save_entire_leased_batch_atomically": True,
        "report_batch_level_progress_only": True,
    }


def _worker_instructions() -> str:
    return (
        "Build your own future Make.com workflow intelligence brain. "
        "Process the maximum "
        "complete batch the returned lease allows. Use catalog.graph.search "
        "and "
        "catalog.semantic.preview before saving when graph fit is "
        "uncertain. Take the "
        "asymmetric bet: aggressively infer useful graph nodes, graph "
        "edges, dependencies, "
        "capabilities, risks, workflow surfaces, and related modules for "
        "search intelligence, "
        "but label inferred records as inferred. Never save empty or "
        "minimalist graph output. "
        "Save the entire leased batch atomically with catalog.work.save, "
        "then immediately lease "
        "the next largest safe batch while context and tooling allow. "
        "Report only batch-level "
        "progress, validation blockers, and current counters. "
        "Do not call providers, call live Make.com, transfer credentials, "
        "or fabricate "
        "credential values, telemetry, auth scopes, schemas, or runtime facts."
    )


def _complete_payload(
    *,
    run_id: str,
    worker_id: str,
    payload_budget: CatalogWorkPayloadBudget,
    progress: JsonObject,
) -> JsonObject:
    return {
        "status": "complete ",
        "response_kind": "catalog_work_next",
        "database_path": DEFAULT_KNOWLEDGE_DB_PATH.as_posix(),
        "sqlite_ssot": True,
        "run_id": run_id,
        "worker_id": worker_id,
        "payload_budget_bytes": payload_budget.bytes,
        "payload_budget_request": payload_budget.request_payload,
        "payload_budget_policy": _payload_budget_policy_payload(),
        "server_payload_ceiling_bytes": CATALOG_WORK_MAX_PAYLOAD_BUDGET_BYTES,
        "server_payload_ceiling_enforced": True,
        "worker_prompt_contract": CATALOG_WORK_PROMPT_CONTRACT,
        "canonical_prompt_trigger": CATALOG_WORK_PROMPT_CONTRACT,
        "accepted_prompt_aliases": list(CATALOG_WORK_PROMPT_ALIASES),
        "worker_instructions": _worker_instructions(),
        "batch_unit_count": 0,
        "units": [],
        "one_active_batch_per_worker": True,
        "lease_replay": False,
        "active_batch_replayed": False,
        "lease_contract": {
            "save_tool": CATALOG_WORK_SAVE_TOOL_NAME,
            "requires_worker_id": True,
            "requires_lease_handle": True,
            "wrong_worker_or_handle_rejected": True,
            "expired_leases_reclaimable": True,
            "repeat_next_with_same_worker_replays_active_batch": True,
            "legacy_lease_input_supported": True,
        },
        "save_payload_contract": _save_payload_contract(),
        "progress": progress,
        "development_only": True,
        "semantic_worker": CATALOG_WORK_SEMANTIC_WORKER,
        "codex_catalog_authoring_allowed": True,
        "cursor_advanced": False,
        "writes_performed": False,
        "write_actions": [],
        "live_make_called": False,
        "provider_api_call": False,
        "credential_value_transfer": False,
        "secret_output": False,
        "parallel_worker_contract": _parallel_worker_contract(),
    }


def _unit_payload(
    row: sqlite3.Row,
    *,
    existing_active_lease: bool = False,
    source_packet_mode: str = CATALOG_WORK_SOURCE_PACKET_MODE_SUMMARY,
) -> JsonObject:
    attempt_count = _row_int(row, "attempt_count")
    payload: JsonObject = {
        "run_id": _row_text(row, "run_id"),
        "unit_id": _row_text(row, "unit_id"),
        "unit_type": _row_text(row, "unit_type"),
        "priority_band": _row_text(row, "priority_band"),
        "priority_order": _row_int(row, "priority_order"),
        "source_ref": _bounded_source_ref(_row_text(row, "source_ref")),
        "source_hash": _row_text(row, "source_hash"),
        "source_size_bytes": _row_int(row, "source_size_bytes"),
        "complexity_score": _row_int(row, "complexity_score"),
        "status": CATALOG_WORK_STATUS_WORKING,
        "attempt_count": attempt_count
        if existing_active_lease
        else attempt_count + 1,
        "validation_status": _row_text(row, "validation_status"),
        "coverage_status": _row_text(row, "coverage_status"),
        "note_surfaces": list(CATALOG_UNIT_NOTE_SURFACES),
    }
    source_evidence = _raw_spec_source_evidence(row)
    if source_evidence is not None:
        payload["source_evidence"] = source_evidence
        source_packet = _raw_spec_source_packet(
            row, source_packet_mode=source_packet_mode
        )
        if source_packet is not None:
            payload["source_packet"] = source_packet
            payload["source_packet_policy"] = {
                "source_packet_mode": source_packet_mode,
                "complete_packet_included": (
                    source_packet_mode
                    == CATALOG_WORK_SOURCE_PACKET_MODE_COMPLETE
                ),
                "safety_shaped_summary_default": True,
                "complete_operation_objects_available_on_request": True,
                "oversized_operation_sent_alone_when_requested": True,
                "whole_app_specs_are_fragmented_for_quality": True,
            }
    control_surface_evidence = _control_surface_evidence(row)
    if control_surface_evidence is not None:
        payload["control_surface_evidence"] = control_surface_evidence
    return payload


def _raw_spec_source_evidence(row: sqlite3.Row) -> JsonObject | None:
    app_slug = _row_text(row, "app_slug")
    if not app_slug:
        return None
    return {
        "evidence_kind": "raw_make_app_version_spec",
        "app_slug": app_slug,
        "app_version": _row_text(row, "app_version"),
        "app_label": _row_text(row, "app_label"),
        "latest": bool(_row_int(row, "latest")),
        "module_count": _row_int(row, "module_count"),
        "module_kinds": _json_array_text(row, "module_kinds_json"),
        "source_metadata": _json_object_text(row, "source_metadata_json"),
        "source_ref": _bounded_source_ref(_row_text(row, "source_ref")),
        "source_size_bytes": _row_int(row, "source_size_bytes"),
        "payload_source_type": _row_text(row, "payload_source_type"),
        "payload_is_truncated": bool(_row_int(row, "payload_is_truncated")),
        "payload_truncation_reason": _row_text(
            row, "payload_truncation_reason"
        ),
        "payload_sanitization_status": _row_text(
            row, "payload_sanitization_status"
        ),
        "payload_detail_policy": (
            "Whole app-version specs are split into manifest and "
            "operation-batch packets. "
            "Catalog work defaults to safety-shaped operation summaries so "
            "ChatGPT can read "
            "leases reliably; exact raw source remains addressed by "
            "source_ref and source_hash."
        ),
    }


def _raw_spec_source_packet(
    row: sqlite3.Row, *, source_packet_mode: str
) -> JsonObject | None:
    value = _row_text(row, "payload_json")
    if not value:
        return None
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        message = (
            "Catalog work raw spec payload_json must decode to a JSON object."
        )
        raise TypeError(message)
    source_ref = _row_text(row, "source_ref")
    if "#manifest" in source_ref:
        return _raw_spec_manifest_packet(
            cast("JsonObject", parsed),
            source_packet_mode=source_packet_mode,
        )
    if "#operations/" in source_ref:
        return _raw_spec_operation_packet(
            cast("JsonObject", parsed),
            source_ref=source_ref,
            source_packet_mode=source_packet_mode,
        )
    return {
        "packet_kind": "raw_spec_requires_fragmented_reset",
        "source_ref": source_ref,
        "detail_policy": (
            "This coarse legacy raw-spec unit should be superseded by "
            "manifest and operation "
            "batch units before worker authoring."
        ),
    }


def _raw_spec_manifest_packet(
    payload: JsonObject,
    *,
    source_packet_mode: str,
) -> JsonObject:
    app = payload.get("app")
    if not isinstance(app, dict):
        return {
            "packet_kind": "app_manifest",
            "source_packet_mode": source_packet_mode,
            "app_manifest": _safe_worker_packet(payload),
            "operation_collections": {},
        }
    app_payload = {
        str(key): item
        for key, item in cast("Mapping[object, object]", app).items()
    }
    manifest: JsonObject = {}
    operation_collections: dict[str, JsonObject] = {}
    for key, item in app_payload.items():
        if isinstance(item, list):
            operation_values = cast("list[object]", item)
            operation_collections[key] = {
                "operation_count": len(operation_values)
            }
            continue
        manifest[_safe_worker_key(key)] = _safe_worker_packet(item)
    return {
        "packet_kind": "app_manifest",
        "source_packet_mode": source_packet_mode,
        "app_manifest": manifest,
        "operation_collections": operation_collections,
    }


def _raw_spec_operation_packet(
    payload: JsonObject,
    *,
    source_ref: str,
    source_packet_mode: str,
) -> JsonObject:
    collection, start_index, end_index = _operation_packet_selector(source_ref)
    app = payload.get("app")
    if not isinstance(app, dict):
        return {
            "packet_kind": "operation_batch",
            "source_packet_mode": source_packet_mode,
            "collection": collection,
            "operations": [],
        }
    app_payload = {
        str(key): item
        for key, item in cast("Mapping[object, object]", app).items()
    }
    collection_value = app_payload.get(collection)
    if not isinstance(collection_value, list):
        return {
            "packet_kind": "operation_batch",
            "source_packet_mode": source_packet_mode,
            "collection": collection,
            "operations": [],
        }
    operations = cast("list[object]", collection_value)[
        start_index : end_index + 1
    ]
    packet: JsonObject = {
        "packet_kind": "operation_batch",
        "source_packet_mode": source_packet_mode,
        "collection": collection,
        "start_index": start_index,
        "end_index": end_index,
        "operation_count": len(operations),
        "sensitive_marker_policy": (
            "Credential-marker strings and fields are normalized for MCP "
            "safety; "
            "exact raw source remains available by source_ref and source_hash."
        ),
    }
    if source_packet_mode == CATALOG_WORK_SOURCE_PACKET_MODE_COMPLETE:
        packet["operations"] = [
            _safe_worker_packet(operation) for operation in operations
        ]
        return packet
    packet["operation_summaries"] = [
        _raw_spec_operation_summary(operation) for operation in operations
    ]
    packet["complete_operations_included"] = False
    return packet


def _raw_spec_operation_summary(value: object) -> JsonObject:
    if not isinstance(value, dict):
        return {"operation_shape": type(value).__name__}
    operation = {
        str(key): item
        for key, item in cast("Mapping[object, object]", value).items()
    }
    return {
        "internal_name": _safe_worker_text(str(operation.get("name", ""))),
        "label": _safe_worker_text(str(operation.get("label", ""))),
        "description": _safe_worker_snippet(
            str(operation.get("description", ""))
        ),
        "field_groups": {
            "parameters": _raw_spec_field_summaries(
                operation.get("parameters")
            ),
            "expect": _raw_spec_field_summaries(operation.get("expect")),
            "interface": _raw_spec_field_summaries(operation.get("interface")),
        },
    }


def _raw_spec_field_summaries(value: object) -> list[JsonObject]:
    if not isinstance(value, list):
        return []
    fields: list[JsonObject] = []
    for item in cast("list[object]", value):
        if not isinstance(item, dict):
            continue
        field = {
            str(key): field_value
            for key, field_value in cast(
                "Mapping[object, object]", item
            ).items()
        }
        fields.append(
            {
                "internal_name": _safe_worker_text(str(field.get("name", ""))),
                "label": _safe_worker_text(str(field.get("label", ""))),
                "type": _safe_worker_text(str(field.get("type", ""))),
                "required": bool(field.get("required")),
            }
        )
    return fields


def _operation_packet_selector(source_ref: str) -> tuple[str, int, int]:
    selector = source_ref.split("#operations/", 1)[1]
    collection, bounds = selector.split("/", 1)
    start_text, end_text = bounds.split("-", 1)
    return collection, int(start_text), int(end_text)


def _safe_worker_packet(value: object) -> object:
    if isinstance(value, dict):
        return {
            _safe_worker_key(str(key)): _safe_worker_packet(item)
            for key, item in cast("Mapping[object, object]", value).items()
        }
    if isinstance(value, list):
        return [
            _safe_worker_packet(item) for item in cast("list[object]", value)
        ]
    if isinstance(value, str):
        return _safe_worker_text(value)
    return value


def _safe_worker_key(key: str) -> str:
    if key == "name":
        return "internal_name"
    if CATALOG_WORK_SECRET_MARKER_PATTERN.search(key):
        return f"credential_marker_field_{_sha256_text(key)[:8]}"
    return _safe_worker_text(key)


def _safe_worker_text(value: str) -> str:
    value = value.replace("__IMTCONN__", "[MAKE_CONNECTION_REFERENCE]")
    return CATALOG_WORK_SECRET_MARKER_PATTERN.sub(
        _secret_marker_replacement, value
    )


def _safe_worker_snippet(value: str) -> str:
    text = _safe_worker_text(value)
    if len(text) <= MAX_SOURCE_PACKET_SUMMARY_CHARS:
        return text
    return f"{text[: MAX_SOURCE_PACKET_SUMMARY_CHARS - 3]}..."


def _secret_marker_replacement(match: re.Match[str]) -> str:
    _ = match
    return "credential marker"


def _control_surface_evidence(row: sqlite3.Row) -> JsonObject | None:
    source_ref = _row_text(row, "source_ref")
    if not source_ref.startswith(CATALOG_CONTROL_SURFACE_SOURCE_PREFIX):
        return None
    surface = source_ref[len(CATALOG_CONTROL_SURFACE_SOURCE_PREFIX) :]
    return catalog_control_surface_payload(surface)


def _payload_budget(value: object) -> CatalogWorkPayloadBudget:
    if value is None:
        return CatalogWorkPayloadBudget(
            bytes=CATALOG_WORK_DEFAULT_PAYLOAD_BUDGET_BYTES,
            request_payload={
                "requested_payload_budget_bytes": None,
                "effective_payload_budget_bytes": (
                    CATALOG_WORK_DEFAULT_PAYLOAD_BUDGET_BYTES
                ),
                "interpretation": "default_payload_budget",
            },
        )
    if isinstance(value, bool) or not isinstance(value, int):
        message = "payload_budget_bytes must be an integer."
        raise TypeError(message)
    if value < CATALOG_WORK_MIN_PAYLOAD_BUDGET_BYTES:
        if 0 < value <= SMALL_PROMPT_COUNT_PAYLOAD_HINT_MAX:
            return CatalogWorkPayloadBudget(
                bytes=CATALOG_WORK_DEFAULT_PAYLOAD_BUDGET_BYTES,
                request_payload={
                    "requested_payload_budget_bytes": value,
                    "effective_payload_budget_bytes": (
                        CATALOG_WORK_DEFAULT_PAYLOAD_BUDGET_BYTES
                    ),
                    "interpretation": (
                        "small_integer_treated_as_prompt_unit_count_hint"
                    ),
                },
            )
        message = "payload_budget_bytes must be positive."
        raise ValueError(message)
    effective_budget = min(value, CATALOG_WORK_MAX_PAYLOAD_BUDGET_BYTES)
    return CatalogWorkPayloadBudget(
        bytes=effective_budget,
        request_payload={
            "requested_payload_budget_bytes": value,
            "effective_payload_budget_bytes": effective_budget,
            "interpretation": (
                "server_ceiling_applied"
                if effective_budget != value
                else "requested_payload_budget_bytes"
            ),
        },
    )


def _required_worker_id(arguments: Mapping[str, object]) -> str:
    worker_id = _required_text(arguments, "worker_id")
    if len(worker_id) > MAX_WORKER_ID_CHARS:
        message = "worker_id is too long."
        raise ValueError(message)
    if any(char not in TEXT_ARGUMENT_ALLOWED_CHARS for char in worker_id):
        message = "worker_id contains unsupported characters."
        raise ValueError(message)
    return worker_id


def _required_text(arguments: Mapping[str, object], key: str) -> str:
    text = _optional_text(arguments.get(key))
    if text is None:
        message = f"missing_required_argument: {key}"
        raise ValueError(message)
    return text


def _required_lease_handle(arguments: Mapping[str, object]) -> str:
    handle = _optional_text(arguments.get(CATALOG_WORK_LEASE_HANDLE_FIELD))
    if handle is not None:
        return handle
    legacy_value = _optional_text(
        arguments.get(CATALOG_WORK_LEGACY_LEASE_FIELD)
    )
    if legacy_value is not None:
        return legacy_value
    message = f"missing_required_argument: {CATALOG_WORK_LEASE_HANDLE_FIELD}"
    raise ValueError(message)


def _required_mapping_text(mapping: Mapping[str, object], key: str) -> str:
    text = _optional_text(mapping.get(key))
    if text is None:
        message = f"missing_required_field: {key}"
        raise ValueError(message)
    return text


def _optional_mapping_text(
    mapping: Mapping[str, object], key: str
) -> str | None:
    return _optional_text(mapping.get(key))


def _optional_mapping_int(
    mapping: Mapping[str, object], key: str
) -> int | None:
    value = mapping.get(key)
    if value is None or _unknown_text_value(value):
        return None
    if isinstance(value, bool):
        message = f"{key} must be an integer or null."
        raise TypeError(message)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    message = f"{key} must be an integer or null."
    raise TypeError(message)


def _optional_mapping_float(
    mapping: Mapping[str, object], key: str
) -> float | None:
    value = mapping.get(key)
    if value is None or _unknown_text_value(value):
        return None
    if isinstance(value, bool):
        message = f"{key} must be a number or null."
        raise TypeError(message)
    if isinstance(value, (int, float)):
        return float(value)
    message = f"{key} must be a number or null."
    raise TypeError(message)


def _optional_mapping_bool_int(
    mapping: Mapping[str, object], key: str
) -> int | None:
    value = mapping.get(key)
    if value is None or _unknown_text_value(value):
        return None
    if isinstance(value, bool):
        return int(value)
    message = f"{key} must be a boolean or null."
    raise TypeError(message)


def _optional_bool(value: object) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        message = "Boolean arguments must be true or false."
        raise TypeError(message)
    return value


def _source_packet_mode(value: object) -> str:
    if value is None:
        return CATALOG_WORK_SOURCE_PACKET_MODE_SUMMARY
    if not isinstance(value, str):
        message = f"{CATALOG_WORK_SOURCE_PACKET_MODE_FIELD} must be a string."
        raise TypeError(message)
    mode = value.strip().casefold()
    if mode not in CATALOG_WORK_SOURCE_PACKET_MODES:
        allowed = ", ".join(sorted(CATALOG_WORK_SOURCE_PACKET_MODES))
        message = (
            f"Unsupported source_packet_mode {mode!r}; expected {allowed}."
        )
        raise ValueError(message)
    return mode


def _optional_json_value_text(
    mapping: Mapping[str, object], *keys: str
) -> str | None:
    for key in keys:
        if key not in mapping:
            continue
        value = mapping[key]
        if value is None:
            return None
        if isinstance(value, str) and key.endswith("_json") and value.strip():
            try:
                parsed = cast("object", json.loads(value))
            except json.JSONDecodeError:
                return _stable_json_value_text(value)
            return _stable_json_value_text(parsed)
        return _stable_json_value_text(value)
    return None


def _unknown_text_value(value: object) -> bool:
    return isinstance(value, str) and value.strip().casefold() in {
        "unknown ",
        "null ",
        "n/a",
    }


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        message = "Text arguments must be strings."
        raise TypeError(message)
    text = value.strip()
    return text or None


def _json_object_argument(value: object, *, field_name: str) -> JsonObject:
    if isinstance(value, dict):
        return {
            str(key): item
            for key, item in cast("Mapping[object, object]", value).items()
        }
    if not isinstance(value, str) or not value.strip():
        message = f"{field_name} must be a JSON object."
        raise ValueError(message)
    parsed = cast("object", json.loads(value))
    if not isinstance(parsed, dict):
        message = f"{field_name} must decode to a JSON object."
        raise TypeError(message)
    return {
        str(key): item
        for key, item in cast("Mapping[object, object]", parsed).items()
    }


def _sqlite_table_exists(
    *, connection: sqlite3.Connection, table_name: str
) -> bool:
    row = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type IN ('table', 'view') AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _table_has_column(
    *,
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    if not _sqlite_table_exists(connection=connection, table_name=table_name):
        return False
    rows = connection.execute(
        f"PRAGMA table_info({_safe_identifier(table_name)})"
    ).fetchall()
    return any(row[1] == column_name for row in rows)


def _replace_text_if_column(
    *,
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    old_value: str,
    new_value: str,
) -> None:
    if not _table_has_column(
        connection=connection,
        table_name=table_name,
        column_name=column_name,
    ):
        return
    table = _safe_identifier(table_name)
    column = _safe_identifier(column_name)
    _ = connection.execute(
        f"""  # noqa: S608
        UPDATE {table}
        SET {column} = replace({column}, ?, ?)
        WHERE {column} LIKE ?
        """,
        (old_value, new_value, f"%{old_value}%"),
    )


def _safe_identifier(value: str) -> str:
    if SQLITE_IDENTIFIER_PATTERN.fullmatch(value) is None:
        message = (
            f"Unsafe SQLite identifier in catalog work migration: {value!r}"
        )
        raise ValueError(message)
    return f'"{value}"'


def _row_text(row: sqlite3.Row, key: str) -> str:
    value = cast("object", row[key])
    return "" if value is None else str(value)


def _row_int(row: sqlite3.Row, key: str) -> int:
    value = cast("object", row[key])
    if isinstance(value, bool):
        message = f"Catalog work column {key} must be an integer."
        raise TypeError(message)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    message = f"Catalog work column {key} must be an integer."
    raise TypeError(message)


def _json_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        message = f"Catalog work payload field {key} must be an integer."
        raise TypeError(message)
    return value


def _json_array_text(row: sqlite3.Row, key: str) -> list[object]:
    value = _row_text(row, key)
    if not value:
        return []
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        message = f"Catalog work column {key} must decode to a JSON array."
        raise TypeError(message)
    return cast("list[object]", parsed)


def _json_object_text(row: sqlite3.Row, key: str) -> JsonObject:
    value = _row_text(row, key)
    if not value:
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        message = f"Catalog work column {key} must decode to a JSON object."
        raise TypeError(message)
    return {
        str(item_key): item
        for item_key, item in cast("Mapping[object, object]", parsed).items()
    }


def _bounded_source_ref(source_ref: str) -> str:
    if len(source_ref) <= MAX_SOURCE_REF_CHARS:
        return source_ref
    return f"{source_ref[:MAX_SOURCE_REF_CHARS]} [truncated]"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _utc_after(*, seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()


def _stable_id(*parts: object) -> str:
    payload = json.dumps(parts, ensure_ascii=True, sort_keys=True, default=str)
    return _sha256_text(payload)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
