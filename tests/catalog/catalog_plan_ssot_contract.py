# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contract tests for catalog-plan state inside the Make knowledge SQLite SSOT.

Boundary contract:
- Owns: schema and non-semantic migration coverage for catalog-plan SQLite
  state.
- Must not: author real catalog answers, call providers, or mutate checked-in
  artifacts.
- Allows: synthetic legacy progress databases and synthetic answer JSON
  fixtures.
- Split when: MCP catalog.next_unit/catalog.save_unit behavior moves to its
  own tests.
"""

from __future__ import annotations

import json
import sqlite3
from shutil import copytree
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from pathlib import Path

from catalog.knowledge import (
    DEFAULT_DB_SNAPSHOT_DIR,
    DEFAULT_KNOWLEDGE_DB_PATH,
    build_knowledge_store,
    knowledge_store_status,
)
from catalog.knowledge.catalog_plan_ssot import (
    cleanup_placeholder_semantic_answers,
    migrate_legacy_catalog_plan_artifacts,
)
from catalog.knowledge.schema import (
    GRAPH_PROJECTION_TABLES,
    PURE_SEMANTIC_TABLES,
    RUNTIME_EXTENSION_TABLES,
)

from tests.support.paths import repo_root

REPO_ROOT = repo_root()
OBSERVED_AT = "2026-05-18T00:00:00+00:00"
CATALOG_PLAN_SSOT_TABLES = {
    "catalog_plan_metadata",
    "catalog_plan_ranges",
    "catalog_plan_units",
    "catalog_plan_progress_events",
    "catalog_plan_semantic_answers",
    "catalog_plan_quarantine_records",
    "catalog_search_documents",
    "make_datastore_structure_evidence",
    "make_webhook_structure_evidence",
    "make_scraped_datastore_evidence",
    "make_scraped_webhook_evidence",
    "make_scraped_structure_evidence",
    "make_scraped_connection_evidence",
    "make_scraped_scope_evidence",
    "make_scraped_import_export_evidence",
    "linter_rule_surface_matrix",
    "linter_data_source_inventory",
}
CATALOG_SEARCH_PERFORMANCE_INDEXES = {
    "idx_modules_current_exact_lookup",
    "idx_modules_current_search_rank",
    "idx_fields_current_module_scan",
    "idx_catalog_plan_answers_valid_scan",
    "idx_catalog_plan_quarantine_open_priority",
}


def test_make_knowledge_schema_contains_catalog_plan_ssot_tables(
    tmp_path: Path,
) -> None:
    """The main Make knowledge SQLite schema owns catalog-plan engine state."""
    prepare_snapshot_dir(tmp_path)

    report = build_knowledge_store(repo_root=tmp_path)

    connection = sqlite3.connect(tmp_path / DEFAULT_KNOWLEDGE_DB_PATH)
    try:
        table_rows = cast(
            "list[tuple[str]]",
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall(),
        )
        tables = {str(row[0]) for row in table_rows}
        schema_version = cast(
            "tuple[str]",
            connection.execute(
                "SELECT value "
                "FROM snapshot_metadata "
                "WHERE key = 'schema_version'"
            ).fetchone(),
        )[0]
    finally:
        connection.close()

    assert report.schema_version == 13
    assert schema_version == "13"
    assert tables >= CATALOG_PLAN_SSOT_TABLES
    assert not (tables & set(RUNTIME_EXTENSION_TABLES))


def test_make_knowledge_schema_keeps_graph_and_semantic_tables_separate(
    tmp_path: Path,
) -> None:
    """Graph projections are engine tables, not semantic answers."""
    prepare_snapshot_dir(tmp_path)

    _ = build_knowledge_store(repo_root=tmp_path)

    connection = sqlite3.connect(tmp_path / DEFAULT_KNOWLEDGE_DB_PATH)
    try:
        table_rows = cast(
            "list[tuple[str]]",
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall(),
        )
    finally:
        connection.close()

    tables = {str(row[0]) for row in table_rows}
    assert set(GRAPH_PROJECTION_TABLES) <= tables
    assert set(PURE_SEMANTIC_TABLES) <= tables
    assert set(GRAPH_PROJECTION_TABLES).isdisjoint(PURE_SEMANTIC_TABLES)


def test_make_knowledge_schema_contains_catalog_search_performance_indexes(
    tmp_path: Path,
) -> None:
    """Catalog search schema includes read-side indexes."""
    prepare_snapshot_dir(tmp_path)

    _ = build_knowledge_store(repo_root=tmp_path)

    connection = sqlite3.connect(tmp_path / DEFAULT_KNOWLEDGE_DB_PATH)
    try:
        index_rows = cast(
            "list[tuple[str]]",
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall(),
        )
        query_plan_rows = cast(
            "list[tuple[int, int, int, str]]",
            connection.execute(
                """
                EXPLAIN QUERY PLAN
                SELECT module_id
                FROM modules
                WHERE valid_to IS NULL
                  AND deprecated = 0
                  AND lower(module_id) = ?
                """,
                ("module:slack:2.14.3:action:actioncreatemessage",),
            ).fetchall(),
        )
    finally:
        connection.close()

    indexes = {row[0] for row in index_rows}
    query_plan = " ".join(row[3] for row in query_plan_rows)
    assert indexes >= CATALOG_SEARCH_PERFORMANCE_INDEXES
    assert "idx_modules_current_exact_lookup" in query_plan


def test_old_knowledge_schema_reports_rebuildable_stale_schema(
    tmp_path: Path,
) -> None:
    """Older generated SQLite files must fail closed."""
    database_path = tmp_path / DEFAULT_KNOWLEDGE_DB_PATH
    database_path.parent.mkdir(parents=True)
    connection = sqlite3.connect(database_path)
    try:
        _ = connection.execute(
            "CREATE TABLE snapshot_metadata ("
            "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        _ = connection.execute(
            "INSERT INTO snapshot_metadata (key, value) VALUES (?, ?)",
            ("schema_version", "3"),
        )
        connection.commit()
    finally:
        connection.close()

    status = knowledge_store_status(repo_root=tmp_path)

    assert status.status == "stale_schema"
    assert status.schema_version == 3
    assert status.recommended_commands == (
        "python -B -m catalog.knowledge ensure",
    )


def test_catalog_plan_legacy_progress_imports_into_main_sqlite(
    tmp_path: Path,
) -> None:
    """Legacy progress rows import without changing source files."""
    prepare_snapshot_dir(tmp_path)
    _ = build_knowledge_store(repo_root=tmp_path)
    legacy_database = write_legacy_progress_database(tmp_path, total_units=2)
    answer_dir = tmp_path / "semantic_answers"
    answer_dir.mkdir()
    _ = (answer_dir / "000001.answer.json").write_text(
        json.dumps(
            {
                "unit_id": "000001",
                "summary": "Synthetic test answer only.",
                "semantic_edges": [],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    connection = sqlite3.connect(tmp_path / DEFAULT_KNOWLEDGE_DB_PATH)
    try:
        report = migrate_legacy_catalog_plan_artifacts(
            connection=connection,
            legacy_database_path=legacy_database,
            semantic_answer_dir=answer_dir,
            source_ref="legacy:catalog_plan_artifact",
            observed_at_utc=OBSERVED_AT,
        )
        status_rows = cast(
            "list[tuple[int, str, str | None]]",
            connection.execute(
                """
                SELECT unit_number, status, semantic_answer_sha256
                FROM catalog_plan_units
                ORDER BY unit_number
                """
            ).fetchall(),
        )
        answer_rows = cast(
            "list[tuple[str, str]]",
            connection.execute(
                """
                SELECT unit_id, saved_by_tool
                FROM catalog_plan_semantic_answers
                ORDER BY unit_id
                """
            ).fetchall(),
        )
        event_count = cast(
            "tuple[int]",
            connection.execute(
                "SELECT COUNT(*) FROM catalog_plan_progress_events"
            ).fetchone(),
        )[0]
    finally:
        connection.close()

    assert report.metadata_count > 0
    assert report.range_count == 1
    assert report.unit_count == 2
    assert report.progress_event_count == 1
    assert report.semantic_answer_count == 1
    assert report.quarantined_answer_count == 0
    assert status_rows[0][1] == "semantic_answered"
    assert status_rows[0][2] is not None
    assert status_rows[1] == (2, "pending", None)
    assert answer_rows == [("000001", "catalog.work.save")]
    assert event_count == 1


def test_catalog_plan_placeholder_answer_enters_quarantine_not_answers(
    tmp_path: Path,
) -> None:
    """Insufficient-evidence placeholders become retry records."""
    prepare_snapshot_dir(tmp_path)
    _ = build_knowledge_store(repo_root=tmp_path)
    legacy_database = write_legacy_progress_database(tmp_path, total_units=1)
    answer_dir = tmp_path / "semantic_answers"
    answer_dir.mkdir()
    _ = (answer_dir / "000001.answer.json").write_text(
        json.dumps(
            {
                "unit_id": "000001",
                "summary": (
                    "No sufficient evidence is available in this fixture."
                ),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    connection = sqlite3.connect(tmp_path / DEFAULT_KNOWLEDGE_DB_PATH)
    try:
        report = migrate_legacy_catalog_plan_artifacts(
            connection=connection,
            legacy_database_path=legacy_database,
            semantic_answer_dir=answer_dir,
            source_ref="legacy:catalog_plan_artifact",
            observed_at_utc=OBSERVED_AT,
        )
        answer_count = cast(
            "tuple[int]",
            connection.execute(
                "SELECT COUNT(*) FROM catalog_plan_semantic_answers"
            ).fetchone(),
        )[0]
        quarantine = cast(
            "tuple[str, str]",
            connection.execute(
                """
                SELECT reason, retry_policy_json
                FROM catalog_plan_quarantine_records
                """
            ).fetchone(),
        )
    finally:
        connection.close()

    assert report.semantic_answer_count == 0
    assert report.quarantined_answer_count == 1
    assert answer_count == 0
    assert (
        quarantine[0] == "semantic_answer_has_insufficient_evidence_placeholder"
    )
    assert "catalog.next_unit -> catalog.save_unit" in quarantine[1]


def test_catalog_plan_placeholder_cleanup_preserves_valid_answer_files(
    tmp_path: Path,
) -> None:
    """Cleanup deletes only placeholders after SQLite records the quarantine."""
    prepare_snapshot_dir(tmp_path)
    _ = build_knowledge_store(repo_root=tmp_path)
    legacy_database = write_legacy_progress_database(tmp_path, total_units=2)
    answer_dir = tmp_path / "semantic_answers"
    answer_dir.mkdir()
    valid_answer = answer_dir / "000001.answer.json"
    placeholder_answer = answer_dir / "000002.answer.json"
    _ = valid_answer.write_text(
        json.dumps(
            {
                "unit_id": "000001",
                "summary": "Synthetic valid cleanup fixture.",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    _ = placeholder_answer.write_text(
        json.dumps(
            {
                "unit_id": "000002",
                "summary": "No sufficient evidence for this synthetic fixture.",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    connection = sqlite3.connect(tmp_path / DEFAULT_KNOWLEDGE_DB_PATH)
    try:
        _ = migrate_legacy_catalog_plan_artifacts(
            connection=connection,
            legacy_database_path=legacy_database,
            semantic_answer_dir=None,
            source_ref="legacy:catalog_plan_artifact",
            observed_at_utc=OBSERVED_AT,
        )
        report = cleanup_placeholder_semantic_answers(
            connection=connection,
            semantic_answer_dir=answer_dir,
            source_ref="legacy:catalog_plan_artifact/semantic_answers",
            observed_at_utc=OBSERVED_AT,
        )
        answer_count = cast(
            "tuple[int]",
            connection.execute(
                "SELECT COUNT(*) FROM catalog_plan_semantic_answers"
            ).fetchone(),
        )[0]
        quarantine_count = cast(
            "tuple[int]",
            connection.execute(
                "SELECT COUNT(*) FROM catalog_plan_quarantine_records"
            ).fetchone(),
        )[0]
    finally:
        connection.close()

    assert report.scanned_answer_count == 2
    assert report.migrated_answer_count == 1
    assert report.quarantined_answer_count == 1
    assert report.removed_placeholder_count == 1
    assert report.retained_answer_file_count == 1
    assert valid_answer.is_file()
    assert not placeholder_answer.exists()
    assert answer_count == 1
    assert quarantine_count == 1


def prepare_snapshot_dir(tmp_path: Path) -> None:
    """Copy tracked SQL snapshots into a temporary repository root."""
    source = REPO_ROOT / DEFAULT_DB_SNAPSHOT_DIR
    destination = tmp_path / DEFAULT_DB_SNAPSHOT_DIR
    _ = copytree(source, destination)


def write_legacy_progress_database(tmp_path: Path, *, total_units: int) -> Path:
    """Create a synthetic legacy catalog-plan progress database.

    Returns:
        Path to the synthetic legacy progress database.
    """
    database_path = tmp_path / "catalog_plan_progress.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        _ = connection.executescript(
            """
            CREATE TABLE metadata(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE ranges(
                range_id INTEGER PRIMARY KEY,
                range_label TEXT NOT NULL,
                range_start INTEGER NOT NULL,
                range_end INTEGER NOT NULL,
                surface TEXT NOT NULL,
                status TEXT NOT NULL
            );
            CREATE TABLE units(
                unit_number INTEGER PRIMARY KEY,
                range_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                surface TEXT NOT NULL,
                evidence_path TEXT NOT NULL DEFAULT '',
                commit_hash TEXT NOT NULL DEFAULT '',
                updated_at_utc TEXT NOT NULL
            );
            CREATE TABLE progress_events(
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                unit_number INTEGER,
                event_type TEXT NOT NULL,
                event_json TEXT NOT NULL,
                created_at_utc TEXT NOT NULL
            );
            """
        )
        range_label = f"000001-{total_units:06d}"
        _ = connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            (
                ("ledger_id", "synthetic_legacy_catalog_plan_progress"),
                ("total_units", str(total_units)),
            ),
        )
        _ = connection.execute(
            """
            INSERT INTO ranges(
                range_id, range_label, range_start, range_end, surface,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                range_label,
                1,
                total_units,
                "synthetic catalog-plan surface",
                "pending",
            ),
        )
        _ = connection.executemany(
            """
            INSERT INTO units(
                unit_number, range_id, status, surface, evidence_path,
                commit_hash, updated_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    unit_number,
                    1,
                    "pending",
                    "synthetic catalog-plan surface",
                    "",
                    "",
                    OBSERVED_AT,
                )
                for unit_number in range(1, total_units + 1)
            ),
        )
        _ = connection.execute(
            """
            INSERT INTO progress_events(
                unit_number, event_type, event_json, created_at_utc
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                1,
                "test_event",
                json.dumps({"unit_id": "000001"}, sort_keys=True),
                OBSERVED_AT,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return database_path
