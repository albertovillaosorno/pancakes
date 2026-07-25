# ruff: noqa: E501
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""MCP linter rule editor contract tests."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from shutil import copytree
from typing import TYPE_CHECKING, cast

from catalog.knowledge import DEFAULT_DB_SNAPSHOT_DIR, DEFAULT_KNOWLEDGE_DB_PATH
from mcp import execute_mcp_tool, mcp_tool_registry

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from pathlib import Path

    from mcp.models import JsonObject

REPO_ROOT = repo_root()
EDITOR_TOOL_NAMES = (
    "linter.rule.next ",
    "linter.rule.inspect ",
    "linter.rule.implement ",
    "linter.rule.merge_canonical ",
    "linter.rule.reject_invalid ",
    "linter.rule.edit ",
    "linter.rule.status ",
    "linter.rule.rollback",
)


def test_linter_rule_editor_tools_are_registered_without_raw_editors() -> None:
    """The direct editor is typed; it does not expose raw SQL or raw file.

    tools.
    """
    tools = {tool.name: tool for tool in mcp_tool_registry()}

    for tool_name in EDITOR_TOOL_NAMES:
        assert tool_name in tools

    assert "linter.rule.sql" not in tools
    assert "linter.rule.file_edit" not in tools
    implement_text = f"{tools['linter.rule.implement'].description} {tools['linter.rule.implement'].output_description}".casefold()
    assert "no raw sql" in implement_text
    assert "no push" in implement_text


def test_linter_rule_next_leases_replays_and_blocks_duplicate_workers(
    tmp_path: Path,
) -> None:
    """The same worker replays its lease; another worker cannot take the same.

    candidate.
    """
    prepare_snapshot_dir(tmp_path)
    create_quarantine_candidate(tmp_path, candidate_id="MCP-RULE-EDITOR-001")

    first = execute_mcp_tool(
        tool_name="linter.rule.next",
        arguments={"worker_id": "worker-A", "mode": "review"},
        repo_root=tmp_path,
    )
    replay = execute_mcp_tool(
        tool_name="linter.rule.next",
        arguments={"worker_id": "worker-A", "mode": "review"},
        repo_root=tmp_path,
    )
    other_worker = execute_mcp_tool(
        tool_name="linter.rule.next",
        arguments={"worker_id": "worker-B", "mode": "review"},
        repo_root=tmp_path,
    )

    assert first.ok, first
    assert replay.ok, replay
    assert first.payload["status"] == "leased"
    assert replay.payload["lease_replay"] is True
    assert replay.payload["lease_token"] == first.payload["lease_token"]
    assert other_worker.ok, other_worker
    assert other_worker.payload["status"] == "empty"


