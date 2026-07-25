# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Knowledge database status matrix contracts.

Boundary contract:
- Owns: missing, empty, stale, and fresh knowledge DB status payload checks.
- Must not: test CLI output, SQL dumps, raw-spec parsing, or live services.
- Allows: temporary repository fixtures and direct read-only status assertions.
- Split when: status states gain independent health-check or service adapters.
- Merge when: another catalog test owns this full status-state matrix.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from catalog.knowledge import build_knowledge_store, knowledge_store_status

from tests.catalog.knowledge_store_status_contract import (
    assert_status_matches_build_report,
)
from tests.catalog.knowledge_store_status_fixtures import (
    DEFAULT_DATABASE_PATH,
    DEFAULT_RAW_SPEC_MANIFEST_PATH,
    EXPECTED_RECOMMENDED_COMMANDS,
    FIXED_GENERATED_AT,
    NEXT_GENERATED_AT,
    create_empty_sqlite_database,
    prepare_snapshot_dir,
    sync_http_raw_spec,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_status_matrix_reports_missing_database_and_manifest(
    tmp_path: Path,
) -> None:
    """Missing local knowledge assets should be explicit and recoverable."""
    status = knowledge_store_status(repo_root=tmp_path)

    assert status.status == "missing_database", (
        f"Missing fixture should report missing_database: {status}"
    )
    assert status.database_path == DEFAULT_DATABASE_PATH, (
        f"Status should expose the default DB path: {status}"
    )
    assert status.raw_spec_manifest_path == DEFAULT_RAW_SPEC_MANIFEST_PATH, (
        f"Status should expose the default manifest path: {status}"
    )
    assert status.missing_paths == (
        DEFAULT_DATABASE_PATH,
        DEFAULT_RAW_SPEC_MANIFEST_PATH,
    ), f"Missing paths should be deterministic: {status}"
    assert status.recommended_commands == EXPECTED_RECOMMENDED_COMMANDS, (
        f"Missing status should recommend deterministic rebuild: {status}"
    )


def test_status_matrix_reports_empty_sqlite_database(tmp_path: Path) -> None:
    """An empty SQLite file is distinct from an absent generated database."""
    create_empty_sqlite_database(tmp_path)

    status = knowledge_store_status(repo_root=tmp_path)

    assert status.status == "empty_database", (
        f"Empty SQLite DB should be classified without traceback: {status}"
    )
    assert status.database_available, (
        f"Empty SQLite file should still report database availability: {status}"
    )
    assert not (status.schema_version is not None), (
        f"Empty SQLite DB should not infer schema version: {status}"
    )
    assert status.missing_paths == (DEFAULT_RAW_SPEC_MANIFEST_PATH,), (
        f"Empty DB should report only the missing manifest path: {status}"
    )
    assert status.recommended_commands == EXPECTED_RECOMMENDED_COMMANDS, (
        f"Empty DB should recommend deterministic rebuild: {status}"
    )


def test_status_matrix_reports_stale_manifest_rebuild_need(
    tmp_path: Path,
) -> None:
    """A DB built from an older raw-spec manifest should request rebuild."""
    prepare_snapshot_dir(tmp_path)
    sync_http_raw_spec(tmp_path, generated_at=FIXED_GENERATED_AT)
    _ = build_knowledge_store(repo_root=tmp_path)
    sync_http_raw_spec(tmp_path, generated_at=NEXT_GENERATED_AT)

    status = knowledge_store_status(repo_root=tmp_path)

    assert status.status == "stale_manifest", (
        f"Stale manifest should dominate status: {status}"
    )
    assert not (status.missing_paths), (
        f"Stale status should not report missing local files: {status}"
    )
    assert status.recommended_commands == EXPECTED_RECOMMENDED_COMMANDS, (
        f"Stale status should recommend deterministic rebuild: {status}"
    )


def test_status_matrix_reports_fresh_database_without_recovery_actions(
    tmp_path: Path,
) -> None:
    """A fresh status payload should retain paths but not recovery actions."""
    prepare_snapshot_dir(tmp_path)
    sync_http_raw_spec(tmp_path, generated_at=FIXED_GENERATED_AT)
    build_report = build_knowledge_store(repo_root=tmp_path)

    status = knowledge_store_status(repo_root=tmp_path)

    assert_status_matches_build_report(status=status, report=build_report)
    assert not (status.missing_paths), (
        f"Fresh status should not report missing local files: {status}"
    )
    assert not (status.recommended_commands), (
        f"Fresh status should not recommend recovery commands: {status}"
    )
