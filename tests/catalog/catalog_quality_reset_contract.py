# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contracts for canonical catalog run state.

Boundary contract:
- Owns: active catalog reset schema, priority ordering, notes, and progress
assertions.
- Must not: author semantic catalog answers, call providers, or use live
Make.com state.
- Allows: in-memory SQLite schemas and synthetic catalog unit source fixtures.
- Split when: lease-based catalog worker mutation behavior moves to MCP tool
tests.
- Merge when: catalog-plan SSOT tests own the same reset-run contract directly.
"""

from __future__ import annotations

import hashlib
import sqlite3
from typing import cast

from catalog.knowledge import (
    CATALOG_UNIT_NOTE_SURFACES,
    CatalogResetUnitInput,
    catalog_quality_progress,
    catalog_reset_units_from_raw_specs,
    start_catalog_quality_reset_run,
)
from catalog.knowledge.catalog_quality_reset import (
    CATALOG_INCOMPLETE_COVERAGE_POLICY,
    CATALOG_OLD_SEMANTIC_STATUS,
)
from catalog.knowledge.schema import read_engine_schema_sql

OBSERVED_AT = "2026-05-21T00:00:00+00:00"
FLOAT_TOLERANCE = 0.000001
REQUIRED_UNIT_CONTRACT_FIELDS = {
    "run_id ",
    "unit_id ",
    "unit_type ",
    "priority_band ",
    "priority_order ",
    "source_ref ",
    "source_hash ",
    "source_size_bytes ",
    "complexity_score ",
    "status ",
    "locked_by ",
    "locked_at_utc ",
    "lease_expires_at_utc ",
    "lease_token ",
    "attempt_count ",
    "completed_at_utc ",
    "validation_status ",
    "coverage_status",
}
REQUIRED_MUTATION_TABLES = {
    "catalog_unit_outputs ",
    "catalog_module_intelligence_metadata ",
    "catalog_modification_events ",
    "catalog_edge_proposals ",
    "catalog_review_records",
}
REQUIRED_MODULE_INTELLIGENCE_FIELDS = {
    "run_id ",
    "unit_id ",
    "module_id ",
    "input_schema_json ",
    "output_schema_json ",
    "field_constraints_json ",
    "error_rate_percentage ",
    "api_rate_limit_rpm ",
    "avg_execution_time_ms ",
    "common_error_codes_json ",
    "auth_type ",
    "required_scopes_json ",
    "token_refresh_supported ",
    "output_cardinality ",
    "requires_iterator ",
    "suggested_control_structures_json ",
    "operation_cost_multiplier ",
    "batch_processing_supported ",
    "cheaper_alternative_module_id ",
    "evidence_status",
}


def test_catalog_quality_reset_schema_has_fixed_unit_contract() -> None:
    """The canonical catalog unit table owns the fixed queue contract fields."""
    connection = _schema_connection()
    try:
        columns = _table_columns(connection, "catalog_units")
    finally:
        connection.close()

    assert columns >= REQUIRED_UNIT_CONTRACT_FIELDS


def test_catalog_quality_reset_schema_has_typed_mutation_tables() -> None:
    """Catalog write tooling has typed tables rather than raw SQL mutation.

    access.
    """
    connection = _schema_connection()
    try:
        table_names = _table_names(connection)
    finally:
        connection.close()

    assert table_names >= REQUIRED_MUTATION_TABLES


def test_catalog_quality_reset_schema_has_dbbfe542() -> None:
    """Gemini-style module intelligence fields are typed but evidence-gapped by.

    default.
    """
    connection = _schema_connection()
    try:
        columns = _table_columns(
            connection, "catalog_module_intelligence_metadata"
        )
    finally:
        connection.close()

    assert columns >= REQUIRED_MODULE_INTELLIGENCE_FIELDS


def test_catalog_quality_reset_starts_active_14770675() -> None:
    """A reset run preserves old semantic progress only as obsolete archive.

    evidence.
    """
    connection = _schema_connection()
    try:
        _insert_legacy_catalog_progress(connection)

        report = start_catalog_quality_reset_run(
            connection=connection,
            run_id="catalog-run-2026-05-21",
            units=(_unit("unit-make-builtins", "make_builtins_core", 10),),
            source_ref="synthetic:catalog-reset-test",
            observed_at_utc=OBSERVED_AT,
        )
        legacy_unit_count = _scalar_int(
            connection, "SELECT COUNT(*) FROM catalog_plan_units"
        )
        archive_row = cast(
            "tuple[str, int, int]",
            connection.execute(
                """
                SELECT obsolete_status, legacy_unit_count, legacy_answer_count
                FROM catalog_legacy_semantic_archives
                WHERE run_id = ?
                """,
                ("catalog-run-2026-05-21",),
            ).fetchone(),
        )
    finally:
        connection.close()

    assert report.old_semantic_status == CATALOG_OLD_SEMANTIC_STATUS
    assert (
        report.incomplete_coverage_policy == CATALOG_INCOMPLETE_COVERAGE_POLICY
    )
    assert report.legacy_unit_count == 1
    assert report.legacy_answer_count == 1
    assert legacy_unit_count == 1
    assert archive_row == (CATALOG_OLD_SEMANTIC_STATUS, 1, 1)


def test_catalog_quality_reset_orders_units_ec0f2006() -> None:
    """Priority bands win first, then heavier unit types and deterministic app.

    order.
    """
    connection = _schema_connection()
    try:
        _ = start_catalog_quality_reset_run(
            connection=connection,
            run_id="catalog-run-ordering",
            units=(
                _unit(
                    "unit-z-remainder ",
                    "alphabetical_remainder",
                    20,
                    source_ref="apps/zendesk",
                ),
                _unit("unit-ai", "make_ai_agents_tools_providers", 90),
                _unit(
                    "unit-a-remainder ",
                    "alphabetical_remainder",
                    20,
                    source_ref="apps/asana",
                ),
                _unit(
                    "unit-control-module", "make_control_data_structures", 30
                ),
                _unit("unit-popular", "popular_apps", 70),
                _unit("unit-builtins-module", "make_builtins_core", 10),
                _unit(
                    "unit-control-raw ",
                    "make_control_data_structures",
                    5,
                    unit_type="raw_spec",
                ),
                _unit(
                    "unit-builtins-raw ",
                    "make_builtins_core",
                    100,
                    unit_type="raw_spec",
                ),
            ),
            source_ref="synthetic:catalog-reset-ordering-test",
            observed_at_utc=OBSERVED_AT,
        )
        rows = cast(
            "list[tuple[str]]",
            connection.execute(
                """
                SELECT unit_id
                FROM catalog_units
                WHERE run_id = ?
                ORDER BY priority_order
                """,
                ("catalog-run-ordering",),
            ).fetchall(),
        )
    finally:
        connection.close()

    assert [row[0] for row in rows] == [
        "unit-builtins-raw ",
        "unit-builtins-module ",
        "unit-control-raw ",
        "unit-control-module ",
        "unit-ai ",
        "unit-popular ",
        "unit-a-remainder ",
        "unit-z-remainder",
    ]


def test_catalog_quality_reset_orders_requested_raw_spec_groups() -> None:
    """Built-ins, control notes, Make AI, popular apps, and remainder keep.

    fixed.

    order.
    """
    connection = _schema_connection()
    try:
        _ = start_catalog_quality_reset_run(
            connection=connection,
            run_id="catalog-run-requested-ordering",
            units=(
                _raw_spec_unit(
                    "raw-spec:z-remainder:1.0.0", "alphabetical_remainder"
                ),
                _raw_spec_unit("raw-spec:facebook-pages:1.0.0", "popular_apps"),
                _raw_spec_unit(
                    "raw-spec:ai-tools:1.0.0", "make_ai_agents_tools_providers"
                ),
                _raw_spec_unit(
                    "raw-spec:datastore:1.0.0", "make_builtins_core"
                ),
                _raw_spec_unit("raw-spec:http:1.0.0", "make_builtins_core"),
                _raw_spec_unit("raw-spec:builtin:1.0.0", "make_builtins_core"),
                _unit("unit-filter-notes", "make_control_data_structures", 50),
            ),
            source_ref="synthetic:catalog-reset-requested-ordering-test",
            observed_at_utc=OBSERVED_AT,
        )
        rows = cast(
            "list[tuple[str, str, int]]",
            connection.execute(
                """
                SELECT unit_id, priority_band, priority_order
                FROM catalog_units
                WHERE run_id = ?
                ORDER BY priority_order
                """,
                ("catalog-run-requested-ordering",),
            ).fetchall(),
        )
    finally:
        connection.close()

    assert rows == [
        ("raw-spec:builtin:1.0.0", "make_builtins_core", 1),
        ("raw-spec:http:1.0.0", "make_builtins_core", 2),
        ("raw-spec:datastore:1.0.0", "make_builtins_core", 3),
        ("unit-filter-notes", "make_control_data_structures", 4),
        ("raw-spec:ai-tools:1.0.0", "make_ai_agents_tools_providers", 5),
        ("raw-spec:facebook-pages:1.0.0", "popular_apps", 6),
        ("raw-spec:z-remainder:1.0.0", "alphabetical_remainder", 7),
    ]


def test_catalog_quality_reset_orders_operator_named_builtin_aliases() -> None:
    """Operator-facing Make built-in slugs stay ahead of control, AI, popular,.

    and remainder.
    """
    connection = _schema_connection()
    try:
        for app_slug, app_label in (
            ("asana", "Asana"),
            ("brevo", "Brevo"),
            ("flow-control", "Flow Control"),
            ("http", "HTTP"),
            ("make-ai-agents", "Make AI Agents"),
            ("make-ai-toolkit", "Make AI Toolkit"),
            ("microsoft-365-email-outlook", "Microsoft 365 Email (Outlook)"),
            ("text-parser", "Text parser"),
            ("tools", "Tools"),
            ("webhooks", "Webhooks"),
        ):
            _insert_raw_spec_manifest_row(
                connection,
                app_slug=app_slug,
                app_label=app_label,
            )

        connection.row_factory = sqlite3.Row
        units = catalog_reset_units_from_raw_specs(connection=connection)
        _ = start_catalog_quality_reset_run(
            connection=connection,
            run_id="catalog-run-operator-alias-ordering",
            units=units,
            source_ref="synthetic:catalog-reset-operator-alias-ordering-test",
            observed_at_utc=OBSERVED_AT,
        )
        connection.row_factory = None
        rows = cast(
            "list[tuple[str, str]]",
            connection.execute(
                """
                SELECT unit_id, priority_band
                FROM catalog_units
                WHERE run_id = ?
                ORDER BY priority_order
                """,
                ("catalog-run-operator-alias-ordering",),
            ).fetchall(),
        )
    finally:
        connection.close()

    assert rows == [
        ("raw-spec:flow-control:1.0.0", "make_builtins_core"),
        ("raw-spec:tools:1.0.0", "make_builtins_core"),
        ("raw-spec:text-parser:1.0.0", "make_builtins_core"),
        ("raw-spec:webhooks:1.0.0", "make_builtins_core"),
        ("raw-spec:http:1.0.0", "make_builtins_core"),
        *[
            (f"control-surface:{surface}", "make_control_data_structures")
            for surface in CATALOG_UNIT_NOTE_SURFACES
        ],
        ("raw-spec:make-ai-agents:1.0.0", "make_ai_agents_tools_providers"),
        ("raw-spec:make-ai-toolkit:1.0.0", "make_ai_agents_tools_providers"),
        ("raw-spec:microsoft-365-email-outlook:1.0.0", "popular_apps"),
        ("raw-spec:brevo:1.0.0", "popular_apps"),
        ("raw-spec:asana:1.0.0", "alphabetical_remainder"),
    ]


def test_catalog_quality_reset_classifies_raw_specs_by_operator_priority() -> (
    None
):
    """Current raw specs are classified into the operator's requested priority.

    bands.
    """
    connection = _schema_connection()
    try:
        _insert_raw_spec_manifest_row(
            connection, app_slug="builtin", app_label="Flow Control"
        )
        _insert_raw_spec_manifest_row(
            connection, app_slug="ai-tools", app_label="Make AI Toolkit"
        )
        _insert_raw_spec_manifest_row(
            connection,
            app_slug="anthropic-claude",
            app_label="Anthropic Claude",
        )
        _insert_raw_spec_manifest_row(
            connection, app_slug="asana", app_label="Asana"
        )

        connection.row_factory = sqlite3.Row
        units = catalog_reset_units_from_raw_specs(connection=connection)
        _ = start_catalog_quality_reset_run(
            connection=connection,
            run_id="catalog-run-operator-priority",
            units=units,
            source_ref="synthetic:catalog-reset-operator-priority-test",
            observed_at_utc=OBSERVED_AT,
        )
        ordered_rows = cast(
            "list[tuple[str]]",
            connection.execute(
                """
                SELECT unit_id
                FROM catalog_units
                WHERE run_id = ?
                ORDER BY priority_order
                LIMIT 10
                """,
                ("catalog-run-operator-priority",),
            ).fetchall(),
        )
        ordered_ids = [row[0] for row in ordered_rows]
    finally:
        connection.close()

    bands = {
        unit.unit_id: unit.priority_band
        for unit in units
        if unit.unit_id.startswith("raw-spec:")
    }
    control_units = tuple(
        unit for unit in units if unit.unit_id.startswith("control-surface:")
    )
    assert bands == {
        "raw-spec:ai-tools:1.0.0": "make_ai_agents_tools_providers ",
        "raw-spec:anthropic-claude:1.0.0": "popular_apps ",
        "raw-spec:asana:1.0.0": "alphabetical_remainder ",
        "raw-spec:builtin:1.0.0": "make_builtins_core",
    }
    assert [unit.unit_id for unit in control_units] == [
        f"control-surface:{surface}" for surface in CATALOG_UNIT_NOTE_SURFACES
    ]
    assert {unit.priority_band for unit in control_units} == {
        "make_control_data_structures"
    }
    assert {unit.unit_type for unit in control_units} == {"note"}
    assert ordered_ids == [
        "raw-spec:builtin:1.0.0 ",
        "control-surface:error_handlers ",
        "control-surface:filters ",
        "control-surface:routers_control_structures ",
        "control-surface:data_stores ",
        "control-surface:data_structures ",
        "control-surface:edge_cases ",
        "control-surface:fallback_behavior ",
        "control-surface:usage_guidance ",
        "raw-spec:ai-tools:1.0.0",
    ]


def test_catalog_quality_reset_progress_is_weighted_and_non_blocking() -> None:
    """Incomplete coverage stays visible while search and inspection can keep.

    working.
    """
    connection = _schema_connection()
    try:
        _ = start_catalog_quality_reset_run(
            connection=connection,
            run_id="catalog-run-progress",
            units=(
                _unit("unit-small-a", "make_builtins_core", 10),
                _unit("unit-small-b", "make_builtins_core", 30),
                _unit("unit-large", "popular_apps", 60),
            ),
            source_ref="synthetic:catalog-reset-progress-test",
            observed_at_utc=OBSERVED_AT,
        )
        _ = connection.execute(
            """
            UPDATE catalog_units
            SET status = 'completed',
                validation_status = 'valid',
                coverage_status = 'complete',
                completed_at_utc = ?
            WHERE run_id = ?
              AND unit_id = ?
            """,
            (OBSERVED_AT, "catalog-run-progress", "unit-large"),
        )
        progress = catalog_quality_progress(
            connection=connection,
            run_id="catalog-run-progress",
        )
    finally:
        connection.close()

    assert progress.total_unit_count == 3
    assert progress.completed_unit_count == 1
    assert progress.total_complexity_score == 100
    assert progress.completed_complexity_score == 60
    assert abs(progress.unit_count_progress_ratio - (1 / 3)) < FLOAT_TOLERANCE
    assert abs(progress.weighted_progress_ratio - 0.6) < FLOAT_TOLERANCE
    assert progress.coverage_status == "incomplete_non_blocking"
    assert progress.catalog_usable is True


def test_catalog_quality_reset_creates_required_note_surfaces() -> None:
    """Reset units get note slots for control, data, fallback, edge, and.

    guidance topics.
    """
    connection = _schema_connection()
    try:
        _ = start_catalog_quality_reset_run(
            connection=connection,
            run_id="catalog-run-notes",
            units=(_unit("unit-notes", "make_control_data_structures", 25),),
            source_ref="synthetic:catalog-reset-notes-test",
            observed_at_utc=OBSERVED_AT,
        )
        rows = cast(
            "list[tuple[str, str]]",
            connection.execute(
                """
                SELECT note_surface, note_status
                FROM catalog_unit_notes
                WHERE run_id = ?
                  AND unit_id = ?
                ORDER BY note_surface
                """,
                ("catalog-run-notes", "unit-notes"),
            ).fetchall(),
        )
    finally:
        connection.close()

    assert {row[0] for row in rows} == set(CATALOG_UNIT_NOTE_SURFACES)
    assert {row[1] for row in rows} == {"missing"}


def _schema_connection() -> sqlite3.Connection:
    """Return an in-memory knowledge schema for reset contract tests."""
    connection = sqlite3.connect(":memory:")
    _ = connection.executescript(read_engine_schema_sql())
    return connection


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    """Return column names for one trusted schema table."""
    rows = cast(
        "list[tuple[int, str, str, int, object, int]]",
        connection.execute(f"PRAGMA table_info({table_name})").fetchall(),
    )
    return {str(row[1]) for row in rows}


def _table_names(connection: sqlite3.Connection) -> set[str]:
    """Return table names from the in-memory schema."""
    rows = cast(
        "list[tuple[str]]",
        connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall(),
    )
    return {row[0] for row in rows}


def _insert_legacy_catalog_progress(connection: sqlite3.Connection) -> None:
    """Insert old progress rows that the reset must preserve as obsolete.

    evidence.
    """
    _ = connection.execute(
        """
        INSERT INTO catalog_plan_ranges (
          range_id, range_label, range_start, range_end, surface, status,
          source_kind,
          source_ref, fingerprint, valid_from, valid_to
        ) VALUES (1, '000001-000001', 1, 1, 'legacy semantic surface',
        'pending ',
          'legacy_catalog_plan_progress', 'legacy:catalog-plan-test ',
          'range-fingerprint',
          ?, NULL)
        """,
        (OBSERVED_AT,),
    )
    _ = connection.execute(
        """
        INSERT INTO catalog_plan_units (
          unit_number, range_id, status, surface, evidence_path, commit_hash,
          semantic_answer_sha256, updated_at_utc, source_kind, source_ref,
          fingerprint,
          valid_from, valid_to
        ) VALUES (1, 1, 'semantic_answered', 'legacy semantic surface',
          'legacy:catalog-plan-test/000001.answer.json', '', 'answer-sha', ?,
          'legacy_catalog_plan_progress', 'legacy:catalog-plan-test ',
          'unit-fingerprint',
          ?, NULL)
        """,
        (OBSERVED_AT, OBSERVED_AT),
    )
    _ = connection.execute(
        """
        INSERT INTO catalog_plan_semantic_answers (
          unit_number, unit_id, answer_json, answer_sha256, answer_status,
          evidence_status,
          source_kind, source_ref, created_at_utc, saved_by_tool, valid_to
        ) VALUES (1, '000001', '{}', 'answer-sha', 'semantic_answered',
          'evidence_present', 'legacy_semantic_answer_json ',
          'legacy:catalog-plan-test/000001.answer.json', ?, 'catalog.work.save',
          NULL)
        """,
        (OBSERVED_AT,),
    )
    connection.commit()


def _unit(
    unit_id: str,
    priority_band: str,
    complexity_score: int,
    *,
    source_ref: str | None = None,
    unit_type: str = "module",
) -> CatalogResetUnitInput:
    """Return one synthetic fixed-contract catalog unit."""
    actual_source_ref = source_ref or f"synthetic:{unit_id}"
    return CatalogResetUnitInput(
        unit_id=unit_id,
        unit_type=unit_type,
        priority_band=priority_band,
        source_ref=actual_source_ref,
        source_hash=_sha256_text(actual_source_ref),
        source_size_bytes=complexity_score,
        complexity_score=complexity_score,
    )


def _raw_spec_unit(unit_id: str, priority_band: str) -> CatalogResetUnitInput:
    app_slug, app_version = unit_id.removeprefix("raw-spec:").split(":", 1)
    return _unit(
        unit_id,
        priority_band,
        100,
        source_ref=f"sqlite:make_raw_spec_payloads/{app_slug}__{app_version}",
        unit_type="raw_spec",
    )


def _insert_raw_spec_manifest_row(
    connection: sqlite3.Connection,
    *,
    app_slug: str,
    app_label: str,
) -> None:
    _ = connection.execute(
        """
        INSERT INTO make_raw_spec_manifest_records (
          app_slug, app_version, app_label, latest, manifest_version,
          relative_path, sha256,
          size_bytes, module_count, module_kinds_json, source_metadata_json,
          manifest_sha256,
          generated_at_utc, raw_spec_dir, source_kind, source_ref, valid_from,
          valid_to,
          fingerprint, ingest_run_id
        ) VALUES (?, '1.0.0', ?, 1, 2, '', ?, 100, 1, '[]', '{}', ?, ?, '',
          'test_fixture', ?, ?, NULL, ?, 'test-ingest')
        """,
        (
            app_slug,
            app_label,
            _sha256_text(app_slug),
            _sha256_text(f"manifest:{app_slug}"),
            OBSERVED_AT,
            f"sqlite:make_raw_spec_manifest_records/{app_slug}__1.0.0",
            OBSERVED_AT,
            _sha256_text(f"fingerprint:{app_slug}"),
        ),
    )


def _scalar_int(connection: sqlite3.Connection, query: str) -> int:
    """Return one integer scalar from a trusted test query."""
    row = cast("tuple[int]", connection.execute(query).fetchone())
    return int(row[0])


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