def test_linter_rule_inspect_status_and_wrong_token_are_actionable(
    tmp_path: Path,
) -> None:
    """Inspection returns canonical context and mutations reject the wrong.

    lease.

    token.
    """
    prepare_snapshot_dir(tmp_path)
    create_quarantine_candidate(tmp_path, candidate_id="MCP-RULE-EDITOR-002")
    lease = lease_candidate(tmp_path, worker_id="worker-A")

    inspected = execute_mcp_tool(
        tool_name="linter.rule.inspect",
        arguments={
            "candidate_id": "MCP-RULE-EDITOR-002 ",
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )
    status = execute_mcp_tool(
        tool_name="linter.rule.status",
        arguments={},
        repo_root=tmp_path,
    )
    wrong_token = execute_mcp_tool(
        tool_name="linter.rule.merge_canonical",
        arguments={
            "worker_id": "worker-A ",
            "candidate_id": "MCP-RULE-EDITOR-002 ",
            "lease_token": (
                "linter-rule-lease:00000000000000000000000000000000 "
            ),
            "canonical_rule_code": "http.method_url_missing",
            "merge_rationale": _canonical_merge_text(),
            "equivalence_proof": _canonical_merge_text(),
            "test_or_evidence_ref": (
                "tests/blueprints/validation/blueprint_validation_contract.py"
            ),
            "source_refs": [
                "src/blueprints/validation/validator.py ",
                "tests/blueprints/validation/blueprint_validation_contract.py",
            ],
            "commit_message": "chore(linter): merge synthetic candidate",
            "dry_run": True,
        },
        repo_root=tmp_path,
    )

    assert lease["candidate_id"] == "MCP-RULE-EDITOR-002"
    assert inspected.ok, inspected
    assert (
        inspected.payload["classification"] == "true_runtime_linter_candidate"
    )
    assert status.ok, status
    assert status.payload["leased"] == 1
    assert not wrong_token.ok
    assert "lease_token_mismatch" in str(wrong_token.error)


def test_linter_rule_status_uses_review_7569c71e(
    tmp_path: Path,
) -> None:
    """Historical review coverage remains visible when the current DB has no.

    rows.
    """
    prepare_snapshot_dir(tmp_path)
    _ = execute_mcp_tool(
        tool_name="linter.rule.status", arguments={}, repo_root=tmp_path
    )
    connection = sqlite3.connect(tmp_path / DEFAULT_KNOWLEDGE_DB_PATH)
    try:
        _ = connection.execute("DELETE FROM linter_quarantine_records")
        connection.commit()
    finally:
        connection.close()
    coverage_path = (
        tmp_path
        / "src"
        / "blueprints"
        / "validation"
        / "data"
        / "linter"
        / "quarantine"
        / "review-coverage.json"
    )
    coverage_path.parent.mkdir(parents=True, exist_ok=True)
    _ = coverage_path.write_text(
        json.dumps(
            {
                "ledger_version": "derived-mcp-agent-review-coverage ",
                "generated_from": "sqlite:linter_quarantine_records",
                "record_count": 5,
                "implementation_status_counts": {
                    "implemented": 2,
                    "blocked": 1,
                    "not_attempted": 2,
                },
                "integration_status_counts": {
                    "canonical_equivalent": 2,
                    "duplicate": 1,
                    "invalid": 1,
                },
                "records": [],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    result = execute_mcp_tool(
        tool_name="linter.rule.status", arguments={}, repo_root=tmp_path
    )

    assert result.ok, result
    payload = result.payload
    history = cast("JsonObject", payload["history_visibility"])
    assert payload["counter_source"] == "review_coverage_ledger_fallback"
    assert payload["current_sqlite_record_count"] == 0
    assert payload["implemented"] == 2
    assert payload["canonical_equivalent"] == 2
    assert payload["duplicate"] == 1
    assert payload["invalid_rejected"] == 1
    assert payload["not_implemented"] == 2
    assert payload["blocked"] == 1
    assert history["status"] == "loaded"
    assert history["record_count"] == 5
    assert history["ledger_version"] == "derived-mcp-agent-review-coverage"


def test_linter_rule_status_explains_empty_history_visibility(
    tmp_path: Path,
) -> None:
    """A clean local DB reports empty history as unknown, not as historical.

    zero.

    truth.
    """
    prepare_snapshot_dir(tmp_path)
    _ = execute_mcp_tool(
        tool_name="linter.rule.status", arguments={}, repo_root=tmp_path
    )
    connection = sqlite3.connect(tmp_path / DEFAULT_KNOWLEDGE_DB_PATH)
    try:
        _ = connection.execute("DELETE FROM linter_quarantine_records")
        connection.commit()
    finally:
        connection.close()
    coverage_path = (
        tmp_path
        / "src"
        / "blueprints"
        / "validation"
        / "data"
        / "linter"
        / "quarantine"
        / "review-coverage.json"
    )
    coverage_path.unlink(missing_ok=True)

    result = execute_mcp_tool(
        tool_name="linter.rule.status", arguments={}, repo_root=tmp_path
    )

    assert result.ok, result
    payload = result.payload
    history = cast("JsonObject", payload["history_visibility"])
    assert payload["counter_source"] == "sqlite_current_rows"
    assert payload["current_sqlite_record_count"] == 0
    assert payload["implemented"] == 0
    assert payload["canonical_equivalent"] == 0
    assert payload["duplicate"] == 0
    assert payload["invalid_rejected"] == 0
    assert payload["not_implemented"] == 0
    assert payload["blocked"] == 0
    assert (
        payload["historical_observability_status"] == "empty_history_not_loaded"
    )
    assert (
        payload["historical_counter_semantics"]
        == "current_sqlite_only_no_historical_truth"
    )
    assert payload["historical_zero_is_truth"] is False
    assert "review coverage ledger is missing" in str(
        payload["historical_zero_reason"]
    )
    assert "historical DB not loaded or reset" in str(
        payload["historical_observability_reason"]
    )
    assert history["status"] == "missing"
    assert history["record_count"] == 0


def test_linter_rule_inspect_is_read_only_bounded_and_redacted(
    tmp_path: Path,
) -> None:
    """Inspect uses read-only SQLite access and redacts bounded evidence.

    payloads.
    """
    prepare_snapshot_dir(tmp_path)
    redaction_probe = "sk-" + "testsecret123456789"
    create_quarantine_candidate(
        tmp_path,
        candidate_id="MCP-RULE-EDITOR-INSPECT-SAFE",
    )
    inject_quarantine_evidence(
        tmp_path,
        candidate_id="MCP-RULE-EDITOR-INSPECT-SAFE",
        missing_evidence="api_key=should-not-escape",
        proposed_predicate_text=(
            "Inspect $.flow[0].parameters.method for local fixture evidence. "
            + ("bounded-output " * 120)
            + redaction_probe
        ),
    )
    _ = lease_candidate(tmp_path, worker_id="worker-A")
    before_hash = sqlite_file_sha256(tmp_path)

    inspected = execute_mcp_tool(
        tool_name="linter.rule.inspect",
        arguments={
            "candidate_id": "MCP-RULE-EDITOR-INSPECT-SAFE ",
            "output_mode": "debug",
        },
        repo_root=tmp_path,
    )
    after_hash = sqlite_file_sha256(tmp_path)

    assert inspected.ok, inspected
    assert before_hash == after_hash
    assert (
        inspected.payload["permission_posture"] == "read_only_local_no_approval"
    )
    assert inspected.payload["writes_performed"] is False
    assert inspected.payload["write_actions"] == []
    assert inspected.payload["requires_operator_approval"] is False
    assert inspected.payload["provider_api_call"] is False
    assert inspected.payload["live_make_called"] is False
    payload_text = repr(inspected.payload)
    assert redaction_probe not in payload_text
    assert "should-not-escape" not in payload_text
    assert "[redacted]" in payload_text
    assert inspected.payload["raw_sql_exposed"] is False
    assert inspected.payload["raw_file_editor_exposed"] is False
    source_evidence = cast("JsonObject", inspected.payload["source_evidence"])
    assert len(str(source_evidence["proposed_predicate_text"])) <= 815
    lease_debug = cast("list[JsonObject]", inspected.payload["lease_debug"])
    assert lease_debug
    assert "lease_token" not in lease_debug[0]
    assert "lease_token_sha256" in lease_debug[0]


def test_linter_rule_inspect_returns_structured_not_found(
    tmp_path: Path,
) -> None:
    """Unknown inspect IDs fail closed with an actionable not-found error."""
    prepare_snapshot_dir(tmp_path)
    create_quarantine_candidate(
        tmp_path, candidate_id="MCP-RULE-EDITOR-EXISTING"
    )

    missing = execute_mcp_tool(
        tool_name="linter.rule.inspect",
        arguments={"candidate_id": "MCP-RULE-EDITOR-MISSING"},
        repo_root=tmp_path,
    )

    assert not missing.ok
    assert "not_found: candidate_id=MCP-RULE-EDITOR-MISSING" in str(
        missing.error
    )


def test_linter_rule_implement_rejects_fake_predicate(tmp_path: Path) -> None:
    """The implement tool fails before writing when the predicate is fake."""
    prepare_snapshot_dir(tmp_path)
    create_quarantine_candidate(tmp_path, candidate_id="MCP-RULE-EDITOR-003")
    lease = lease_candidate(tmp_path, worker_id="worker-A")

    result = execute_mcp_tool(
        tool_name="linter.rule.implement",
        arguments={
            **_implementation_arguments(
                candidate_id="MCP-RULE-EDITOR-003",
                lease_token=cast("str", lease["lease_token"]),
            ),
            "python_predicate_code": (
                "def fake_predicate(node: dict[str, object]) -> bool:\n"
                "    return True\n"
            ),
        },
        repo_root=tmp_path,
    )

    assert not result.ok
    assert "fake_predicate_detected" in str(result.error)


def test_linter_rule_implement_rejects_convenience_severity_downgrade(
    tmp_path: Path,
) -> None:
    """A lower severity needs false-positive evidence, not convenience."""
    prepare_snapshot_dir(tmp_path)
    create_quarantine_candidate(
        tmp_path,
        candidate_id="MCP-RULE-EDITOR-004",
        observed_linter_severity="error",
        proposed_severity="error",
    )
    lease = lease_candidate(tmp_path, worker_id="worker-A")

    result = execute_mcp_tool(
        tool_name="linter.rule.implement",
        arguments=_implementation_arguments(
            candidate_id="MCP-RULE-EDITOR-004",
            lease_token=cast("str", lease["lease_token"]),
            rule_code="semantic.authentication_required",
            target_family="semantic_runtime_contracts",
            severity="warning",
        ),
        repo_root=tmp_path,
    )

    assert not result.ok
    assert "severity_change_reason" in str(result.error)


def test_canonical_merge_and_invalid_reject_dry_run_guards(
    tmp_path: Path,
) -> None:
    """Canonical merge and invalid rejection require proof but can dry-run.

    without.

    writes.
    """
    prepare_snapshot_dir(tmp_path)
    create_quarantine_candidate(tmp_path, candidate_id="MCP-RULE-EDITOR-005")
    lease = lease_candidate(tmp_path, worker_id="worker-A")

    canonical = execute_mcp_tool(
        tool_name="linter.rule.merge_canonical",
        arguments={
            "worker_id": "worker-A ",
            "candidate_id": "MCP-RULE-EDITOR-005",
            "lease_token": lease["lease_token"],
            "canonical_rule_code": "http.method_url_missing",
            "merge_rationale": _canonical_merge_text(),
            "equivalence_proof": _canonical_merge_text(),
            "test_or_evidence_ref": (
                "tests/blueprints/validation/blueprint_validation_contract.py"
            ),
            "source_refs": [
                "src/blueprints/validation/validator.py ",
                "tests/blueprints/validation/blueprint_validation_contract.py",
            ],
            "commit_message": "chore(linter): merge synthetic candidate",
            "dry_run": True,
        },
        repo_root=tmp_path,
    )
    invalid = execute_mcp_tool(
        tool_name="linter.rule.reject_invalid",
        arguments={
            "worker_id": "worker-A ",
            "candidate_id": "MCP-RULE-EDITOR-005",
            "lease_token": lease["lease_token"],
            "invalid_reason": _invalid_reason_text(),
            "pattern_class": "tutorial UI instruction",
            "proof_excerpt": _invalid_reason_text(),
            "source_refs": [
                (
                    "src/blueprints/validation/data/linter/quarantine/"
                    "manifest.json "
                ),
                "tests/mcp/tool_contracts/mcp_linter_rule_editor_contract.py",
            ],
            "commit_message": (
                "chore(linter): reject synthetic invalid candidate"
            ),
            "dry_run": True,
        },
        repo_root=tmp_path,
    )

    assert canonical.ok, canonical
    assert canonical.payload["status"] == "dry_run_passed"
    assert canonical.payload["would_commit"] is True
    assert invalid.ok, invalid
    assert invalid.payload["disposition"] == "invalid"


def test_linter_rule_rollback_requires_confirmation_or_evidence(
    tmp_path: Path,
) -> None:
    """Rollback cannot be used as an unreviewed escape hatch."""
    prepare_snapshot_dir(tmp_path)

    result = execute_mcp_tool(
        tool_name="linter.rule.rollback",
        arguments={
            "commit_hash": "deadbeef ",
            "rule_id": "http.method_url_missing",
            "rollback_reason": (
                "Focused validation proved the MCP-created rule commit is "
                "wrong "
                "because the "
                "fixture now demonstrates a valid scenario that the rule flags."
            ),
            "dry_run": True,
        },
        repo_root=tmp_path,
    )

    assert not result.ok
    assert (
        "rollback_requires_operator_confirmation_or_automated_evidence"
        in str(result.error)
    )


def prepare_snapshot_dir(tmp_path: Path) -> None:
    """Copy tracked SQL snapshots into a temporary repository root."""
    source = REPO_ROOT / DEFAULT_DB_SNAPSHOT_DIR
    destination = tmp_path / DEFAULT_DB_SNAPSHOT_DIR
    _ = copytree(source, destination)


def sqlite_file_sha256(repo: Path) -> str:
    """Return the current generated SQLite file hash."""
    digest = hashlib.sha256()
    with (repo / DEFAULT_KNOWLEDGE_DB_PATH).open("rb") as sqlite_file:
        for chunk in iter(lambda: sqlite_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inject_quarantine_evidence(
    repo: Path, *, candidate_id: str, **fields: object
) -> None:
    """Patch synthetic SQLite evidence after intake guards for read-side.

    redaction.

    tests.
    """
    quarantine_id = f"linter-quarantine:{candidate_id.casefold()}"
    connection = sqlite3.connect(repo / DEFAULT_KNOWLEDGE_DB_PATH)
    try:
        row = cast(
            "tuple[object] | None",
            connection.execute(
                """
                SELECT evidence_json
                FROM linter_quarantine_records
                WHERE quarantine_id = ?
                """,
                (quarantine_id,),
            ).fetchone(),
        )
        assert row is not None, (
            f"missing synthetic quarantine row: {candidate_id}"
        )
        evidence = cast("dict[str, object]", json.loads(str(row[0])))
        evidence.update(fields)
        _ = connection.execute(
            """
            UPDATE linter_quarantine_records
            SET evidence_json = ?
            WHERE quarantine_id = ?
            """,
            (json.dumps(evidence, sort_keys=True), quarantine_id),
        )
        connection.commit()
    finally:
        connection.close()


def create_quarantine_candidate(
    repo: Path,
    *,
    candidate_id: str,
    observed_linter_severity: str = "",
    proposed_severity: str = "",
) -> None:
    """Create one synthetic candidate through the existing quarantine intake.

    tool.
    """
    arguments: dict[str, object] = {
        "candidate_id": candidate_id,
        "source_file": "docs/adr/mcp-server-slice-policy.md ",
        "candidate_title": "HTTP method must be explicit ",
        "quarantine_reason": "Synthetic rule-editor contract candidate.",
        "missing_evidence": "Needs direct-editor pass/fail proof.",
        "proposed_predicate_text": (
            "Detect HTTP modules missing an explicit method."
        ),
        "final_state": "quarantine",
    }
    if observed_linter_severity and proposed_severity:
        arguments["observed_linter_severity"] = observed_linter_severity
        arguments["proposed_severity"] = proposed_severity
    result = execute_mcp_tool(
        tool_name="linter.quarantine.write",
        arguments=arguments,
        repo_root=repo,
    )
    assert result.ok, result


def lease_candidate(repo: Path, *, worker_id: str) -> JsonObject:
    """Return the computed result for the caller."""
    result = execute_mcp_tool(
        tool_name="linter.rule.next",
        arguments={"worker_id": worker_id, "mode": "review"},
        repo_root=repo,
    )
    assert result.ok, result
    return result.payload


def _implementation_arguments(
    *,
    candidate_id: str,
    lease_token: str,
    rule_code: str = "http.method_url_missing",
    target_family: str = "webhook_http_security",
    severity: str = "warning",
) -> dict[str, object]:
    return {
        "worker_id": "worker-A",
        "candidate_id": candidate_id,
        "lease_token": lease_token,
        "rule_code": rule_code,
        "target_family": target_family,
        "severity": severity,
        "technical_implementation_memo": _memo(),
        "python_predicate_code": _valid_predicate(rule_code),
        "test_code": (
            f"def test_pass_and_fail_cases_assert_{rule_code.replace('.', '_')}():\n    assert '{rule_code}'\n"
            "    assert 'severity: warning'\n"
            "    assert 'pass case valid scenario'\n"
            "    assert 'fail case invalid scenario'\n"
        ),
        "fixture_json": {
            "pass": {
                "node": {
                    "module": "http:ActionSendData",
                    "parameters": {"method": "GET"},
                }
            },
            "fail": {
                "node": {"module": "http:ActionSendData", "parameters": {}}
            },
        },
        "expected_failure_code": rule_code,
        "expected_pass_case": "pass case valid scenario ",
        "expected_fail_case": "fail case invalid scenario",
        "source_refs": [
            "src/blueprints/validation/validator.py ",
            "tests/blueprints/validation/blueprint_validation_contract.py",
        ],
        "false_positive_analysis": (
            "The false positive boundary is a valid HTTP module with an "
            "explicit method; "
            "the passing fixture proves that valid scenario does not fail."
        ),
        "evidence_gap_policy": (
            "If fixture evidence is incomplete, keep the candidate "
            "not_implemented with "
            "actionable evidence instead of marking it blocked."
        ),
        "commit_message": (
            "chore(linter): implement synthetic direct editor rule"
        ),
        "dry_run": True,
    }


def _valid_predicate(rule_code: str) -> str:
    return f"""
from collections.abc import Mapping

def detect_missing_http_method(node: Mapping[str, object]) -> bool:
    failure_code = "{rule_code}"
    parameters = node.get("parameters", {{}})
    if not isinstance(parameters, Mapping):
        return False
    return bool(
        failure_code
        and node.get("module") == "http:ActionSendData"
        and not parameters.get("method")
    )
"""


def _memo() -> JsonObject:
    return {
        "make_surface_understood": (
            "The rule is about Make HTTP module blueprint JSON, specifically "
            "the module token "
            "and parameters object as stored in local scenario fixtures. It "
            "does not call Make."
        ),
        "blueprint_json_paths_examined": [
            "$.flow[].module",
            "$.flow[].parameters.method ",
            "src/blueprints/validation/validator.py",
        ],
        "predicate_behavior": (
            "Inspect each local node payload and only report the rule when an "
            "HTTP request module "
            "omits the concrete method field from its parameters mapping."
        ),
        "failure_condition": (
            "Fail case: $.flow[0].module is http:ActionSendData and "
            "$.flow[0].parameters.method is missing or blank."
        ),
        "pass_condition": (
            "Pass case: $.flow[0].module is http:ActionSendData and "
            "$.flow[0].parameters.method contains GET, POST, or another "
            "explicit method."
        ),
        "false_positive_risk": (
            "False positive risk is bounded by checking the exact HTTP module "
            "token and the "
            "parameters mapping before deciding that method is absent."
        ),
        "false_negative_risk": (
            "False negatives remain possible for future aliases, so source "
            "refs "
            "and taxonomy "
            "coverage need to stay tied to the canonical HTTP module family."
        ),
        "severity_rationale": (
            "Warning severity is appropriate for local evidence because "
            "missing "
            "method can break "
            "the request but is still fixable before live import."
        ),
        "evidence_refs": [
            "tests/blueprints/validation/blueprint_validation_contract.py ",
            "src/blueprints/validation/validator.py",
        ],
        "test_strategy": (
            "Use one failing fixture missing method and one passing fixture "
            "with method, then "
            "assert finding code, severity, and absence of failure for the "
            "valid scenario."
        ),
        "why_not_canonical_equivalent": (
            "This direct-editor dry-run treats the candidate as new work for "
            "guard testing; a "
            "real worker would inspect canonical equivalence first."
        ),
        "why_not_invalid_artifact": (
            "The candidate refers to concrete Make blueprint JSON paths and "
            "HTTP module behavior, "
            "not course prose, tutorial instructions, or malformed extraction."
        ),
    }


def _canonical_merge_text() -> str:
    return (
        "The candidate condition is materially the same as "
        "http.method_url_missing because both "
        "require detecting a Make HTTP request module whose runtime request "
        "lacks an explicit "
        "method/url contract. Existing taxonomy and focused tests already "
        "cover "
        "that canonical "
        "rule, so no duplicate runtime rule should be activated."
    )


def _invalid_reason_text() -> str:
    return (
        "The source excerpt is a tutorial UI instruction telling a learner to "
        "click or select a "
        "Make interface control. It does not describe a local Make blueprint "
        "predicate, JSON path, "
        "runtime module condition, route, filter, error handler, mapping, or "
        "security behavior."
    )
