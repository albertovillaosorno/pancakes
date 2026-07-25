# ruff: noqa: E501, PLR0913, S404, S603
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001055#repo.mcp.required-tool-surface
# - 001079#repo.make-linter.rule-intake-manual-gate
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end
# pyright: reportAny=false

"""Guarded MCP linter rule editor tools.

Boundary contract:
- Owns: typed MCP rule leases, rule inspection, safe dispositions, and guard
receipts.
- Must not: expose raw SQL, expose a raw file editor, call providers, read
secrets, or push.
- Allows: fixed SQLite transitions, derived snapshots, static code guards, and
local git commits.
- Split when: non-Python linter predicate writers become independently
supported.
- Merge when: quarantine evidence and direct-editor state share one
authoritative workflow module.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
from collections.abc import Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Final, NoReturn, cast

from blueprints.validation.linter_rule_ast_guard import (
    validate_linter_predicate_source,
)
from blueprints.validation.linter_taxonomy import (
    make_linter_rule_family_by_id,
    make_linter_rule_family_for_code,
    make_linter_supported_codes,
)
from catalog.knowledge import (
    DEFAULT_KNOWLEDGE_DB_PATH,
    connect_catalog_plan_ssot,
    knowledge_store_status,
)
from languages.make.raw_specs.paths import resolve_repo_relative_path

from mcp.linter_quarantine import (
    SQLITE_SOURCE_OF_TRUTH,
    ensure_linter_quarantine_database,
    export_linter_quarantine_snapshots,
    linter_quarantine_canonical_json_text,
    linter_quarantine_coverage_ledger_path,
    linter_quarantine_evidence_from_row,
    linter_quarantine_family_id_for_record,
    linter_quarantine_json_mapping,
    linter_quarantine_manifest_path,
    linter_quarantine_repo_relative_path,
    safe_linter_quarantine_source_reference,
    sqlite_linter_quarantine_record_for_candidate,
    sqlite_linter_quarantine_rows,
    update_linter_quarantine_evidence,
)
from mcp.linter_rule_editor_contracts import (
    ACTIONABLE_SOURCE_STATUSES,
    ALLOWED_DISPOSITIONS,
    ALLOWED_INVALID_CLASSES,
    DEFAULT_LEASE_MODE,
    DEFAULT_LEASE_SECONDS,
    LEASE_MODES,
    LINTER_RULE_EDIT_TOOL,
    LINTER_RULE_IMPLEMENT_TOOL,
    LINTER_RULE_MERGE_CANONICAL_TOOL,
    LINTER_RULE_REJECT_INVALID_TOOL,
    LINTER_RULE_ROLLBACK_TOOL,
    MEMO_REQUIRED_FIELDS,
    MIN_MEMO_CHARACTERS,
    MIN_MEMO_POPULATED_FIELDS,
    MIN_MEMO_REFERENCE_COUNT,
    NORMAL_TARGET_STATUSES,
    SEVERITY_RANK,
    VALID_SEVERITIES,
    implementation_contract_payload,
    required_evidence_fields_payload,
    validation_commands_payload,
)

if TYPE_CHECKING:
    from pathlib import Path

    from mcp.models import JsonObject

LEASE_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^linter-rule-lease:[a-f0-9]{32}$"
)
SAFE_WORKER_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9._:/@ -]{1,120}$"
)
JSON_PATH_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:\$|blueprint|scenario|node|module|route|payload)"
    r"(?:[./\[][A-Za-z0-9_@*'\" -]+)+"
)
BOILERPLATE_REPEAT_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(.{80,}?)\1", re.DOTALL
)
MIN_PROOF_TEXT_CHARS: Final = 80
MAX_INSPECT_TEXT_CHARS: Final = 800
MAX_INSPECT_FULL_TEXT_CHARS: Final = 1_200
MAX_INSPECT_MAPPING_ITEMS: Final = 40
MAX_INSPECT_LIST_ITEMS: Final = 20
MAX_COMMIT_MESSAGE_CHARS: Final = 500
MCP_CREATED_COMMIT_MARKER: Final = "MCP-Linter-Rule-Editor: true"
GIT_EXECUTABLE: Final = shutil.which("git") or "git"
REDACTED_TEXT: Final = "[redacted]"
SECRET_KEY_TERMS: Final[frozenset[str]] = frozenset(
    (
        "authorization ",
        "api_key ",
        "apikey ",
        "cookie ",
        "credential ",
        "password ",
        "secret ",
        "token",
    )
)
SECRET_VALUE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?i)(sk-[A-Za-z0-9_-]{8,}|(?:bearer|token|password|secret|api[_-]?key)\s*[:=]\s*[^,\s;]+)"
)
EDITOR_SCHEMA_SQL: Final = """
CREATE TABLE IF NOT EXISTS linter_rule_editor_leases (
  candidate_id TEXT PRIMARY KEY,
  rule_id TEXT NOT NULL,
  worker_id TEXT NOT NULL,
  lease_token TEXT NOT NULL,
  mode TEXT NOT NULL,
  family_filter TEXT NOT NULL,
  status TEXT NOT NULL,
  leased_at_utc TEXT NOT NULL,
  expires_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_linter_rule_editor_leases_worker
  ON linter_rule_editor_leases (worker_id, status, expires_at_utc);

CREATE INDEX IF NOT EXISTS idx_linter_rule_editor_leases_status
  ON linter_rule_editor_leases (status, expires_at_utc, candidate_id);

CREATE TABLE IF NOT EXISTS linter_rule_editor_events (
  event_id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL,
  rule_id TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  worker_id TEXT NOT NULL,
  disposition TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  commit_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_linter_rule_editor_events_candidate
  ON linter_rule_editor_events (candidate_id, created_at_utc);
"""


@dataclass(frozen=True)
class _Lease:
    candidate_id: str
    rule_id: str
    worker_id: str
    lease_token: str
    mode: str
    family_filter: str
    expires_at_utc: str
    replay: bool


def _raise_validation_error(message: str) -> NoReturn:
    raise ValueError(message)


def _raise_type_error(message: str) -> NoReturn:
    raise TypeError(message)


def next_linter_rule(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Lease one actionable linter rule candidate for a worker.

    Returns:
        MCP response payload with either a lease or an empty-queue status.
    """
    worker_id = _worker_id(arguments)
    mode = _lease_mode(arguments)
    family_filter = _optional_text(arguments, "family_filter")
    priority_floor = _optional_int(arguments, "priority_floor")
    _ = _ensure_linter_rule_editor_database(repo_root)
    now = _utc_now()
    with (
        closing(connect_catalog_plan_ssot(repo_root=repo_root)) as connection,
        connection,
    ):
        _expire_stale_leases(connection=connection, now=now)
        replay = _active_worker_lease(
            connection=connection,
            worker_id=worker_id,
            mode=mode,
            family_filter=family_filter,
            now=now,
        )
        if replay is not None:
            return _lease_payload(
                connection=connection,
                lease=replay,
                repo_root=repo_root,
                status="leased",
            )
        row = _select_next_candidate(
            connection=connection,
            mode=mode,
            family_filter=family_filter,
            priority_floor=priority_floor,
            now=now,
        )
        if row is None:
            return {
                "status": "empty",
                "worker_id": worker_id,
                "mode": mode,
                "family_filter": family_filter or None,
                "source_of_truth": SQLITE_SOURCE_OF_TRUTH,
                "allowed_dispositions": list(ALLOWED_DISPOSITIONS),
                "implementation_contract": implementation_contract_payload(),
                "required_evidence_fields": required_evidence_fields_payload(),
                "validation_commands": validation_commands_payload(),
            }
        evidence = linter_quarantine_evidence_from_row(row)
        candidate_id = _candidate_id_from_row(row)
        rule_id = str(row[2])
        lease = _create_lease(
            connection=connection,
            candidate_id=candidate_id,
            rule_id=rule_id,
            worker_id=worker_id,
            mode=mode,
            family_filter=family_filter,
            now=now,
        )
        return _lease_payload(
            connection=connection,
            lease=lease,
            repo_root=repo_root,
            status="leased",
            row=row,
            evidence=evidence,
        )


def inspect_linter_rule(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Inspect one candidate, taxonomy family, and canonical coverage hints.

    Returns:
        MCP response payload describing source evidence and coverage hints.
    """
    output_mode = _output_mode(arguments)
    candidate_id = _optional_text(arguments, "candidate_id")
    rule_id = _optional_text(arguments, "rule_id")
    if not candidate_id and not rule_id:
        _raise_validation_error("candidate_id or rule_id is required.")
    database_path = _require_linter_rule_inspect_database(repo_root)
    with closing(_connect_catalog_plan_read_only(repo_root)) as connection:
        row = (
            sqlite_linter_quarantine_record_for_candidate(
                connection=connection,
                candidate_id=candidate_id,
            )
            if candidate_id
            else _sqlite_record_for_rule(connection=connection, rule_id=rule_id)
        )
        if row is None:
            lookup_key = "candidate_id" if candidate_id else "rule_id"
            lookup_value = candidate_id or rule_id or ""
            _raise_validation_error(f"not_found: {lookup_key}={lookup_value}")
        evidence = linter_quarantine_evidence_from_row(row)
        resolved_candidate_id = _candidate_id_from_row(row)
        family_id = linter_quarantine_family_id_for_record(evidence=evidence)
        family = make_linter_rule_family_by_id(family_id)
        taxonomy_payload = _taxonomy_payload(rule_id=str(row[2]))
        payload: JsonObject = {
            "status": "inspected",
            "candidate_id": resolved_candidate_id,
            "rule_id": str(row[2]),
            "output_mode": output_mode,
            "family_id": family_id,
            "current_status": str(row[4]),
            "existing_predicate_location": family.owner_path,
            "existing_taxonomy_code": taxonomy_payload,
            "existing_tests": [family.focused_test_path],
            "related_quarantine_rows": _related_rows_payload(
                connection, resolved_candidate_id
            ),
            "source_evidence": _source_evidence_payload(
                row=row, evidence=evidence
            ),
            "possible_canonical_equivalents": _canonical_candidates_payload(
                rule_id=str(row[2]), evidence=evidence
            ),
            "classification": _candidate_classification(
                row=row, evidence=evidence
            ),
            "raw_sql_exposed": False,
            "raw_file_editor_exposed": False,
            "live_make_called": False,
            "provider_api_call": False,
            "secret_output": False,
            "database_path": database_path,
        }
        if output_mode in {"full", "debug"}:
            payload["quarantine_evidence"] = _redacted_bounded_json(
                evidence,
                max_text_chars=MAX_INSPECT_FULL_TEXT_CHARS,
            )
        if output_mode == "debug":
            payload["lease_debug"] = _lease_rows_payload(
                connection, resolved_candidate_id
            )
        return payload


def implement_linter_rule(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Validate a submitted linter implementation through guarded MCP contracts.

    Returns:
        Dry-run or committed implementation receipt.
    """
    worker_id = _worker_id(arguments)
    candidate_id = _required_text(arguments, "candidate_id")
    lease_token = _lease_token(arguments)
    target_family = _required_text(arguments, "target_family")
    rule_code = _required_text(arguments, "rule_code")
    severity = _severity(arguments)
    expected_failure_code = _required_text(arguments, "expected_failure_code")
    dry_run = _optional_bool(arguments, "dry_run")
    _ = _ensure_linter_rule_editor_database(repo_root)
    with closing(connect_catalog_plan_ssot(repo_root=repo_root)) as connection:
        _validate_lease(
            connection=connection,
            candidate_id=candidate_id,
            worker_id=worker_id,
            lease_token=lease_token,
        )
        row = _require_candidate_row(
            connection=connection, candidate_id=candidate_id
        )
        evidence = linter_quarantine_evidence_from_row(row)
        family = make_linter_rule_family_by_id(target_family)
        if rule_code != expected_failure_code:
            _raise_validation_error(
                "expected_failure_code must match rule_code for implementation."
            )
        if severity not in family.allowed_severities:
            _raise_validation_error(
                "severity is not allowed by the target linter family."
            )
        memo_report = _validate_technical_memo(
            _json_object_argument(arguments, "technical_implementation_memo")
        )
        predicate_report = validate_linter_predicate_source(
            _required_text(arguments, "python_predicate_code"),
            expected_failure_code=expected_failure_code,
        )
        if not predicate_report.ok:
            _raise_validation_error("; ".join(predicate_report.errors))
        _validate_test_payload(
            arguments=arguments, expected_failure_code=expected_failure_code
        )
        _validate_source_refs(_source_refs(arguments))
        _validate_false_positive_analysis(arguments)
        _validate_evidence_gap_policy(arguments)
        _validate_severity_change(
            arguments=arguments,
            candidate_evidence=evidence,
            new_severity=severity,
        )
        receipt: JsonObject = {
            "status": "dry_run_passed" if dry_run else "rejected_before_write",
            "tool_name": LINTER_RULE_IMPLEMENT_TOOL,
            "candidate_id": candidate_id,
            "rule_id": rule_code,
            "target_family": target_family,
            "severity": severity,
            "predicate_name": predicate_report.predicate_name,
            "memo_validation": memo_report,
            "ast_guard": {
                "ok": predicate_report.ok,
                "inspected_payload_terms": list(
                    predicate_report.inspected_payload_terms
                ),
            },
            "write_actions": [
                "predicate_source ",
                "taxonomy_metadata_if_required ",
                "test_fixture ",
                "focused_test ",
                "sqlite_status_transition ",
                "snapshot_evidence ",
                "git_commit",
            ],
            "active_rule_written": False,
            "accepted_rule_code_written": False,
            "live_make_called": False,
            "provider_api_call": False,
        }
        if dry_run:
            return receipt
        receipt["status"] = "runtime_writer_adapter_required"
        receipt["error_code"] = (
            "implementation_non_dry_run_requires_registered_writer"
        )
        receipt["actionable_next_step"] = (
            "Add a per-family writer adapter that can prove runtime "
            "registration before "
            "linter.rule.implement may write source files."
        )
        _raise_validation_error(str(receipt["error_code"]))


def merge_linter_rule_canonical(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Merge a leased candidate into an exact canonical runtime rule.

    Returns:
        Dry-run or committed canonical-merge receipt.
    """
    worker_id = _worker_id(arguments)
    candidate_id = _required_text(arguments, "candidate_id")
    lease_token = _lease_token(arguments)
    canonical_rule_code = _required_text(arguments, "canonical_rule_code")
    merge_rationale = _proof_text(arguments, "merge_rationale")
    equivalence_proof = _proof_text(arguments, "equivalence_proof")
    test_or_evidence_ref = safe_linter_quarantine_source_reference(
        _required_text(arguments, "test_or_evidence_ref")
    )
    source_refs = _source_refs(arguments)
    dry_run = _optional_bool(arguments, "dry_run")
    _validate_source_refs(source_refs)
    if canonical_rule_code not in make_linter_supported_codes():
        _raise_validation_error(
            "canonical_rule_code must be a supported Make linter code."
        )
    if (
        canonical_rule_code not in merge_rationale
        or canonical_rule_code not in equivalence_proof
    ):
        _raise_validation_error(
            "canonical merge proof must name the exact canonical_rule_code."
        )
    family = make_linter_rule_family_for_code(canonical_rule_code)
    disposition_payload: JsonObject = {
        "disposition": "canonical_equivalent",
        "canonical_rule_code": canonical_rule_code,
        "merge_rationale": merge_rationale,
        "equivalence_proof": equivalence_proof,
        "test_or_evidence_ref": test_or_evidence_ref,
        "source_refs": list(source_refs),
        "family_id": family.family_id,
        "active_rule_written": False,
        "accepted_rule_code_written": False,
    }
    return _apply_disposition(
        arguments=arguments,
        repo_root=repo_root,
        tool_name=LINTER_RULE_MERGE_CANONICAL_TOOL,
        worker_id=worker_id,
        candidate_id=candidate_id,
        lease_token=lease_token,
        dry_run=dry_run,
        disposition="canonical_equivalent",
        review_state="implemented",
        sqlite_status="implemented",
        promotion_state="candidate_implemented_by_canonical_equivalent",
        payload=disposition_payload,
    )


def reject_invalid_linter_rule(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Reject a leased candidate as a proven invalid non-linter artifact.

    Returns:
        Dry-run or committed invalid-rejection receipt.
    """
    worker_id = _worker_id(arguments)
    candidate_id = _required_text(arguments, "candidate_id")
    lease_token = _lease_token(arguments)
    invalid_reason = _proof_text(arguments, "invalid_reason")
    pattern_class = _invalid_pattern_class(arguments)
    proof_excerpt = _proof_text(arguments, "proof_excerpt")
    source_refs = _source_refs(arguments)
    dry_run = _optional_bool(arguments, "dry_run")
    _validate_source_refs(source_refs)
    disposition_payload: JsonObject = {
        "disposition": "invalid",
        "invalid_reason": invalid_reason,
        "pattern_class": pattern_class,
        "proof_excerpt": proof_excerpt,
        "source_refs": list(source_refs),
        "active_rule_written": False,
        "accepted_rule_code_written": False,
    }
    return _apply_disposition(
        arguments=arguments,
        repo_root=repo_root,
        tool_name=LINTER_RULE_REJECT_INVALID_TOOL,
        worker_id=worker_id,
        candidate_id=candidate_id,
        lease_token=lease_token,
        dry_run=dry_run,
        disposition="invalid",
        review_state="rejected",
        sqlite_status="rejected",
        promotion_state="candidate_rejected_invalid",
        payload=disposition_payload,
    )


def edit_linter_rule(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Validate an edit request for an existing implemented linter rule.

    Returns:
        Dry-run edit receipt or a committed edit receipt.
    """
    worker_id = _worker_id(arguments)
    rule_code = _required_text(arguments, "rule_code")
    lease_token = _lease_token(arguments)
    dry_run = _optional_bool(arguments, "dry_run")
    if rule_code not in make_linter_supported_codes():
        _raise_validation_error(
            "rule_code must be an existing supported Make linter code."
        )
    _ = _ensure_linter_rule_editor_database(repo_root)
    with closing(connect_catalog_plan_ssot(repo_root=repo_root)) as connection:
        lease_row = _active_rule_lease(connection=connection, rule_id=rule_code)
        if lease_row is None:
            _raise_validation_error(
                "lease_token_mismatch: no active lease for rule_code."
            )
        _validate_lease(
            connection=connection,
            candidate_id=str(lease_row[0]),
            worker_id=worker_id,
            lease_token=lease_token,
        )
    memo_report = _validate_technical_memo(
        _json_object_argument(arguments, "technical_implementation_memo")
    )
    patch_code = _required_text(arguments, "patch_code")
    updated_test_code = _required_text(arguments, "updated_test_code")
    _validate_patch_source(patch_code)
    _validate_test_source(updated_test_code, expected_failure_code=rule_code)
    _ = _proof_text(arguments, "regression_reason")
    _validate_source_refs(_source_refs(arguments))
    _validate_edit_severity_downgrade(arguments)
    if dry_run:
        return {
            "status": "dry_run_passed",
            "tool_name": LINTER_RULE_EDIT_TOOL,
            "rule_code": rule_code,
            "worker_id": worker_id,
            "memo_validation": memo_report,
            "active_rule_written": False,
            "live_make_called": False,
            "provider_api_call": False,
        }
    _raise_validation_error("edit_non_dry_run_requires_registered_writer")


def linter_rule_status(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Summarize linter editor, quarantine, duplicate, and lease health.

    Returns:
        MCP response payload with quarantine, duplicate, and lease counts.
    """
    include_debug = _optional_bool(arguments, "include_debug")
    _ = _ensure_linter_rule_editor_database(repo_root)
    now = _utc_now()
    with closing(connect_catalog_plan_ssot(repo_root=repo_root)) as connection:
        with connection:
            _expire_stale_leases(connection=connection, now=now)
        rows = sqlite_linter_quarantine_rows(connection)
        counts = _status_counts(rows)
        history_visibility = _history_visibility_payload(repo_root=repo_root)
        visible_counts = _visible_status_counts(
            current_counts=counts,
            current_row_count=len(rows),
            history_visibility=history_visibility,
        )
        counter_source = (
            "review_coverage_ledger_fallback"
            if visible_counts != counts
            else "sqlite_current_rows"
        )
        duplicate_ids = _duplicate_ids(rows)
        duplicate_source_headings = _duplicate_source_headings(rows)
        active_leases = _lease_count(connection, status="active")
        stale_leases = _lease_count(connection, status="expired")
        payload: JsonObject = {
            "status": "summarized",
            "source_of_truth": SQLITE_SOURCE_OF_TRUTH,
            "counter_source": counter_source,
            "current_sqlite_record_count": len(rows),
            "implemented": visible_counts["implemented"],
            "canonical_equivalent": visible_counts["canonical_equivalent"],
            "duplicate": visible_counts["duplicate"],
            "invalid_rejected": visible_counts["invalid"],
            "not_implemented": visible_counts["not_implemented"],
            "blocked": visible_counts["blocked"],
            "leased": active_leases,
            "stale_leases": stale_leases,
            "mismatch_count": (
                0
                if not duplicate_ids
                and not duplicate_source_headings
                and not visible_counts["duplicate"]
                else 1
            ),
            "duplicate_ids": duplicate_ids,
            "duplicate_source_heading_pairs": duplicate_source_headings,
            "history_visibility": history_visibility,
            **_historical_observability_payload(
                current_row_count=len(rows),
                history_visibility=history_visibility,
            ),
            "validation_status": {
                "duplicate_ids": not duplicate_ids,
                "duplicate_source_heading_pairs": not duplicate_source_headings,
                "blocked_is_exceptional": True,
                "raw_sql_tool_exposed": False,
                "raw_file_editor_tool_exposed": False,
                "live_make_called": False,
            },
            "allowed_dispositions": list(ALLOWED_DISPOSITIONS),
            "normal_target_statuses": list(NORMAL_TARGET_STATUSES),
        }
        if include_debug:
            payload["debug"] = {
                "row_count": len(rows),
                "lease_rows": _all_lease_rows_payload(connection),
            }
        return payload


def rollback_linter_rule(
    arguments: Mapping[str, object], repo_root: Path
) -> JsonObject:
    """Rollback one MCP-created linter-rule commit when explicit evidence.

    allows.

    it.

    Returns:
        Dry-run or committed rollback receipt.
    """
    commit_hash = _required_text(arguments, "commit_hash")
    rule_id = _required_text(arguments, "rule_id")
    rollback_reason = _proof_text(arguments, "rollback_reason")
    operator_confirmation = _optional_bool(arguments, "operator_confirmation")
    automated_evidence = _optional_text(arguments, "automated_evidence")
    dry_run = _optional_bool(arguments, "dry_run")
    if (
        not operator_confirmation
        and len(automated_evidence) < MIN_PROOF_TEXT_CHARS
    ):
        _raise_validation_error(
            "rollback_requires_operator_confirmation_or_automated_evidence"
        )
    _require_mcp_created_commit(
        repo_root=repo_root, commit_hash=commit_hash, rule_id=rule_id
    )
    if dry_run:
        return {
            "status": "dry_run_passed",
            "tool_name": LINTER_RULE_ROLLBACK_TOOL,
            "commit_hash": commit_hash,
            "rule_id": rule_id,
            "rollback_reason": rollback_reason,
            "operator_confirmation": operator_confirmation,
            "automated_evidence_present": bool(automated_evidence),
            "push_performed": False,
        }
    _require_clean_git_worktree(repo_root)
    _run_git(repo_root, "revert", "--no-edit", commit_hash)
    new_hash = _git_head(repo_root)
    return {
        "status": "rolled_back",
        "tool_name": LINTER_RULE_ROLLBACK_TOOL,
        "commit_hash": commit_hash,
        "rollback_commit_hash": new_hash,
        "rule_id": rule_id,
        "push_performed": False,
    }


def _ensure_linter_rule_editor_database(repo_root: Path) -> str:
    status = ensure_linter_quarantine_database(repo_root)
    with (
        closing(connect_catalog_plan_ssot(repo_root=repo_root)) as connection,
        connection,
    ):
        _ = connection.executescript(EDITOR_SCHEMA_SQL)
    return status.database_path


def _require_linter_rule_inspect_database(repo_root: Path) -> str:
    status = knowledge_store_status(repo_root=repo_root)
    if not status.database_available:
        _raise_validation_error(
            "not_found: Make knowledge SQLite is unavailable for read-only "
            "inspect: " + status.status
        )
    with closing(_connect_catalog_plan_read_only(repo_root)) as connection:
        if not _sqlite_table_exists(
            connection=connection, table_name="linter_quarantine_records"
        ):
            _raise_validation_error(
                "not_found: linter_quarantine_records is unavailable for "
                "read-only inspect."
            )
    return status.database_path


def _connect_catalog_plan_read_only(repo_root: Path) -> sqlite3.Connection:
    resolved_database = resolve_repo_relative_path(
        repo_root, DEFAULT_KNOWLEDGE_DB_PATH
    ).resolve()
    if not resolved_database.is_file():
        _raise_validation_error(
            "not_found: Make knowledge SQLite database is missing."
        )
    connection = sqlite3.connect(
        f"{resolved_database.as_uri()}?mode=ro",
        timeout=5.0,
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    return connection


def _sqlite_table_exists(
    *, connection: sqlite3.Connection, table_name: str
) -> bool:
    row = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _worker_id(arguments: Mapping[str, object]) -> str:
    worker_id = _required_text(arguments, "worker_id")
    if not SAFE_WORKER_ID_PATTERN.fullmatch(worker_id):
        _raise_validation_error("worker_id contains unsupported characters.")
    return worker_id


def _lease_mode(arguments: Mapping[str, object]) -> str:
    mode = _optional_text(arguments, "mode") or DEFAULT_LEASE_MODE
    if mode not in LEASE_MODES:
        allowed = ", ".join(sorted(LEASE_MODES))
        _raise_validation_error(f"mode must be one of: {allowed}.")
    return mode


def _output_mode(arguments: Mapping[str, object]) -> str:
    output_mode = _optional_text(arguments, "output_mode") or "compact"
    if output_mode not in {"compact", "full", "debug"}:
        _raise_validation_error("output_mode must be compact, full, or debug.")
    return output_mode


def _lease_token(arguments: Mapping[str, object]) -> str:
    token = _required_text(arguments, "lease_token")
    if not LEASE_TOKEN_PATTERN.fullmatch(token):
        _raise_validation_error("lease_token_mismatch: malformed lease token.")
    return token


def _required_text(arguments: Mapping[str, object], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str):
        _raise_type_error(f"missing_required_field: {key}")
    text = value.strip()
    if not text:
        _raise_validation_error(f"missing_required_field: {key}")
    if _contains_secret_marker(text):
        _raise_validation_error(f"secret_like_value_rejected: {key}")
    return text


def _optional_text(arguments: Mapping[str, object], key: str) -> str:
    value = arguments.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        _raise_type_error(f"{key} must be a string.")
    text = value.strip()
    if text and _contains_secret_marker(text):
        _raise_validation_error(f"secret_like_value_rejected: {key}")
    return text


def _optional_bool(arguments: Mapping[str, object], key: str) -> bool:
    value = arguments.get(key)
    if value is None:
        return False
    if not isinstance(value, bool):
        _raise_type_error(f"{key} must be a boolean.")
    return value


def _optional_int(arguments: Mapping[str, object], key: str) -> int | None:
    value = arguments.get(key)
    if value is None:
        return None
    if not isinstance(value, int):
        _raise_type_error(f"{key} must be an integer.")
    return value


def _contains_secret_marker(value: str) -> bool:
    lowered = value.casefold()
    return any(
        marker in lowered
        for marker in (".env", "bearer ", "password", "secret=", "token=")
    )


def _json_object_argument(
    arguments: Mapping[str, object], key: str
) -> JsonObject:
    value = arguments.get(key)
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        return {
            str(item_key): item_value
            for item_key, item_value in mapping.items()
        }
    if isinstance(value, str):
        parsed = cast("object", json.loads(value))
        if isinstance(parsed, Mapping):
            mapping = cast("Mapping[object, object]", parsed)
            return {
                str(item_key): item_value
                for item_key, item_value in mapping.items()
            }
    _raise_type_error(f"{key} must be a JSON object.")


def _source_refs(arguments: Mapping[str, object]) -> tuple[str, ...]:
    raw = arguments.get("source_refs")
    parsed = cast("object", json.loads(raw)) if isinstance(raw, str) else raw
    if not isinstance(parsed, list) or not parsed:
        _raise_validation_error("source_refs must be a non-empty JSON array.")
    refs: list[str] = []
    parsed_refs = cast("list[object]", parsed)
    for item in parsed_refs:
        if not isinstance(item, str):
            _raise_type_error("source_refs items must be strings.")
        refs.append(safe_linter_quarantine_source_reference(item))
    return tuple(refs)


def _validate_source_refs(source_refs: Sequence[str]) -> None:
    if len(source_refs) < MIN_MEMO_REFERENCE_COUNT:
        _raise_validation_error(
            "source_refs must include at least two concrete local references."
        )
    for source_ref in source_refs:
        if not source_ref or source_ref.startswith(("http://", "https://")):
            _raise_validation_error(
                "source_refs must be local evidence references."
            )


def _proof_text(arguments: Mapping[str, object], key: str) -> str:
    value = _required_text(arguments, key)
    if len(value) < MIN_PROOF_TEXT_CHARS:
        _raise_validation_error(
            f"{key} must include evidence-backed proof, not a shallow note."
        )
    return value


def _severity(arguments: Mapping[str, object]) -> str:
    severity = _required_text(arguments, "severity").casefold()
    if severity not in VALID_SEVERITIES:
        allowed = ", ".join(sorted(VALID_SEVERITIES))
        _raise_validation_error(f"severity must be one of: {allowed}.")
    return severity


def _candidate_id_from_row(row: tuple[object, ...]) -> str:
    evidence = linter_quarantine_evidence_from_row(row)
    candidate_id = str(evidence.get("candidate_id") or row[2]).strip()
    if not candidate_id:
        _raise_validation_error(
            "quarantine row is missing candidate_id evidence."
        )
    return candidate_id


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _lease_expiration(now: str) -> str:
    return (
        _parse_utc(now) + timedelta(seconds=DEFAULT_LEASE_SECONDS)
    ).isoformat()


def _lease_token_for(*, worker_id: str, candidate_id: str, now: str) -> str:
    seed = (
        f"{worker_id}\n{candidate_id}\n{now}\n{datetime.now(UTC).timestamp()}"
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]
    return f"linter-rule-lease:{digest}"


def _expire_stale_leases(*, connection: sqlite3.Connection, now: str) -> None:
    _ = connection.execute(
        """
        UPDATE linter_rule_editor_leases
        SET status = 'expired', updated_at_utc = ?
        WHERE status = 'active'
          AND expires_at_utc <= ?
        """,
        (now, now),
    )


def _active_worker_lease(
    *,
    connection: sqlite3.Connection,
    worker_id: str,
    mode: str,
    family_filter: str,
    now: str,
) -> _Lease | None:
    row = connection.execute(
        """
        SELECT candidate_id, rule_id, worker_id, lease_token, mode,
        family_filter, expires_at_utc
        FROM linter_rule_editor_leases
        WHERE worker_id = ?
          AND mode = ?
          AND family_filter = ?
          AND status = 'active'
          AND expires_at_utc > ?
        ORDER BY leased_at_utc
        LIMIT 1
        """,
        (worker_id, mode, family_filter, now),
    ).fetchone()
    if row is None:
        return None
    return _lease_from_row(row, replay=True)


def _active_rule_lease(
    *,
    connection: sqlite3.Connection,
    rule_id: str,
) -> tuple[object, ...] | None:
    return cast(
        "tuple[object, ...] | None",
        connection.execute(
            """
            SELECT candidate_id, rule_id, worker_id, lease_token, mode,
            family_filter,
                   expires_at_utc
            FROM linter_rule_editor_leases
            WHERE rule_id = ?
              AND status = 'active'
              AND expires_at_utc > ?
            ORDER BY leased_at_utc
            LIMIT 1
            """,
            (rule_id, _utc_now()),
        ).fetchone(),
    )


def _lease_from_row(row: object, *, replay: bool) -> _Lease:
    values = cast("tuple[object, ...]", row)
    return _Lease(
        candidate_id=str(values[0]),
        rule_id=str(values[1]),
        worker_id=str(values[2]),
        lease_token=str(values[3]),
        mode=str(values[4]),
        family_filter=str(values[5]),
        expires_at_utc=str(values[6]),
        replay=replay,
    )


def _select_next_candidate(
    *,
    connection: sqlite3.Connection,
    mode: str,
    family_filter: str,
    priority_floor: int | None,
    now: str,
) -> tuple[object, ...] | None:
    _ = mode
    _ = priority_floor
    active_lease_rows = connection.execute(
        """
        SELECT candidate_id
        FROM linter_rule_editor_leases
        WHERE status = 'active'
          AND expires_at_utc > ?
        """,
        (now,),
    ).fetchall()
    leased_candidate_ids = {str(row[0]) for row in active_lease_rows}
    for row in sqlite_linter_quarantine_rows(connection):
        candidate_id = _candidate_id_from_row(row)
        if candidate_id in leased_candidate_ids:
            continue
        if str(row[4]) not in ACTIONABLE_SOURCE_STATUSES:
            continue
        evidence = linter_quarantine_evidence_from_row(row)
        family_id = linter_quarantine_family_id_for_record(evidence=evidence)
        if family_filter and family_id != family_filter:
            continue
        return row
    return None


def _create_lease(
    *,
    connection: sqlite3.Connection,
    candidate_id: str,
    rule_id: str,
    worker_id: str,
    mode: str,
    family_filter: str,
    now: str,
) -> _Lease:
    lease_token = _lease_token_for(
        worker_id=worker_id, candidate_id=candidate_id, now=now
    )
    expires_at = _lease_expiration(now)
    _ = connection.execute(
        """
        INSERT INTO linter_rule_editor_leases (
          candidate_id, rule_id, worker_id, lease_token, mode, family_filter,
          status,
          leased_at_utc, expires_at_utc, updated_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
        ON CONFLICT(candidate_id) DO UPDATE SET
          rule_id = excluded.rule_id,
          worker_id = excluded.worker_id,
          lease_token = excluded.lease_token,
          mode = excluded.mode,
          family_filter = excluded.family_filter,
          status = excluded.status,
          leased_at_utc = excluded.leased_at_utc,
          expires_at_utc = excluded.expires_at_utc,
          updated_at_utc = excluded.updated_at_utc
        """,
        (
            candidate_id,
            rule_id,
            worker_id,
            lease_token,
            mode,
            family_filter,
            now,
            expires_at,
            now,
        ),
    )
    return _Lease(
        candidate_id=candidate_id,
        rule_id=rule_id,
        worker_id=worker_id,
        lease_token=lease_token,
        mode=mode,
        family_filter=family_filter,
        expires_at_utc=expires_at,
        replay=False,
    )


def _lease_payload(
    *,
    connection: sqlite3.Connection,
    lease: _Lease,
    repo_root: Path,
    status: str,
    row: tuple[object, ...] | None = None,
    evidence: JsonObject | None = None,
) -> JsonObject:
    candidate_row = row or _require_candidate_row(
        connection=connection,
        candidate_id=lease.candidate_id,
    )
    candidate_evidence = evidence or linter_quarantine_evidence_from_row(
        candidate_row
    )
    family_id = linter_quarantine_family_id_for_record(
        evidence=candidate_evidence
    )
    return {
        "status": status,
        "rule_id": lease.rule_id,
        "candidate_id": lease.candidate_id,
        "lease_token": lease.lease_token,
        "lease_replay": lease.replay,
        "lease_expires_at_utc": lease.expires_at_utc,
        "worker_id": lease.worker_id,
        "family_id": family_id,
        "current_status": str(candidate_row[4]),
        "source_heading": str(candidate_evidence.get("original_heading", "")),
        "source_excerpt": _source_excerpt(candidate_evidence),
        "source_ref": str(
            candidate_evidence.get("source_file") or candidate_row[1]
        ),
        "existing_canonical_candidates": _canonical_candidates_payload(
            rule_id=lease.rule_id,
            evidence=candidate_evidence,
        ),
        "allowed_dispositions": list(ALLOWED_DISPOSITIONS),
        "implementation_contract": implementation_contract_payload(),
        "required_evidence_fields": required_evidence_fields_payload(),
        "validation_commands": validation_commands_payload(),
        "source_of_truth": SQLITE_SOURCE_OF_TRUTH,
        "database_path": linter_quarantine_repo_relative_path(
            repo_root=repo_root,
            path=resolve_repo_relative_path(
                repo_root, DEFAULT_KNOWLEDGE_DB_PATH
            ),
        ),
    }


def _source_excerpt(evidence: Mapping[str, object]) -> str:
    for key in (
        "proposed_predicate_text ",
        "missing_evidence ",
        "quarantine_reason",
    ):
        value = str(evidence.get(key, "")).strip()
        if value:
            return value[:500]
    return ""


def _canonical_candidates_payload(
    *,
    rule_id: str,
    evidence: Mapping[str, object],
) -> list[JsonObject]:
    candidates: list[JsonObject] = []
    integration = linter_quarantine_json_mapping(
        evidence.get("integration_review")
    )
    canonical_rule_code = str(
        integration.get("canonical_rule_code", "")
    ).strip()
    if canonical_rule_code:
        candidates.append(
            {
                "rule_code": canonical_rule_code,
                "source": "integration_review",
                "family_id": _safe_inspect_text(
                    integration.get("family_id", "")
                ),
                "coverage": _safe_inspect_text(
                    integration.get("validation_reference", "")
                ),
            }
        )
    if rule_id in make_linter_supported_codes():
        family = make_linter_rule_family_for_code(rule_id)
        candidates.append(
            {
                "rule_code": rule_id,
                "source": "taxonomy",
                "family_id": family.family_id,
                "owner_path": family.owner_path,
                "focused_test_path": family.focused_test_path,
            }
        )
    deduped: dict[str, JsonObject] = {}
    for candidate in candidates:
        deduped[str(candidate["rule_code"])] = candidate
    return list(deduped.values())


def _taxonomy_payload(*, rule_id: str) -> JsonObject | None:
    if rule_id not in make_linter_supported_codes():
        return None
    family = make_linter_rule_family_for_code(rule_id)
    return {
        "rule_code": rule_id,
        "family_id": family.family_id,
        "owner_path": family.owner_path,
        "focused_test_path": family.focused_test_path,
        "allowed_severities": list(family.allowed_severities),
        "gate_behavior": family.gate_behavior,
    }


def _related_rows_payload(
    connection: sqlite3.Connection,
    candidate_id: str,
) -> list[JsonObject]:
    row = sqlite_linter_quarantine_record_for_candidate(
        connection=connection,
        candidate_id=candidate_id,
    )
    if row is None:
        return []
    evidence = linter_quarantine_evidence_from_row(row)
    return [
        {
            "candidate_id": candidate_id,
            "rule_id": str(row[2]),
            "status": str(row[4]),
            "source_ref": _safe_inspect_text(
                evidence.get("source_file") or row[1]
            ),
            "heading": _safe_inspect_text(evidence.get("original_heading", "")),
        }
    ]


def _source_evidence_payload(
    *,
    row: tuple[object, ...],
    evidence: Mapping[str, object],
) -> JsonObject:
    return {
        "candidate_id": _candidate_id_from_row(row),
        "source_file": _safe_inspect_text(
            evidence.get("source_file") or row[1]
        ),
        "original_heading": _safe_inspect_text(
            evidence.get("original_heading", "")
        ),
        "quarantine_reason": _safe_inspect_text(
            evidence.get("quarantine_reason", "")
        ),
        "missing_evidence": _safe_inspect_text(
            evidence.get("missing_evidence", "")
        ),
        "proposed_predicate_text": _safe_inspect_text(
            evidence.get("proposed_predicate_text", "")
        ),
    }


def _redacted_bounded_json(value: object, *, max_text_chars: int) -> object:
    if isinstance(value, Mapping):
        payload: JsonObject = {}
        items = list(cast("Mapping[object, object]", value).items())
        for raw_key, item_value in items[:MAX_INSPECT_MAPPING_ITEMS]:
            key = str(raw_key)
            if _is_secret_key(key):
                payload[key] = REDACTED_TEXT
            else:
                payload[key] = _redacted_bounded_json(
                    item_value,
                    max_text_chars=max_text_chars,
                )
        if len(items) > MAX_INSPECT_MAPPING_ITEMS:
            payload["_truncated_key_count"] = (
                len(items) - MAX_INSPECT_MAPPING_ITEMS
            )
        return payload
    if isinstance(value, list):
        raw_values = cast("list[object]", value)
        values = [
            _redacted_bounded_json(item, max_text_chars=max_text_chars)
            for item in raw_values[:MAX_INSPECT_LIST_ITEMS]
        ]
        if len(raw_values) > MAX_INSPECT_LIST_ITEMS:
            values.append(
                {
                    "_truncated_item_count": len(raw_values)
                    - MAX_INSPECT_LIST_ITEMS
                }
            )
        return values
    if isinstance(value, str):
        return _safe_inspect_text(value, max_chars=max_text_chars)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _safe_inspect_text(value, max_chars=max_text_chars)


def _safe_inspect_text(
    value: object, *, max_chars: int = MAX_INSPECT_TEXT_CHARS
) -> str:
    text = str(value)
    if _is_secret_key(text):
        return REDACTED_TEXT
    redacted = SECRET_VALUE_PATTERN.sub(REDACTED_TEXT, text)
    if len(redacted) <= max_chars:
        return redacted
    return f"{redacted[:max_chars]}...[truncated]"


def _is_secret_key(value: str) -> bool:
    normalized = value.replace("-", "_").casefold()
    return any(term in normalized for term in SECRET_KEY_TERMS)


def _candidate_classification(
    *, row: tuple[object, ...], evidence: Mapping[str, object]
) -> str:
    integration = linter_quarantine_json_mapping(
        evidence.get("integration_review")
    )
    disposition = str(integration.get("disposition", "")).strip()
    if disposition in {"canonical_equivalent", "duplicate", "invalid"}:
        return disposition
    if str(row[2]) in make_linter_supported_codes():
        return "exact_canonical_equivalent"
    current_review = linter_quarantine_json_mapping(
        evidence.get("current_review")
    )
    if str(current_review.get("implementation_status", "")) == "implemented":
        return "true_runtime_linter_candidate"
    if str(row[4]) == "blocked":
        return "valid_but_not_implementable_yet"
    return "true_runtime_linter_candidate"


def _lease_rows_payload(
    connection: sqlite3.Connection, candidate_id: str
) -> list[JsonObject]:
    if not _sqlite_table_exists(
        connection=connection, table_name="linter_rule_editor_leases"
    ):
        return []
    rows = connection.execute(
        """
        SELECT worker_id, lease_token, mode, status, expires_at_utc
        FROM linter_rule_editor_leases
        WHERE candidate_id = ?
        ORDER BY updated_at_utc DESC
        """,
        (candidate_id,),
    ).fetchall()
    return [
        {
            "worker_id": _safe_inspect_text(row[0]),
            "lease_token_present": bool(str(row[1])),
            "lease_token_sha256": _sha256_text(str(row[1]))[:16],
            "mode": str(row[2]),
            "status": str(row[3]),
            "expires_at_utc": str(row[4]),
        }
        for row in rows
    ]


def _all_lease_rows_payload(connection: sqlite3.Connection) -> list[JsonObject]:
    rows = connection.execute(
        """
        SELECT candidate_id, rule_id, worker_id, mode, status, expires_at_utc
        FROM linter_rule_editor_leases
        ORDER BY updated_at_utc DESC, candidate_id
        LIMIT 100
        """
    ).fetchall()
    return [
        {
            "candidate_id": str(row[0]),
            "rule_id": str(row[1]),
            "worker_id": str(row[2]),
            "mode": str(row[3]),
            "status": str(row[4]),
            "expires_at_utc": str(row[5]),
        }
        for row in rows
    ]


def _sqlite_record_for_rule(
    *,
    connection: sqlite3.Connection,
    rule_id: str,
) -> tuple[object, ...] | None:
    return cast(
        "tuple[object, ...] | None",
        connection.execute(
            """
            SELECT quarantine_id, subject_ref, finding_code, severity, status,
            evidence_json,
                   source_kind, source_ref, created_at_utc, updated_at_utc,
                   resolved_at_utc
            FROM linter_quarantine_records
            WHERE finding_code = ?
            ORDER BY updated_at_utc DESC, quarantine_id
            LIMIT 1
            """,
            (rule_id,),
        ).fetchone(),
    )


def _require_candidate_row(
    *,
    connection: sqlite3.Connection,
    candidate_id: str,
) -> tuple[object, ...]:
    row = sqlite_linter_quarantine_record_for_candidate(
        connection=connection,
        candidate_id=candidate_id,
    )
    if row is None:
        _raise_validation_error(f"unknown_candidate_id: {candidate_id}")
    return row


def _validate_lease(
    *,
    connection: sqlite3.Connection,
    candidate_id: str,
    worker_id: str,
    lease_token: str,
) -> None:
    row = connection.execute(
        """
        SELECT worker_id, lease_token, status, expires_at_utc
        FROM linter_rule_editor_leases
        WHERE candidate_id = ?
        LIMIT 1
        """,
        (candidate_id,),
    ).fetchone()
    if row is None:
        _raise_validation_error(
            "lease_token_mismatch: no active lease for candidate."
        )
    expected_worker = str(row[0])
    expected_token = str(row[1])
    status = str(row[2])
    expires_at = str(row[3])
    now = _utc_now()
    if status != "active" or expires_at <= now:
        _raise_validation_error(
            "lease_token_mismatch: lease is expired or inactive."
        )
    if expected_worker != worker_id:
        _raise_validation_error("worker_id_mismatch")
    if expected_token != lease_token:
        _raise_validation_error("lease_token_mismatch")


def _validate_technical_memo(memo: JsonObject) -> JsonObject:
    missing = [
        field
        for field in MEMO_REQUIRED_FIELDS
        if field not in memo or not _memo_field_populated(memo[field])
    ]
    if missing:
        field_name = missing[0]
        _raise_validation_error(
            f"missing_required_field: "
            f"technical_implementation_memo.{field_name}"
        )
    memo_text = linter_quarantine_canonical_json_text(memo)
    if len(memo_text) < MIN_MEMO_CHARACTERS:
        _raise_validation_error("technical_implementation_memo_too_shallow")
    populated = sum(
        1
        for field in MEMO_REQUIRED_FIELDS
        if _memo_field_populated(memo.get(field))
    )
    refs = _memo_refs(memo)
    if populated < MIN_MEMO_POPULATED_FIELDS:
        _raise_validation_error(
            "technical_implementation_memo_missing_populated_fields"
        )
    if len(refs) < MIN_MEMO_REFERENCE_COUNT:
        _raise_validation_error(
            "technical_implementation_memo_missing_json_path_or_source_refs"
        )
    if (
        not str(memo["pass_condition"]).strip()
        or not str(memo["failure_condition"]).strip()
    ):
        _raise_validation_error(
            "technical_implementation_memo_requires_pass_and_fail_cases"
        )
    if not str(memo["false_positive_risk"]).strip():
        _raise_validation_error(
            "missing_required_field: "
            "technical_implementation_memo.false_positive_risk"
        )
    if BOILERPLATE_REPEAT_PATTERN.search(memo_text):
        _raise_validation_error(
            "technical_implementation_memo_repeated_boilerplate"
        )
    return {
        "ok": True,
        "character_count": len(memo_text),
        "populated_field_count": populated,
        "reference_count": len(refs),
        "references": refs,
    }


def _memo_field_populated(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        items = cast("list[object]", value)
        return any(_memo_field_populated(item) for item in items)
    return value is not None


def _memo_refs(memo: Mapping[str, object]) -> list[str]:
    refs: list[str] = []
    for key in ("blueprint_json_paths_examined", "evidence_refs"):
        value = memo.get(key)
        if isinstance(value, list):
            items = cast("list[object]", value)
            refs.extend(
                str(item)
                for item in items
                if isinstance(item, str) and item.strip()
            )
        elif isinstance(value, str) and value.strip():
            refs.append(value.strip())
    memo_text = linter_quarantine_canonical_json_text(
        {str(key): value for key, value in memo.items()}
    )
    refs.extend(
        match.group(0) for match in JSON_PATH_PATTERN.finditer(memo_text)
    )
    return sorted(set(refs))


def _validate_test_payload(
    *,
    arguments: Mapping[str, object],
    expected_failure_code: str,
) -> None:
    fixture = _json_object_argument(arguments, "fixture_json")
    if "pass" not in fixture and "expected_pass_case" not in fixture:
        _raise_validation_error("missing_test_case: no passing fixture")
    if "fail" not in fixture and "expected_fail_case" not in fixture:
        _raise_validation_error("missing_test_case: no failing fixture")
    pass_case = _required_text(arguments, "expected_pass_case")
    fail_case = _required_text(arguments, "expected_fail_case")
    if pass_case == fail_case:
        _raise_validation_error(
            "expected_pass_case and expected_fail_case must differ."
        )
    test_code = _required_text(arguments, "test_code")
    _validate_test_source(
        test_code, expected_failure_code=expected_failure_code
    )


def _validate_test_source(
    test_code: str, *, expected_failure_code: str
) -> None:
    guard = validate_linter_predicate_source(
        f"from typing import Mapping\n\n{_test_source_probe(test_code, expected_failure_code)}",
        expected_failure_code=expected_failure_code,
    )
    if "unauthorized_import" in "; ".join(guard.errors):
        _raise_validation_error("; ".join(guard.errors))
    if expected_failure_code not in test_code:
        _raise_validation_error("missing_test_case: no finding code assertion")
    if "severity" not in test_code.casefold():
        _raise_validation_error("missing_test_case: no severity assertion")
    if "pass" not in test_code.casefold():
        _raise_validation_error("missing_test_case: no passing fixture")
    if "fail" not in test_code.casefold():
        _raise_validation_error("missing_test_case: no failing fixture")


def _test_source_probe(test_code: str, expected_failure_code: str) -> str:
    escaped = json.dumps(test_code[:200])
    return (
        "def test_source_probe(node: Mapping[str, object]) -> bool:\n"
        f"    evidence = {escaped}\n    return node.get('module') == {expected_failure_code!r} and bool(evidence)\n"
    )


def _validate_false_positive_analysis(arguments: Mapping[str, object]) -> None:
    text = _proof_text(arguments, "false_positive_analysis")
    if (
        "false positive" not in text.casefold()
        and "valid scenario" not in text.casefold()
    ):
        _raise_validation_error(
            "false_positive_analysis must name the false-positive boundary."
        )


def _validate_evidence_gap_policy(arguments: Mapping[str, object]) -> None:
    text = _required_text(arguments, "evidence_gap_policy")
    if "not_implemented" not in text and "evidence" not in text.casefold():
        _raise_validation_error(
            "evidence_gap_policy must describe evidence handling."
        )


def _validate_severity_change(
    *,
    arguments: Mapping[str, object],
    candidate_evidence: Mapping[str, object],
    new_severity: str,
) -> None:
    severity_mapping = linter_quarantine_json_mapping(
        candidate_evidence.get("severity_mapping")
    )
    observed = str(severity_mapping.get("observed_linter_severity", "") or "")
    proposed = str(severity_mapping.get("proposed_severity", "") or observed)
    old_severity = proposed or observed
    if not old_severity or old_severity not in SEVERITY_RANK:
        return
    if SEVERITY_RANK[new_severity] >= SEVERITY_RANK[old_severity]:
        return
    reason = _required_text(arguments, "severity_change_reason")
    evidence = _required_text(arguments, "severity_change_evidence")
    regression = _required_text(arguments, "severity_regression_test")
    convenience_note = _required_text(arguments, "severity_not_for_convenience")
    if "not for convenience" not in convenience_note.casefold():
        _raise_validation_error(
            "severity_downgrade_requires_not_for_convenience_note"
        )
    if (
        len(reason) < MIN_PROOF_TEXT_CHARS
        or len(evidence) < MIN_PROOF_TEXT_CHARS
    ):
        _raise_validation_error(
            "severity_downgrade_requires_false_positive_evidence"
        )
    if "false positive" not in regression.casefold():
        _raise_validation_error(
            "severity_downgrade_requires_false_positive_evidence"
        )


def _validate_patch_source(patch_code: str) -> None:
    if "git " in patch_code.casefold() or "subprocess" in patch_code.casefold():
        _raise_validation_error("patch_code may not run shell or git commands.")
    if ".env" in patch_code.casefold() or "sqlite3" in patch_code.casefold():
        _raise_validation_error(
            "patch_code may not read secrets or open SQLite directly."
        )


def _validate_edit_severity_downgrade(arguments: Mapping[str, object]) -> None:
    from_severity = _optional_text(arguments, "from_severity")
    to_severity = _optional_text(arguments, "to_severity")
    if not from_severity and not to_severity:
        return
    if from_severity not in SEVERITY_RANK or to_severity not in SEVERITY_RANK:
        _raise_validation_error(
            "from_severity and to_severity must be valid severities."
        )
    if SEVERITY_RANK[to_severity] >= SEVERITY_RANK[from_severity]:
        return
    _ = _proof_text(arguments, "severity_change_reason")
    evidence = _proof_text(arguments, "severity_change_evidence")
    regression = _proof_text(arguments, "severity_regression_test")
    note = _required_text(arguments, "severity_not_for_convenience")
    if (
        "false positive" not in evidence.casefold()
        and "false positive" not in regression.casefold()
    ):
        _raise_validation_error(
            "severity_downgrade_requires_false_positive_evidence"
        )
    if "not for convenience" not in note.casefold():
        _raise_validation_error(
            "severity_downgrade_requires_not_for_convenience_note"
        )


def _invalid_pattern_class(arguments: Mapping[str, object]) -> str:
    pattern_class = _required_text(arguments, "pattern_class")
    if pattern_class not in ALLOWED_INVALID_CLASSES:
        allowed = ", ".join(ALLOWED_INVALID_CLASSES)
        _raise_validation_error(f"pattern_class must be one of: {allowed}.")
    return pattern_class


def _apply_disposition(
    *,
    arguments: Mapping[str, object],
    repo_root: Path,
    tool_name: str,
    worker_id: str,
    candidate_id: str,
    lease_token: str,
    dry_run: bool,
    disposition: str,
    review_state: str,
    sqlite_status: str,
    promotion_state: str,
    payload: JsonObject,
) -> JsonObject:
    _ = _ensure_linter_rule_editor_database(repo_root)
    with closing(connect_catalog_plan_ssot(repo_root=repo_root)) as connection:
        _validate_lease(
            connection=connection,
            candidate_id=candidate_id,
            worker_id=worker_id,
            lease_token=lease_token,
        )
        row = _require_candidate_row(
            connection=connection, candidate_id=candidate_id
        )
        rule_id = str(row[2])
        if dry_run:
            return {
                "status": "dry_run_passed",
                "tool_name": tool_name,
                "candidate_id": candidate_id,
                "rule_id": rule_id,
                "disposition": disposition,
                "would_update_sqlite": True,
                "would_write_snapshots": True,
                "would_commit": True,
                "push_performed": False,
            }
    commit_message = _commit_message(
        arguments, tool_name=tool_name, rule_id=str(row[2])
    )
    _require_clean_git_worktree(repo_root)
    changed_paths = (
        resolve_repo_relative_path(repo_root, DEFAULT_KNOWLEDGE_DB_PATH),
        linter_quarantine_manifest_path(repo_root=repo_root),
        linter_quarantine_coverage_ledger_path(repo_root=repo_root),
    )
    backups = _file_backups(changed_paths)
    now = _utc_now()
    try:
        with closing(
            connect_catalog_plan_ssot(repo_root=repo_root)
        ) as write_connection:
            _ = write_connection.execute("BEGIN IMMEDIATE")
            try:
                write_row = _require_candidate_row(
                    connection=write_connection,
                    candidate_id=candidate_id,
                )
                write_evidence = linter_quarantine_evidence_from_row(write_row)
                _apply_disposition_to_evidence(
                    evidence=write_evidence,
                    payload=payload,
                    worker_id=worker_id,
                    reviewed_at_utc=now,
                    review_state=review_state,
                    promotion_state=promotion_state,
                    commit_hash="pending:mcp-commit",
                )
                update_linter_quarantine_evidence(
                    connection=write_connection,
                    candidate_id=candidate_id,
                    evidence=write_evidence,
                    status=sqlite_status,
                    resolved_at_utc=now,
                )
                _insert_editor_event(
                    connection=write_connection,
                    candidate_id=candidate_id,
                    rule_id=str(write_row[2]),
                    tool_name=tool_name,
                    worker_id=worker_id,
                    disposition=disposition,
                    payload=payload,
                    created_at_utc=now,
                    commit_hash="pending:mcp-commit",
                )
                export = export_linter_quarantine_snapshots(
                    connection=write_connection,
                    repo_root=repo_root,
                    reset_unimplemented=False,
                )
                write_connection.commit()
            except BaseException:
                write_connection.rollback()
                raise
        _git_commit_paths(
            repo_root=repo_root, paths=changed_paths, message=commit_message
        )
        commit_hash = _git_head(repo_root)
        _stamp_commit_hash_and_amend(
            repo_root=repo_root,
            candidate_id=candidate_id,
            commit_hash=commit_hash,
            paths=changed_paths,
        )
        final_hash = _git_head(repo_root)
    except BaseException:
        _restore_file_backups(backups)
        raise
    return {
        "status": "committed",
        "tool_name": tool_name,
        "candidate_id": candidate_id,
        "rule_id": str(row[2]),
        "disposition": disposition,
        "source_of_truth": SQLITE_SOURCE_OF_TRUTH,
        "manifest_path": export["manifest_path"],
        "coverage_path": export["coverage_path"],
        "commit_hash": final_hash,
        "push_performed": False,
        "active_rule_written": False,
        "accepted_rule_code_written": False,
        "live_make_called": False,
        "provider_api_call": False,
    }


def _apply_disposition_to_evidence(
    *,
    evidence: JsonObject,
    payload: JsonObject,
    worker_id: str,
    reviewed_at_utc: str,
    review_state: str,
    promotion_state: str,
    commit_hash: str,
) -> None:
    disposition = str(payload["disposition"])
    integration_review: JsonObject = {
        "schema_version": 1,
        "disposition": disposition,
        "reviewer": worker_id,
        "reviewed_at_utc": reviewed_at_utc,
        "explanation": _disposition_explanation(payload),
        "active_rule_written": False,
        "accepted_rule_code_written": False,
        "source_evidence": payload.get("source_refs", []),
    }
    for key in (
        "canonical_rule_code ",
        "equivalence_proof ",
        "invalid_reason ",
        "pattern_class ",
        "proof_excerpt ",
        "test_or_evidence_ref ",
        "family_id",
    ):
        value = payload.get(key)
        if value is not None:
            integration_review[key] = value
    evidence["integration_review"] = integration_review
    evidence["current_review"] = {
        "review_state": review_state,
        "implementation_status": "implemented"
        if review_state == "implemented"
        else "rejected",
        "implementation_level": disposition
        if review_state == "implemented"
        else None,
        "blocked_reason": "",
        "reviewed_at": reviewed_at_utc,
        "commit_hash": commit_hash,
        "review_path": "",
        "coverage_event": f"mcp_rule_editor_{disposition}",
    }
    evidence["promotion_state"] = promotion_state


def _disposition_explanation(payload: Mapping[str, object]) -> str:
    for key in ("merge_rationale", "invalid_reason", "equivalence_proof"):
        value = str(payload.get(key, "")).strip()
        if value:
            return value
    return str(payload.get("disposition", ""))


def _insert_editor_event(
    *,
    connection: sqlite3.Connection,
    candidate_id: str,
    rule_id: str,
    tool_name: str,
    worker_id: str,
    disposition: str,
    payload: JsonObject,
    created_at_utc: str,
    commit_hash: str,
) -> None:
    event_id = _stable_id(tool_name, candidate_id, disposition, created_at_utc)
    _ = connection.execute(
        """
        INSERT INTO linter_rule_editor_events (
          event_id, candidate_id, rule_id, tool_name, worker_id, disposition,
          payload_json,
          source_ref, created_at_utc, commit_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            candidate_id,
            rule_id,
            tool_name,
            worker_id,
            disposition,
            linter_quarantine_canonical_json_text(payload),
            f"mcp:{tool_name}/{candidate_id}",
            created_at_utc,
            commit_hash,
        ),
    )


def _stable_id(*parts: object) -> str:
    return hashlib.sha256(
        json.dumps(
            parts, ensure_ascii=True, sort_keys=True, default=str
        ).encode("utf-8")
    ).hexdigest()[:24]


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _commit_message(
    arguments: Mapping[str, object],
    *,
    tool_name: str,
    rule_id: str,
) -> str:
    message = _required_text(arguments, "commit_message")
    if len(message) > MAX_COMMIT_MESSAGE_CHARS:
        _raise_validation_error("commit_message is too long.")
    if "\n\n" not in message:
        message = f"{message}\n\n{MCP_CREATED_COMMIT_MARKER}\n MCP-Tool: {tool_name}\n Rule-ID: {rule_id}\n"
    elif MCP_CREATED_COMMIT_MARKER not in message:
        message = f"{message.rstrip()}\n\n{MCP_CREATED_COMMIT_MARKER}\n MCP-Tool: {tool_name}\n Rule-ID: {rule_id}\n"
    return message


def _file_backups(paths: Sequence[Path]) -> dict[Path, bytes | None]:
    return {
        path: path.read_bytes() if path.exists() else None for path in paths
    }


def _restore_file_backups(backups: Mapping[Path, bytes | None]) -> None:
    for path, content in backups.items():
        if content is None:
            if path.exists():
                path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_bytes(content)


def _stamp_commit_hash_and_amend(
    *,
    repo_root: Path,
    candidate_id: str,
    commit_hash: str,
    paths: Sequence[Path],
) -> None:
    now = _utc_now()
    with closing(connect_catalog_plan_ssot(repo_root=repo_root)) as connection:
        _ = connection.execute("BEGIN IMMEDIATE")
        try:
            row = _require_candidate_row(
                connection=connection, candidate_id=candidate_id
            )
            evidence = linter_quarantine_evidence_from_row(row)
            current_review = linter_quarantine_json_mapping(
                evidence.get("current_review")
            )
            current_review["commit_hash"] = commit_hash
            evidence["current_review"] = current_review
            update_linter_quarantine_evidence(
                connection=connection,
                candidate_id=candidate_id,
                evidence=evidence,
                status=str(row[4]),
                resolved_at_utc=now,
            )
            _ = connection.execute(
                """
                UPDATE linter_rule_editor_events
                SET commit_hash = ?
                WHERE candidate_id = ?
                  AND commit_hash = 'pending:mcp-commit'
                """,
                (commit_hash, candidate_id),
            )
            _ = export_linter_quarantine_snapshots(
                connection=connection,
                repo_root=repo_root,
                reset_unimplemented=False,
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    repo_relative_paths = tuple(
        linter_quarantine_repo_relative_path(repo_root=repo_root, path=path)
        for path in paths
    )
    _run_git(repo_root, "add", *repo_relative_paths)
    _run_git(repo_root, "commit", "--amend", "--no-edit")


def _status_counts(rows: Sequence[tuple[object, ...]]) -> dict[str, int]:
    counts = {
        "implemented": 0,
        "canonical_equivalent": 0,
        "duplicate": 0,
        "invalid": 0,
        "not_implemented": 0,
        "blocked": 0,
    }
    for row in rows:
        status = str(row[4])
        evidence = linter_quarantine_evidence_from_row(row)
        integration = linter_quarantine_json_mapping(
            evidence.get("integration_review")
        )
        disposition = str(integration.get("disposition", "")).strip()
        current_review = linter_quarantine_json_mapping(
            evidence.get("current_review")
        )
        implementation_status = str(
            current_review.get("implementation_status", "")
        )
        if disposition == "canonical_equivalent":
            counts["canonical_equivalent"] += 1
        if disposition == "duplicate":
            counts["duplicate"] += 1
        if disposition == "invalid":
            counts["invalid"] += 1
        if status == "blocked" or implementation_status == "blocked":
            counts["blocked"] += 1
        elif status == "implemented" or implementation_status == "implemented":
            counts["implemented"] += 1
        elif status in ACTIONABLE_SOURCE_STATUSES:
            counts["not_implemented"] += 1
    return counts


def _visible_status_counts(
    *,
    current_counts: Mapping[str, int],
    current_row_count: int,
    history_visibility: Mapping[str, object],
) -> dict[str, int]:
    if (
        current_row_count != 0
        or _int_count_value(history_visibility.get("record_count")) == 0
    ):
        return dict(current_counts)
    history_counts = linter_quarantine_json_mapping(
        history_visibility.get("status_counts")
    )
    return {
        "implemented": _int_count_value(history_counts.get("implemented")),
        "canonical_equivalent": _int_count_value(
            history_counts.get("canonical_equivalent")
        ),
        "duplicate": _int_count_value(history_counts.get("duplicate")),
        "invalid": _int_count_value(history_counts.get("invalid")),
        "not_implemented": _int_count_value(
            history_counts.get("not_implemented")
        ),
        "blocked": _int_count_value(history_counts.get("blocked")),
    }


def _historical_observability_payload(
    *,
    current_row_count: int,
    history_visibility: Mapping[str, object],
) -> JsonObject:
    history_status = str(history_visibility.get("status", "missing"))
    history_record_count = _int_count_value(
        history_visibility.get("record_count")
    )
    if history_record_count:
        return {
            "historical_observability_status": "loaded ",
            "historical_counter_semantics": (
                "history_ledger_fallback_when_current_sqlite_empty"
            ),
            "historical_observability_reason": (
                "Historical review coverage is loaded from the coverage ledger "
                "when the "
                "current SQLite quarantine table has no rows."
            ),
        }
    if current_row_count == 0:
        return {
            "historical_observability_status": "empty_history_not_loaded ",
            "historical_counter_semantics": (
                "current_sqlite_only_no_historical_truth"
            ),
            "historical_zero_is_truth": False,
            "historical_zero_reason": (
                "Historical counters are zero because the review coverage "
                "ledger is missing; "
                "zero means no historical ledger was loaded, not that "
                "historical review work "
                "proved there were zero records."
            ),
            "historical_observability_reason": (
                "The historical DB not loaded or reset state is explicit: "
                "current counters "
                "are zero because neither current SQLite rows nor a historical "
                "review ledger "
                f"are available (history_status={history_status})."
            ),
        }
    return {
        "historical_observability_status": "current_sqlite_rows_active ",
        "historical_counter_semantics": "current_sqlite_rows_override_history",
        "historical_observability_reason": (
            "Current SQLite quarantine rows are present, so visible counters "
            "describe the "
            "active local queue rather than historical ledger totals."
        ),
    }


def _history_visibility_payload(*, repo_root: Path) -> JsonObject:
    coverage_path = linter_quarantine_coverage_ledger_path(repo_root=repo_root)
    if not coverage_path.is_file():
        return {
            "status": "missing ",
            "source": "review_coverage_ledger",
            "path": safe_linter_quarantine_source_reference(
                linter_quarantine_repo_relative_path(
                    repo_root=repo_root, path=coverage_path
                )
            ),
            "record_count": 0,
            "status_counts": _zero_history_status_counts(),
        }
    raw_payload = cast(
        "object", json.loads(coverage_path.read_text(encoding="utf-8"))
    )
    if not isinstance(raw_payload, Mapping):
        _raise_type_error("review-coverage.json must contain a JSON object.")
    payload = linter_quarantine_json_mapping(
        cast("Mapping[object, object]", raw_payload)
    )
    implementation_counts = linter_quarantine_json_mapping(
        payload.get("implementation_status_counts")
    )
    integration_counts = linter_quarantine_json_mapping(
        payload.get("integration_status_counts")
    )
    status_counts = {
        "implemented": _int_count_value(
            implementation_counts.get("implemented")
        ),
        "canonical_equivalent": _int_count_value(
            integration_counts.get("canonical_equivalent")
        ),
        "duplicate": _int_count_value(integration_counts.get("duplicate")),
        "invalid": _int_count_value(integration_counts.get("invalid")),
        "not_implemented": _int_count_value(
            implementation_counts.get("not_attempted")
        )
        + _int_count_value(implementation_counts.get("not_implemented")),
        "blocked": _int_count_value(implementation_counts.get("blocked")),
    }
    return {
        "status": "loaded ",
        "source": "review_coverage_ledger",
        "path": safe_linter_quarantine_source_reference(
            linter_quarantine_repo_relative_path(
                repo_root=repo_root, path=coverage_path
            )
        ),
        "ledger_version": str(payload.get("ledger_version", "")),
        "generated_from": str(payload.get("generated_from", "")),
        "record_count": _int_count_value(payload.get("record_count")),
        "implementation_status_counts": implementation_counts,
        "integration_status_counts": integration_counts,
        "status_counts": status_counts,
    }


def _zero_history_status_counts() -> JsonObject:
    return {
        "implemented": 0,
        "canonical_equivalent": 0,
        "duplicate": 0,
        "invalid": 0,
        "not_implemented": 0,
        "blocked": 0,
    }


def _int_count_value(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


def _duplicate_ids(rows: Sequence[tuple[object, ...]]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for row in rows:
        candidate_id = _candidate_id_from_row(row)
        if candidate_id in seen:
            duplicates.add(candidate_id)
        seen.add(candidate_id)
    return sorted(duplicates)


def _duplicate_source_headings(rows: Sequence[tuple[object, ...]]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for row in rows:
        evidence = linter_quarantine_evidence_from_row(row)
        key = "|".join(
            (
                str(evidence.get("source_file") or row[1]),
                str(evidence.get("original_heading", "")),
            )
        )
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    return sorted(duplicates)


def _lease_count(connection: sqlite3.Connection, *, status: str) -> int:
    value = connection.execute(
        "SELECT COUNT(*) FROM linter_rule_editor_leases WHERE status = ?",
        (status,),
    ).fetchone()
    if value is None:
        return 0
    return int(value[0])


def _require_mcp_created_commit(
    *, repo_root: Path, commit_hash: str, rule_id: str
) -> None:
    result = _run_git_capture(
        repo_root, "show", "-s", "--format=%B", commit_hash
    )
    message = result.stdout
    if MCP_CREATED_COMMIT_MARKER not in message or rule_id not in message:
        _raise_validation_error(
            "rollback_requires_mcp_created_linter_rule_commit"
        )


def _require_clean_git_worktree(repo_root: Path) -> None:
    result = _run_git_capture(repo_root, "status", "--short")
    if result.stdout.strip():
        _raise_validation_error(
            "git_worktree_must_be_clean_before_mcp_linter_rule_commit"
        )


def _git_commit_paths(
    *, repo_root: Path, paths: Sequence[Path], message: str
) -> None:
    relative_paths = tuple(
        linter_quarantine_repo_relative_path(repo_root=repo_root, path=path)
        for path in paths
    )
    _run_git(repo_root, "add", *relative_paths)
    _run_git(repo_root, "diff", "--cached", "--check")
    _run_git(repo_root, "commit", "-m", message)


def _git_head(repo_root: Path) -> str:
    return _run_git_capture(repo_root, "rev-parse", "HEAD").stdout.strip()


def _run_git(repo_root: Path, *args: str) -> None:
    _ = subprocess.run(
        [GIT_EXECUTABLE, *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
    )


def _run_git_capture(
    repo_root: Path, *args: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [GIT_EXECUTABLE, *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
    )
