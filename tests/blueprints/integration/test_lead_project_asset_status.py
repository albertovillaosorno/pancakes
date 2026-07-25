# ruff: noqa: E501
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Lead project fixture importability regression tests.

Boundary contract:
- Owns: portfolio honesty checks for the tracked lead-routing project fixture.
- Must not: mutate project JSON, call live Make services, or require
credentials.
- Allows: offline AST parsing, catalog-backed validation, and strict handoff
gating.
- Split when: project-loop MCP payload shape needs its own integration coverage.
- Merge when: another integration test pins this exact project asset status.
"""

from __future__ import annotations

import json
from functools import cache
from typing import TYPE_CHECKING, Final, NamedTuple, cast

from blueprints.ast import parse_make_ast_json_text
from blueprints.ast.artifacts import classify_blueprint_artifact_phase
from blueprints.validation.generation_gate import guard_blueprint_for_handoff
from catalog.json_payloads import normalize_json_object
from tests.catalog.test_module_token_resolution import native_module_snapshot

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping

    from blueprints.ast.models import JsonObject
    from blueprints.validation.generation_gate import BlueprintHandoffGateReport
    from blueprints.validation.models import BlueprintValidationFinding


type AstPath = tuple[str | int, ...]

REPO_ROOT = repo_root()
LEAD_PROJECT_SCENARIO = (
    REPO_ROOT
    / "tests"
    / "blueprints"
    / "fixtures"
    / "portfolio_projects"
    / "lead-routing-data-store-mvp"
    / "scenario.json"
)
KNOWN_BLOCKER_CODES: Final[frozenset[str]] = frozenset(
    (
        "route.routes_on_non_router",
        "filter.reference_not_upstream",
        "importability.placeholder_registry_incomplete",
        "importability.placeholder_unregistered",
    )
)
EXPECTED_RUNTIME_PLACEHOLDERS: Final[tuple[str, ...]] = (
    "runtime.webhook.lead_intake_hook",
    "runtime.datastore.qualified_leads",
    "runtime.datastore.incomplete_leads",
)
FORBIDDEN_LIVE_OR_SECRET_MARKERS: Final[tuple[str, ...]] = (
    "http://",
    "https://",
    "api_key",
    "apikey",
    "account_id",
    "client_secret",
    "bearer ",
)


class LeadProjectStatus(NamedTuple):
    """Cached offline status for the tracked lead-routing project asset."""

    payload: JsonObject
    scenario_text: str
    strict_gate: BlueprintHandoffGateReport


def test_lead_project_asset_has_honest_importability_status() -> None:
    """The portfolio asset stays source-draft-classified while strict handoff.

    is.

    blocked.
    """
    status = _lead_project_status()

    artifact_phase = classify_blueprint_artifact_phase(status.payload)

    assert artifact_phase == "source_draft", (
        f"Lead project asset phase drifted: {artifact_phase!r}"
    )
    assert status.strict_gate.mode == "strict", (
        f"Lead project asset did not use the strict handoff gate: {status}"
    )
    assert status.strict_gate.status == "blocked", (
        f"Lead project asset must not be represented as importable: {status}"
    )
    assert not (status.strict_gate.importable), (
        f"Lead project asset must not be represented as importable: {status}"
    )
    assert not (status.strict_gate.generation_gate.can_render), (
        f"Strict gate allowed rendering for a blocked project asset: {status}"
    )
    assert not (
        "Strict handoff is blocked" not in status.strict_gate.operator_message
    ), f"Strict gate did not report an honest blocker message: {status}"


def test_lead_project_asset_known_blockers_are_stable_until_fixed() -> None:
    """Known local blockers are pinned without asserting the full finding.

    list.
    """
    error_findings = _lead_project_status().strict_gate.validation_report.findings_for_severity(
        "error"
    )
    error_codes = frozenset(finding.code for finding in error_findings)
    missing_codes = KNOWN_BLOCKER_CODES - error_codes

    assert not (missing_codes), (
        f"Lead project asset known blockers drifted: {sorted(missing_codes)}"
    )

    assert "ast.note_invalid" not in error_codes, (
        f"Lead project asset note normalization regressed: {error_findings}"
    )
    _require_error_at(
        error_findings,
        code="route.routes_on_non_router",
        source_path=("flow", 0, "routes"),
    )
    _require_paths(
        error_findings,
        code="filter.reference_not_upstream",
        expected_paths=frozenset(
            (
                ("flow", 0, "routes", 0, "filter", "conditions", "expression"),
                ("flow", 0, "routes", 1, "filter", "conditions", "expression"),
            )
        ),
    )
    _require_paths(
        error_findings,
        code="importability.placeholder_registry_incomplete",
        expected_paths=frozenset(
            (
                ("metadata", "placeholder_registry", 0),
                ("metadata", "placeholder_registry", 1),
                ("metadata", "placeholder_registry", 2),
            )
        ),
    )
    _require_paths(
        error_findings,
        code="importability.placeholder_unregistered",
        expected_paths=frozenset(
            (
                ("flow", 0, "parameters", "hook"),
                ("flow", 0, "routes", 0, "flow", 0, "parameters", "datastore"),
                ("flow", 0, "routes", 1, "flow", 0, "parameters", "datastore"),
            )
        ),
    )


def test_lead_project_asset_requires_no_credentials_for_validation() -> None:
    """Offline validation uses placeholders and local catalog facts only."""
    status = _lead_project_status()
    lowered = status.scenario_text.casefold()
    forbidden_hits = tuple(
        marker
        for marker in FORBIDDEN_LIVE_OR_SECRET_MARKERS
        if marker in lowered
    )

    assert not (forbidden_hits), (
        f"Lead project asset contains live or credential-like markers: "
        f"{forbidden_hits}"
    )
    for placeholder in EXPECTED_RUNTIME_PLACEHOLDERS:
        assert not (f"{{{{{placeholder}}}}}" not in status.scenario_text), (
            f"Lead project asset lost runtime placeholder {placeholder!r}."
        )
    assert (
        "module.unresolved" not in status.strict_gate.validation_report.codes()
    ), f"Lead project asset should stay catalog-backed: {status.strict_gate}"
    assert not (
        any(
            blocker.code == "generation.unsupported_module"
            for blocker in status.strict_gate.generation_gate.blockers
        )
    ), (
        f"Lead project asset validation required unsupported live modules: "
        f"{status}"
    )


@cache
def _lead_project_status() -> LeadProjectStatus:
    """Return cached local validation state for the tracked project asset."""
    scenario_text = LEAD_PROJECT_SCENARIO.read_text(encoding="utf-8")
    payload = _json_object_from_text(scenario_text)
    root = parse_make_ast_json_text(scenario_text)
    strict_gate = guard_blueprint_for_handoff(
        root=root,
        catalog=native_module_snapshot(),
    )
    return LeadProjectStatus(
        payload=payload,
        scenario_text=scenario_text,
        strict_gate=strict_gate,
    )


def _json_object_from_text(source_text: str) -> JsonObject:
    """Return a normalized JSON object from scenario text."""
    payload = cast("object", json.loads(source_text))
    assert isinstance(payload, dict), (
        f"{LEAD_PROJECT_SCENARIO} must contain a JSON object."
    )
    return normalize_json_object(cast("Mapping[str, object]", payload))


def _require_error_at(
    findings: tuple[BlueprintValidationFinding, ...],
    *,
    code: str,
    source_path: AstPath,
) -> None:
    """Fail unless one error finding appears at the expected path."""
    _require_paths(
        findings, code=code, expected_paths=frozenset((source_path,))
    )


def _require_paths(
    findings: tuple[BlueprintValidationFinding, ...],
    *,
    code: str,
    expected_paths: frozenset[AstPath],
) -> None:
    """Fail unless all expected paths are present for one finding code."""
    actual_paths = frozenset(
        finding.source_path for finding in findings if finding.code == code
    )
    missing_paths = expected_paths - actual_paths
    if missing_paths:
        missing = sorted(missing_paths)
        actual = sorted(actual_paths)
        message = (
            f"Lead project asset missing {code!r} paths: missing={missing},"
            f"actual={actual}"
        )
        assert not (missing_paths), message
