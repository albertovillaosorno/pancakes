# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Status-report tests for the generated Make knowledge SQLite store.

Boundary contract:
- Owns: freshness, coverage-count, and missing-database status behavior.
- Must not: test SQL dumping, raw-spec parsing depth, or blueprint validation.
- Allows: temporary raw-spec manifests and CLI JSON status assertions.
- Split when: status gains independent health probes or service adapters.
- Merge when: another catalog test duplicates these exact status behaviors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from catalog.knowledge import build_knowledge_store, knowledge_store_status

from tests.catalog.knowledge_store_status_fixtures import (
    DEFAULT_DATABASE_PATH,
    FIXED_GENERATED_AT,
    NEXT_GENERATED_AT,
    corrupt_manifest_timestamp,
    prepare_snapshot_dir,
    sync_http_raw_spec,
)

if TYPE_CHECKING:
    from pathlib import Path

    from catalog.knowledge import (
        KnowledgeStoreBuildReport,
        KnowledgeStoreStatusReport,
    )


def test_knowledge_store_status_reports_freshness_and_coverage_counts(
    tmp_path: Path,
) -> None:
    """Status reports raw-spec freshness and promoted structural coverage."""
    prepare_snapshot_dir(tmp_path)
    sync_http_raw_spec(tmp_path, generated_at=FIXED_GENERATED_AT)
    build_report = build_knowledge_store(repo_root=tmp_path)

    status = knowledge_store_status(repo_root=tmp_path)

    assert_status_matches_build_report(status=status, report=build_report)


def test_knowledge_store_status_reports_stale_raw_spec_manifest(
    tmp_path: Path,
) -> None:
    """Status distinguishes stale SQLite from native module coverage gaps."""
    prepare_snapshot_dir(tmp_path)
    sync_http_raw_spec(
        tmp_path,
        generated_at=FIXED_GENERATED_AT,
        action_label="Make a request",
    )
    _ = build_knowledge_store(repo_root=tmp_path)
    sync_http_raw_spec(
        tmp_path,
        generated_at=NEXT_GENERATED_AT,
        action_label="Make HTTP request",
    )

    status = knowledge_store_status(repo_root=tmp_path)

    assert status.status == "stale_manifest", (
        f"Stale raw-spec manifest should dominate status: {status}"
    )
    assert not (status.raw_spec_manifest_matches_database is not False), (
        f"Status must expose stale raw-spec mismatch: {status}"
    )
    assert (
        status.database_raw_spec_manifest_generated_at_utc == FIXED_GENERATED_AT
    ), f"Status lost the DB ingest freshness timestamp: {status}"
    assert status.raw_spec_manifest_generated_at_utc == NEXT_GENERATED_AT, (
        f"Status lost the current manifest freshness timestamp: {status}"
    )


def test_knowledge_store_status_handles_missing_database(
    tmp_path: Path,
) -> None:
    """Status reports missing generated DBs without creating files."""
    prepare_snapshot_dir(tmp_path)

    status = knowledge_store_status(repo_root=tmp_path)

    assert status.status == "missing_database", (
        f"Unexpected missing database status: {status}"
    )
    assert not (status.database_available), (
        f"Unexpected missing database status: {status}"
    )
    assert not (status.raw_spec_manifest_generated_at_utc is not None), (
        f"Missing-DB status should only report freshness when manifest "
        f"exists: {status}"
    )
    assert not (status.database_raw_spec_manifest_sha256 is not None), (
        f"Missing-DB status must not infer DB manifest fingerprints: {status}"
    )
    assert not (status.raw_spec_manifest_matches_database is not None), (
        f"Missing-DB status cannot compare raw manifest freshness: {status}"
    )
    assert status.course_claim_count == 0, (
        f"Missing-DB status must not infer SQLite counts: {status}"
    )
    assert status.claim_evidence_count == 0, (
        f"Missing-DB status must not infer SQLite counts: {status}"
    )
    assert status.claim_conflict_count == 0, (
        f"Missing-DB status must not infer SQLite counts: {status}"
    )
    assert status.transaction_profile_count == 0, (
        f"Missing-DB status must not infer SQLite counts: {status}"
    )
    assert status.native_expectation_count == 0, (
        f"Missing-DB status must not infer SQLite counts: {status}"
    )
    assert not ((tmp_path / DEFAULT_DATABASE_PATH).exists()), (
        "Status must not create the generated SQLite database."
    )


def test_knowledge_store_status_reports_invalid_manifest_without_database(
    tmp_path: Path,
) -> None:
    """Status reports present manifest corruption before a DB exists."""
    sync_http_raw_spec(tmp_path, generated_at=FIXED_GENERATED_AT)
    corrupt_manifest_timestamp(tmp_path)

    status = knowledge_store_status(repo_root=tmp_path)

    assert status.status == "invalid_manifest", (
        f"Invalid manifest should dominate status: {status}"
    )
    assert status.database_available, (
        f"Invalid SQLite raw-spec status must expose the existing SSOT "
        f"file: {status}"
    )
    assert not (status.raw_spec_manifest_available is not True), (
        f"Invalid manifest status must expose manifest presence: {status}"
    )
    assert status.raw_spec_record_count == 0, (
        f"Invalid manifest status must not infer records: {status}"
    )


def assert_status_matches_build_report(
    *,
    status: KnowledgeStoreStatusReport,
    report: KnowledgeStoreBuildReport,
) -> None:
    """Assert status reports the same freshness and coverage counts as build."""
    assert status.raw_spec_manifest_generated_at_utc == FIXED_GENERATED_AT, (
        f"Status must expose raw-spec freshness: {status}"
    )
    assert (
        status.database_raw_spec_manifest_generated_at_utc == FIXED_GENERATED_AT
    ), f"Status must expose DB manifest freshness: {status}"
    assert not (status.raw_spec_manifest_matches_database is not True), (
        f"Status must compare DB and current raw manifest fingerprints: "
        f"{status}"
    )

    count_pairs = (
        ("alias_count", status.alias_count, report.alias_count),
        ("rule_count", status.rule_count, report.rule_count),
        (
            "optimizer_hint_count",
            status.optimizer_hint_count,
            report.optimizer_hint_count,
        ),
        (
            "transaction_profile_count",
            status.transaction_profile_count,
            report.transaction_profile_count,
        ),
        (
            "course_claim_count",
            status.course_claim_count,
            report.course_claim_count,
        ),
        (
            "claim_evidence_count",
            status.claim_evidence_count,
            report.claim_evidence_count,
        ),
        (
            "claim_conflict_count",
            status.claim_conflict_count,
            report.claim_conflict_count,
        ),
        (
            "native_expectation_count",
            status.native_expectation_count,
            report.native_expectation_count,
        ),
    )
    mismatches = [
        name
        for name, status_count, report_count in count_pairs
        if status_count != report_count
    ]
    assert not (mismatches), (
        f"Status counts diverged from build report for {mismatches}: {status}"
    )
