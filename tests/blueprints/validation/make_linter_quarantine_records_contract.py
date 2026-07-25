# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contract tests for Make linter quarantine records.

Boundary contract:
- Owns: validation that tracked quarantine files are SQLite-derived snapshots
  or legacy review evidence, not runtime authority.
- Must not: activate linter behavior, inspect completed TODO archives, or read
  customer blueprints.
- Allows: static reads from the quarantine manifest, review coverage, and
  legacy quarantine Markdown records.
- Split when: quarantine promotion becomes an executable workflow.
- Merge when: linter candidate intake persistence owns the same snapshot checks.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

REPO_ROOT = repo_root()
LINTER_DATA_ROOT = (
    REPO_ROOT / "src" / "blueprints" / "validation" / "data" / "linter"
)
QUARANTINE_ROOT = LINTER_DATA_ROOT / "quarantine"
QUARANTINE_MANIFEST_PATH = QUARANTINE_ROOT / "manifest.json"
REVIEW_COVERAGE_PATH = QUARANTINE_ROOT / "review-coverage.json"
MCP_REVIEW_DIR = QUARANTINE_ROOT / "mcp-review-decisions"
QUARANTINE_FINAL_STATES = frozenset(
    ("kept_quarantined", "promoted", "rewritten", "aliased", "rejected")
)

type JsonObject = dict[str, object]


def test_quarantine_manifest_is_sqlite_derived_snapshot() -> None:
    """Every manifest row is a SQLite-derived quarantine snapshot."""
    manifest = load_quarantine_manifest()
    coverage = load_json_object(REVIEW_COVERAGE_PATH)
    manifest_records = object_rows(manifest, "records")
    coverage_records = object_rows(coverage, "records")

    assert (
        str_member(manifest, "source_of_truth")
        == "sqlite:linter_quarantine_records"
    )
    assert bool_member(manifest, "sqlite_ssot") is True
    assert (
        str_member(manifest, "generated_from")
        == "sqlite:linter_quarantine_records"
    )
    assert int_member(manifest, "total_quarantined") == len(manifest_records), (
        f"Quarantine manifest count drifted from records: {manifest}"
    )
    assert int_member(coverage, "record_count") == len(coverage_records), (
        f"Review coverage count drifted from records: {coverage}"
    )
    assert int_member(coverage, "manifest_record_count") == len(
        manifest_records
    ), f"Review coverage count drifted from manifest: {coverage}"
    assert str_member(manifest, "runtime_activation").startswith("none;"), (
        f"Quarantine manifest must not activate runtime behavior: {manifest}"
    )
    diagnostics = [
        str(record.get("candidate_id", ""))
        for record in manifest_records
        if record.get("source_of_truth") != "sqlite:linter_quarantine_records"
        or not str(record.get("sqlite_quarantine_id", "")).startswith(
            "linter-quarantine:"
        )
    ]
    assert not diagnostics, (
        f"Manifest rows are not SQLite-derived: {diagnostics}"
    )


def test_quarantine_records_preserve_required_review_fields() -> None:
    """Quarantine records preserve the fields needed for later one-by-one.

    review.
    """
    required_sections = (
        "## Original Source File",
        "## Original Candidate ID",
        "## Original Candidate Heading Or Title",
        "## Quarantine Reason",
        "## Missing Evidence",
        "## Missing Deterministic Predicate",
        "## False-Positive Risk",
        "## Blocked Severity Posture",
        "## Blocked Profile Gates",
        "## Related Aliases Or Duplicate Active Rules",
        "## Required Fixtures If Promoted Later",
        "## ADR Impact If Promoted Later",
        "## Client-Safe Wording If Promoted Later",
        "## Last Review Date",
        "## Final State",
    )
    diagnostics: list[str] = []

    for record in object_rows(load_quarantine_manifest(), "records"):
        relative_path = str_member(record, "record_path")
        if "#" in relative_path:
            diagnostics.extend(manifest_locator_diagnostics(record))
            continue

        record_path = REPO_ROOT / relative_path
        if not record_path.is_file():
            diagnostics.append(f"{relative_path}: missing file")
            continue
        if not record_path.is_relative_to(QUARANTINE_ROOT):
            diagnostics.append(f"{relative_path}: outside quarantine root")
            continue

        text = record_path.read_text(encoding="utf-8")
        final_state = str_member(record, "final_state")
        required_fragments = (
            str_member(record, "candidate_id"),
            str_member(record, "source_file"),
            str_member(record, "original_heading"),
            str_member(record, "quarantine_reason"),
            "`kept_quarantined`",
            "ADR 001079",
            "Do not expose internal candidate IDs",
        )
        missing_sections = tuple(
            section for section in required_sections if section not in text
        )
        missing_fragments = tuple(
            fragment for fragment in required_fragments if fragment not in text
        )
        if final_state not in QUARANTINE_FINAL_STATES:
            diagnostics.append(
                f"{relative_path}: invalid final state {final_state!r}"
            )
        if missing_sections:
            diagnostics.append(
                f"{relative_path}: missing sections {missing_sections}"
            )
        if missing_fragments:
            diagnostics.append(
                f"{relative_path}: missing fragments {missing_fragments}"
            )

    assert not diagnostics, f"Quarantine records are incomplete: {diagnostics}"


