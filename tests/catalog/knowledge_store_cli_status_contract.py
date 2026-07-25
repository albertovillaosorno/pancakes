# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""CLI status-report tests for the generated Make knowledge SQLite store.

Boundary contract:
- Owns: knowledge-store CLI status JSON behavior.
- Must not: test direct status APIs, SQL dumping, or raw-spec parsing depth.
- Allows: temporary raw-spec manifests and CLI JSON status assertions.
- Split when: CLI status gains independent command surfaces.
- Merge when: direct status tests own these exact CLI behaviors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from catalog.knowledge import build_knowledge_store
from catalog.knowledge.__main__ import main as knowledge_cli_main

from tests.catalog.knowledge_store_status_fixtures import (
    DEFAULT_DATABASE_PATH,
    EXPECTED_CLAIM_CONFLICTS,
    EXPECTED_CLAIM_EVIDENCE,
    EXPECTED_NATIVE_EXPECTATIONS,
    EXPECTED_PROMOTED_COURSE_CLAIMS,
    EXPECTED_TRANSACTION_PROFILES,
    FIXED_GENERATED_AT,
    NEXT_GENERATED_AT,
    corrupt_manifest_timestamp,
    prepare_snapshot_dir,
    sync_http_raw_spec,
)
from tests.support.json_payloads import json_object_from_text

if TYPE_CHECKING:
    from pathlib import Path

    from _pytest.capture import CaptureFixture


def test_knowledge_store_cli_status_outputs_freshness_and_coverage_counts(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    """The CLI status command reports raw freshness and promoted coverage.

    counts.
    """
    prepare_snapshot_dir(tmp_path)
    sync_http_raw_spec(tmp_path, generated_at=FIXED_GENERATED_AT)
    _ = build_knowledge_store(repo_root=tmp_path)

    exit_code = knowledge_cli_main(["--repo-root", str(tmp_path), "status"])
    captured = capsys.readouterr()
    payload = json_object_from_text(captured.out, "knowledge status output")

    assert exit_code == 0, f"Status command failed: {exit_code}, {payload}"
    assert (
        payload.get("raw_spec_manifest_generated_at_utc") == FIXED_GENERATED_AT
    ), f"Status payload is missing raw freshness: {payload}"
    assert not (
        payload.get("raw_spec_manifest_matches_database") is not True
    ), f"Status payload is missing manifest freshness comparison: {payload}"
    assert (
        payload.get("database_raw_spec_manifest_generated_at_utc")
        == FIXED_GENERATED_AT
    ), f"Status payload is missing DB manifest freshness: {payload}"
    assert (
        payload.get("course_claim_count") == EXPECTED_PROMOTED_COURSE_CLAIMS
    ), f"Status payload is missing promoted course counts: {payload}"
    assert payload.get("claim_evidence_count") == EXPECTED_CLAIM_EVIDENCE, (
        f"Status payload is missing claim evidence counts: {payload}"
    )
    assert payload.get("claim_conflict_count") == EXPECTED_CLAIM_CONFLICTS, (
        f"Status payload is missing claim conflict counts: {payload}"
    )
    assert (
        payload.get("transaction_profile_count")
        == EXPECTED_TRANSACTION_PROFILES
    ), f"Status payload is missing transaction profile counts: {payload}"
    assert (
        payload.get("native_expectation_count") == EXPECTED_NATIVE_EXPECTATIONS
    ), f"Status payload is missing native coverage counts: {payload}"


def test_knowledge_store_cli_ensure_rebuilds_stale_generated_sqlite(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    """The ensure command rebuilds SQLite after raw-spec snapshots change."""
    prepare_snapshot_dir(tmp_path)
    sync_http_raw_spec(tmp_path, generated_at=FIXED_GENERATED_AT)
    _ = build_knowledge_store(repo_root=tmp_path)
    sync_http_raw_spec(tmp_path, generated_at=NEXT_GENERATED_AT)

    exit_code = knowledge_cli_main(["--repo-root", str(tmp_path), "ensure"])
    captured = capsys.readouterr()
    payload = json_object_from_text(captured.out, "knowledge ensure output")
    status_report = cast("dict[str, object]", payload["status_report"])

    assert exit_code == 0, f"Ensure command failed: {exit_code}, {payload}"
    assert payload.get("before_status") == "stale_manifest", (
        f"Ensure should detect stale SQLite before rebuilding: {payload}"
    )
    assert payload.get("rebuilt") is True, (
        f"Ensure should rebuild stale SQLite: {payload}"
    )
    assert status_report.get("raw_spec_manifest_matches_database") is True, (
        f"Ensure should leave SQLite aligned with raw specs: {payload}"
    )
    assert (
        status_report.get("database_raw_spec_manifest_generated_at_utc")
        == NEXT_GENERATED_AT
    ), f"Ensure should update DB ingest freshness: {payload}"


def test_knowledge_store_cli_status_reports_invalid_manifest_with_database(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    """The CLI status command preserves DB health when the manifest is.

    invalid.
    """
    prepare_snapshot_dir(tmp_path)
    sync_http_raw_spec(tmp_path, generated_at=FIXED_GENERATED_AT)
    _ = build_knowledge_store(repo_root=tmp_path)
    corrupt_manifest_timestamp(tmp_path)

    exit_code = knowledge_cli_main(["--repo-root", str(tmp_path), "status"])
    captured = capsys.readouterr()
    payload = json_object_from_text(
        captured.out, "knowledge invalid-manifest status output"
    )

    assert exit_code == 0, (
        f"Invalid manifest should return a status payload: {payload}"
    )
    assert payload.get("status") == "invalid_manifest", (
        f"Invalid manifest should return a status payload: {payload}"
    )
    assert not (payload.get("database_available") is not True), (
        f"Invalid manifest status must preserve DB availability: {payload}"
    )
    assert (
        payload.get("database_raw_spec_manifest_generated_at_utc")
        == FIXED_GENERATED_AT
    ), f"Invalid manifest status lost DB freshness: {payload}"
    assert not (payload.get("raw_spec_manifest_available") is not True), (
        f"Invalid manifest status must expose manifest presence: {payload}"
    )


def test_knowledge_store_cli_status_reports_sqlite_errors_as_json(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    """The CLI reports unreadable SQLite status failures without tracebacks."""
    database_path = tmp_path / DEFAULT_DATABASE_PATH
    database_path.parent.mkdir(parents=True)
    _ = database_path.write_text("not a sqlite database", encoding="utf-8")

    exit_code = knowledge_cli_main(["--repo-root", str(tmp_path), "status"])
    captured = capsys.readouterr()
    payload = json_object_from_text(
        captured.out, "knowledge SQLite failure output"
    )

    assert exit_code == 1, (
        f"Unreadable SQLite should return structured failure JSON: {payload}"
    )
    assert payload.get("status") == "failed", (
        f"Unreadable SQLite should return structured failure JSON: {payload}"
    )
    assert not ("Error" not in str(payload.get("error_type"))), (
        f"SQLite failure should preserve the error type: {payload}"
    )
