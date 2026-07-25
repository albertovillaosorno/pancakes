# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contract tests for the Make linter SQLite audit matrix.

Boundary contract:
- Owns: proof that linter rules and linter evidence files are represented in
  SQLite as code-only, SQLite-only, or cross-surface audit rows.
- Must not: promote linter candidates, author catalog semantic answers, or call
  live Make services.
- Allows: synthetic linter data files in a temporary repository root.
- Split when: linter rule promotion decisions gain a dedicated SQLite store.
"""

from __future__ import annotations

import json
import sqlite3
from shutil import copytree
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from pathlib import Path

from blueprints.validation.linter_sqlite_audit import (
    LINTER_AUDIT_SOURCE_OF_TRUTH,
    LINTER_DATA_INVENTORY_SOURCE_OF_TRUTH,
    linter_rule_surface_matrix,
    sync_linter_sqlite_audit,
)
from catalog.knowledge import (
    DEFAULT_DB_SNAPSHOT_DIR,
    DEFAULT_KNOWLEDGE_DB_PATH,
    KNOWLEDGE_SCHEMA_VERSION,
)

from tests.support.paths import repo_root

REPO_ROOT = repo_root()


def test_linter_rule_surface_matrix_covers_surfaces() -> None:
    """The taxonomy declares which linter rules evaluate each surface."""
    rows = {row.family_id: row for row in linter_rule_surface_matrix()}

    assert rows["ast_import_shape"].rule_surface == "code_only"
    assert rows["ast_import_shape"].sqlite_predicate_sources == ()
    assert rows["ast_import_shape"].source_tables == ()
    assert rows["designer_message_evidence"].rule_surface == "sqlite_only"
    assert rows["designer_message_evidence"].source_tables == (
        "claim_conflicts",
        "claim_evidence",
        "course_claims",
        "designer_message_evidence",
        "linter_quarantine_records",
        "module_transaction_profiles",
        "native_module_expectations",
        "optimizer_hints",
        "rule_facts",
    )
    assert rows["mapping_reference_contracts"].rule_surface == "cross_surface"
    assert rows["mapping_reference_contracts"].code_predicate_sources == (
        "ast_structure",
        "validation_fixture",
    )
    assert rows["mapping_reference_contracts"].sqlite_predicate_sources == (
        "knowledge_store",
    )


def test_linter_sqlite_audit_sync_writes_matrix_and_inventory_rows(
    tmp_path: Path,
) -> None:
    """The audit sync writes rule and data-source coverage."""
    prepare_snapshot_dir(tmp_path)
    write_synthetic_linter_files(tmp_path)

    report = sync_linter_sqlite_audit(tmp_path)

    assert report.schema_version == KNOWLEDGE_SCHEMA_VERSION
    assert report.source_of_truth == LINTER_AUDIT_SOURCE_OF_TRUTH
    assert report.rule_matrix_count == len(linter_rule_surface_matrix())
    assert report.code_only_count > 0
    assert report.sqlite_only_count > 0
    assert report.cross_surface_count > 0
    assert report.data_source_count == 5

    connection = sqlite3.connect(tmp_path / DEFAULT_KNOWLEDGE_DB_PATH)
    try:
        rule_counts = dict(
            cast(
                "list[tuple[str, int]]",
                connection.execute(
                    """
                    SELECT rule_surface, COUNT(*)
                    FROM linter_rule_surface_matrix
                    GROUP BY rule_surface
                    ORDER BY rule_surface
                    """
                ).fetchall(),
            )
        )
        inventory_rows = cast(
            "list[tuple[str, str, str, str]]",
            connection.execute(
                """
                SELECT
                    source_path,
                    source_kind,
                    authority_state,
                    source_of_truth
                FROM linter_data_source_inventory
                ORDER BY source_path
                """
            ).fetchall(),
        )
    finally:
        connection.close()

    assert rule_counts["code_only"] == report.code_only_count
    assert rule_counts["sqlite_only"] == report.sqlite_only_count
    assert rule_counts["cross_surface"] == report.cross_surface_count
    assert inventory_rows == [
        (
            (
                "src/blueprints/validation/data/linter/decisions/"
                "linter-candidate-decisions.json"
            ),
            "legacy_candidate_decision_ledger",
            "legacy_evidence_pending_sqlite_migration",
            LINTER_DATA_INVENTORY_SOURCE_OF_TRUTH,
        ),
        (
            "src/blueprints/validation/data/linter/decisions/linter-candidate-decisions.json",
            "sqlite_derived_quarantine_manifest",
            "sqlite_derived_snapshot",
            LINTER_DATA_INVENTORY_SOURCE_OF_TRUTH,
        ),
        (
            (
                "src/blueprints/validation/data/linter/quarantine/"
                "mcp-review-decisions/sec-005.json"
            ),
            "sqlite_derived_review_event",
            "sqlite_derived_snapshot",
            LINTER_DATA_INVENTORY_SOURCE_OF_TRUTH,
        ),
        (
            "src/blueprints/validation/data/linter/quarantine/review-coverage.json",
            "sqlite_derived_review_coverage",
            "sqlite_derived_snapshot",
            LINTER_DATA_INVENTORY_SOURCE_OF_TRUTH,
        ),
        (
            "src/blueprints/validation/data/linter/quarantine/security/sec-005.md",
            "legacy_quarantine_record",
            "legacy_evidence_pending_sqlite_migration",
            LINTER_DATA_INVENTORY_SOURCE_OF_TRUTH,
        ),
    ]


def prepare_snapshot_dir(tmp_path: Path) -> None:
    """Copy tracked SQL snapshots into a temporary repository root."""
    source = REPO_ROOT / DEFAULT_DB_SNAPSHOT_DIR
    destination = tmp_path / DEFAULT_DB_SNAPSHOT_DIR
    _ = copytree(source, destination)


def write_synthetic_linter_files(tmp_path: Path) -> None:
    """Write a tiny linter data tree for inventory tests."""
    write_json(
        tmp_path
        / "src/blueprints/validation/data/linter/decisions/linter-candidate-decisions.json",
        {"schema_version": 1, "records": []},
    )
    write_json(
        tmp_path
        / "src/blueprints/validation/data/linter/quarantine"
        / "review-coverage.json",
        {"schema_version": 1, "records": []},
    )
    write_json(
        tmp_path
        / "src/blueprints/validation/data/linter/quarantine"
        / "mcp-review-decisions/sec-005.json",
        {
            "candidate_id": "SEC-005",
            "source_of_truth": "sqlite:linter_quarantine_records",
        },
    )
    write_json(
        tmp_path
        / "src/blueprints/validation/data/linter/decisions"
        / "linter-candidate-decisions.json",
        {"sources": []},
    )
    write_text(
        tmp_path
        / "src/blueprints/validation/data/linter/quarantine/security"
        / "sec-005.md",
        "# SEC-005\n\nLegacy candidate evidence pending SQLite promotion.\n",
    )


def write_json(path: Path, payload: dict[str, object]) -> None:
    """Write one deterministic JSON object."""
    write_text(path, f"{json.dumps(payload, indent=2, sort_keys=True)}\n")


def write_text(path: Path, text: str) -> None:
    """Write one UTF-8 test fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(text, encoding="utf-8")