def manifest_locator_diagnostics(record: JsonObject) -> tuple[str, ...]:
    """Return diagnostics for one SQLite-derived manifest-backed record."""
    relative_path = str_member(record, "record_path")
    candidate_id = str_member(record, "candidate_id")
    diagnostics: list[str] = []
    manifest_relative_path = QUARANTINE_MANIFEST_PATH.relative_to(
        REPO_ROOT
    ).as_posix()
    if relative_path != f"{manifest_relative_path}#candidate_id={candidate_id}":
        diagnostics.append(f"{relative_path}: invalid manifest locator")
    if str_member(record, "final_state") not in QUARANTINE_FINAL_STATES:
        diagnostics.append(f"{relative_path}: invalid final state")
    if (
        str_member(record, "source_of_truth")
        != "sqlite:linter_quarantine_records"
    ):
        diagnostics.append(f"{relative_path}: missing SQLite source of truth")
    if not str_member(record, "sqlite_quarantine_id").startswith(
        "linter-quarantine:"
    ):
        diagnostics.append(f"{relative_path}: missing SQLite quarantine id")
    required_fields = (
        "source_file ",
        "original_heading ",
        "quarantine_reason ",
        "missing_evidence ",
        "proposed_predicate_text ",
        "owner_todo ",
        "origin ",
        "promotion_state",
    )
    missing_fields = tuple(
        field
        for field in required_fields
        if not isinstance(record.get(field), str) or field not in record
    )
    if missing_fields:
        diagnostics.append(
            f"{relative_path}: missing structured fields {missing_fields}"
        )
    return tuple(diagnostics)


def test_mcp_review_decisions_preserve_not_a8e98557() -> None:
    """Legacy blocked MCP review files must be reclassified without losing.

    evidence.
    """
    coverage_records = {
        str_member(record, "candidate_id"): record
        for record in object_rows(
            load_json_object(REVIEW_COVERAGE_PATH), "records"
        )
    }
    diagnostics = [
        diagnostic
        for review_path in sorted(MCP_REVIEW_DIR.glob("*.json"))
        for diagnostic in review_decision_diagnostics(
            review_path, coverage_records
        )
    ]

    assert not diagnostics, (
        f"MCP review decisions lost blocked-state evidence: {diagnostics}"
    )


def review_decision_diagnostics(
    review_path: Path,
    coverage_records: Mapping[str, JsonObject],
) -> tuple[str, ...]:
    """Return diagnostics for one MCP review decision file."""
    payload = load_json_object(review_path)
    candidate_id = str_member(payload, "candidate_id")
    review_state = str_member(payload, "review_state")
    if review_state == "blocked":
        return (f"{review_path.name}: stale blocked review state",)
    if review_state not in {"implemented", "not_implemented", "rejected"}:
        return (
            f"{review_path.name}: unsupported review state {review_state!r}",
        )

    coverage = coverage_records.get(candidate_id)
    if coverage is None:
        return (f"{review_path.name}: missing review coverage row",)
    if review_state == "rejected":
        return rejected_review_diagnostics(review_path.name, payload, coverage)
    if review_state == "implemented":
        return ()
    return not_implemented_review_decision_diagnostics(
        review_path.name, payload, coverage
    )


