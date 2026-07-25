# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001055#repo.mcp.required-tool-surface
# - 001079#repo.make-linter.rule-intake-manual-gate
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Typed contracts for MCP linter rule editor tools.

Boundary contract:
- Owns: stable tool names, statuses, disposition classes, and memo policy.
- Must not: dispatch tools, write files, mutate SQLite, or inspect source code.
- Allows: shared constants and deterministic validation policy summaries.
- Split when: another editor family needs a separate status model.
- Merge when: linter editor execution and registry contracts become inseparable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from mcp.models import JsonObject

LINTER_RULE_NEXT_TOOL: Final = "linter.rule.next"
LINTER_RULE_INSPECT_TOOL: Final = "linter.rule.inspect"
LINTER_RULE_IMPLEMENT_TOOL: Final = "linter.rule.implement"
LINTER_RULE_MERGE_CANONICAL_TOOL: Final = "linter.rule.merge_canonical"
LINTER_RULE_REJECT_INVALID_TOOL: Final = "linter.rule.reject_invalid"
LINTER_RULE_EDIT_TOOL: Final = "linter.rule.edit"
LINTER_RULE_STATUS_TOOL: Final = "linter.rule.status"
LINTER_RULE_ROLLBACK_TOOL: Final = "linter.rule.rollback"

LINTER_RULE_EDITOR_TOOL_NAMES: Final[tuple[str, ...]] = (
    LINTER_RULE_NEXT_TOOL,
    LINTER_RULE_INSPECT_TOOL,
    LINTER_RULE_IMPLEMENT_TOOL,
    LINTER_RULE_MERGE_CANONICAL_TOOL,
    LINTER_RULE_REJECT_INVALID_TOOL,
    LINTER_RULE_EDIT_TOOL,
    LINTER_RULE_STATUS_TOOL,
    LINTER_RULE_ROLLBACK_TOOL,
)
LEASE_MODES: Final[frozenset[str]] = frozenset(
    ("implementable", "canonical_merge", "invalid_disposition", "review")
)
DEFAULT_LEASE_MODE: Final = "review"
ALLOWED_DISPOSITIONS: Final[tuple[str, ...]] = (
    "implemented",
    "canonical_equivalent",
    "duplicate",
    "invalid",
    "not_implemented",
)
NORMAL_TARGET_STATUSES: Final[tuple[str, ...]] = (
    "implemented",
    "canonical_equivalent",
    "duplicate",
    "invalid",
    "not_implemented",
)
ACTIONABLE_SOURCE_STATUSES: Final[frozenset[str]] = frozenset(
    (
        "accepted_pending_implementation",
        "blocked",
        "not_implemented",
        "quarantined",
    )
)
EXIT_STATUSES: Final[frozenset[str]] = frozenset(("implemented", "rejected"))
ALLOWED_INVALID_CLASSES: Final[tuple[str, ...]] = (
    "course quiz answer key",
    "tutorial UI instruction",
    "marketing/training prose",
    "duplicate heading fragment",
    "generic API definition prose",
    "non-blueprint policy text",
    "malformed extraction",
    "proven impossible to interpret as local Make blueprint predicate",
)
MEMO_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "make_surface_understood",
    "blueprint_json_paths_examined",
    "predicate_behavior",
    "failure_condition",
    "pass_condition",
    "false_positive_risk",
    "false_negative_risk",
    "severity_rationale",
    "evidence_refs",
    "test_strategy",
    "why_not_canonical_equivalent",
    "why_not_invalid_artifact",
)
MIN_MEMO_CHARACTERS: Final = 1_200
MIN_MEMO_POPULATED_FIELDS: Final = 8
MIN_MEMO_REFERENCE_COUNT: Final = 2
SEVERITY_RANK: Final[dict[str, int]] = {
    "info": 1,
    "advisory_info": 2,
    "warning": 3,
    "error": 4,
    "critical": 5,
}
VALID_SEVERITIES: Final[frozenset[str]] = frozenset(SEVERITY_RANK)
EDITOR_LEASE_TABLE_NAME: Final = "linter_rule_editor_leases"
EDITOR_EVENT_TABLE_NAME: Final = "linter_rule_editor_events"
DEFAULT_LEASE_SECONDS: Final = 7_200


def implementation_contract_payload() -> JsonObject:
    """Return the worker-facing linter editor implementation contract."""
    return {
        "no_raw_sql_tool": True,
        "no_raw_file_editor_tool": True,
        "dry_run_supported": True,
        "runtime_activation_requires_registered_family_writer": True,
        "no_fake_predicates": True,
        "required_memo_fields": list(MEMO_REQUIRED_FIELDS),
        "minimum_memo_characters": MIN_MEMO_CHARACTERS,
        "minimum_populated_memo_fields": MIN_MEMO_POPULATED_FIELDS,
        "minimum_source_or_json_path_refs": MIN_MEMO_REFERENCE_COUNT,
        "required_tests": [
            "failing fixture",
            "passing fixture",
            "finding code assertion",
            "severity assertion",
            "valid scenario does not fail",
        ],
        "validation_order": [
            "lease",
            "memo",
            "AST guard",
            "severity guard",
            "focused tests",
            "snapshot invariant",
            "git hygiene",
            "commit",
        ],
    }


def required_evidence_fields_payload() -> JsonObject:
    """Return the evidence fields required before any rule disposition."""
    return {
        "implementation": [
            "technical_implementation_memo",
            "python_predicate_code",
            "test_code",
            "fixture_json",
            "expected_failure_code",
            "expected_pass_case",
            "expected_fail_case",
            "source_refs",
            "false_positive_analysis",
            "evidence_gap_policy",
        ],
        "canonical_merge": [
            "canonical_rule_code",
            "merge_rationale",
            "source_refs",
            "equivalence_proof",
            "test_or_evidence_ref",
        ],
        "invalid_rejection": [
            "invalid_reason",
            "pattern_class",
            "source_refs",
            "proof_excerpt",
        ],
        "rollback": [
            "commit_hash",
            "rule_id",
            "rollback_reason",
            "operator_confirmation_or_automated_evidence",
        ],
    }


def validation_commands_payload() -> list[str]:
    """Return command-layer validation expected for linter editor work."""
    return [
        "pancakes.lint",
        "pancakes.typecheck",
        "focused MCP/linter pytest",
        "pancakes.validate",
        "git diff --check",
    ]