def rejected_review_diagnostics(
    review_name: str,
    payload: JsonObject,
    coverage: JsonObject,
) -> tuple[str, ...]:
    """Return diagnostics for one rejected review decision."""
    diagnostics: list[str] = []
    if coverage.get("integration_status") not in {"duplicate", "invalid"}:
        diagnostics.append(
            f"{review_name}: rejected without duplicate/invalid proof"
        )
    if payload.get("leaves_quarantine") is not True:
        diagnostics.append(
            f"{review_name}: rejected review must leave quarantine"
        )
    if payload.get("active_rule_written") is not False:
        diagnostics.append(
            f"{review_name}: rejected review wrote an active rule"
        )
    return tuple(diagnostics)


def not_implemented_review_decision_diagnostics(
    review_name: str,
    payload: JsonObject,
    coverage: JsonObject,
) -> tuple[str, ...]:
    """Return diagnostics for one not-implemented review decision."""
    state_evidence = payload.get("state_evidence")
    diagnostics: list[str] = []
    if coverage.get("integration_status") != "not_implemented":
        diagnostics.append(
            f"{review_name}: coverage is not valid/actionable not_implemented"
        )
    if not isinstance(state_evidence, dict):
        diagnostics.append(f"{review_name}: state_evidence must be an object")
        return tuple(diagnostics)
    evidence = cast("JsonObject", state_evidence)
    diagnostics.extend(
        not_implemented_review_evidence_diagnostics(
            review_name, payload, evidence
        )
    )
    return tuple(diagnostics)


def not_implemented_review_evidence_diagnostics(
    review_name: str,
    payload: JsonObject,
    evidence: JsonObject,
) -> tuple[str, ...]:
    """Return evidence diagnostics for a not-implemented review decision."""
    diagnostics: list[str] = []
    if evidence.get("previous_review_state") != "blocked":
        diagnostics.append(
            f"{review_name}: previous blocked state was not preserved"
        )
    if "valid/actionable" not in str(evidence.get("actionability_summary", "")):
        diagnostics.append(f"{review_name}: missing valid/actionable summary")
    if (
        "fixture"
        not in str(evidence.get("promotion_requirement", "")).casefold()
    ):
        diagnostics.append(
            f"{review_name}: missing fixture promotion requirement"
        )
    if payload.get("leaves_quarantine") is not False:
        diagnostics.append(
            f"{review_name}: not_implemented must stay quarantined"
        )
    if payload.get("allowed_exit_reason"):
        diagnostics.append(
            f"{review_name}: not_implemented must not set an exit reason"
        )
    if payload.get("active_rule_written") is not False:
        diagnostics.append(
            f"{review_name}: reclassification wrote an active rule"
        )
    if payload.get("accepted_rule_code_written") is not False:
        diagnostics.append(
            f"{review_name}: reclassification accepted a rule code"
        )
    if payload.get("live_services_called") is not False:
        diagnostics.append(
            f"{review_name}: reclassification called live services"
        )
    return tuple(diagnostics)


def load_quarantine_manifest() -> JsonObject:
    """Load the linter quarantine manifest.

    Returns:
        The parsed quarantine manifest.
    """
    return load_json_object(QUARANTINE_MANIFEST_PATH)


def load_json_object(path: Path) -> JsonObject:
    """Load one JSON object payload from a repository path.

    Returns:
        The parsed JSON object.
    """
    payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(payload, dict), f"JSON payload must be an object: {path}"
    return cast("JsonObject", payload)


def bool_member(payload: JsonObject, key: str) -> bool:
    """Return one boolean member."""
    value = payload.get(key)
    assert isinstance(value, bool), (
        f"JSON member {key!r} must be a boolean: {payload}"
    )
    return value


def object_rows(payload: JsonObject, key: str) -> tuple[JsonObject, ...]:
    """Return one list-of-objects member."""
    value = payload.get(key)
    assert isinstance(value, list), (
        f"JSON member {key!r} must be a list: {payload}"
    )
    rows: list[JsonObject] = []
    for item in cast("list[object]", value):
        assert isinstance(item, dict), (
            f"JSON member {key!r} must contain objects: {payload}"
        )
        rows.append(cast("JsonObject", item))
    return tuple(rows)


def int_member(payload: JsonObject, key: str) -> int:
    """Return one integer member."""
    value = payload.get(key)
    assert isinstance(value, int), (
        f"JSON member {key!r} must be an integer: {payload}"
    )
    assert not isinstance(value, bool), (
        f"JSON member {key!r} must be an integer: {payload}"
    )
    return value


def str_member(payload: JsonObject, key: str) -> str:
    """Return one string member."""
    value = payload.get(key)
    assert isinstance(value, str), (
        f"JSON member {key!r} must be a string: {payload}"
    )
    return value
