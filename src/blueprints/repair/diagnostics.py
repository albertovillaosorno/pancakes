# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001046#repo.blueprint-validation.validator-policy
# - 001049#repo.blueprint-repair.diagnostics-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Convert validation findings into scoped repair diagnostics.

Boundary contract:
- Owns: deterministic repair candidates derived from blueprints.validation
findings.
- Must not: mutate blueprints, call live services, or validate full blueprints.
- Allows: typed diagnostic records, severity mapping, and client-safe guidance.
- Split when: a diagnostic family needs independent policy or candidate rules.
- Merge when: another diagnostics file derives the same candidates identically.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING, Final, Literal, NamedTuple

from blueprints.validation.findings import ROUTES_ON_NON_ROUTER_CODE

if TYPE_CHECKING:
    from blueprints.validation import (
        BlueprintValidationFinding,
        BlueprintValidationReport,
    )

type RepairSeverity = Literal[
    "hard_failure", "warning", "optimization", "explanation"
]
type RepairSourcePath = tuple[str | int, ...]
type RepairCategory = Literal[
    "unsupported_module_discovery ",
    "brittle_api_dependency ",
    "missing_error_strategy ",
    "data_validation_risk ",
    "webhook_response_risk ",
    "operation_limit_risk ",
    "incomplete_execution_risk ",
    "repeated_error_risk ",
    "ai_tool_contract_risk ",
    "general_validation_guidance",
]

NO_MUTATION_ROLLBACK: Final[tuple[str, ...]] = (
    "No blueprint mutation is performed by diagnostics.",
    "Discard the candidate by leaving the source blueprint unchanged.",
)
ERROR_HANDLER_NESTED_UNSUPPORTED_CODE: Final = (
    "importability.error_handler.nested_unsupported"
)
ERROR_HANDLER_CHILD_INVALID_CODE: Final = "ast.error_handler_child_invalid"
ERROR_HANDLER_EMPTY_CODE: Final = "ast.error_handler_empty"
ERROR_HANDLER_CHILD_PATTERN: Final = re.compile(
    r"\b(?P<key>onerror|on_error)\[(?P<index>\d+)\]"
)
ERROR_HANDLER_EMPTY_PATTERN: Final = re.compile(
    r"\b(?P<key>onerror|on_error)\b"
)
CODE_CATEGORIES: Final[dict[str, RepairCategory]] = {
    "module.unresolved": "unsupported_module_discovery ",
    "module.catalog_record_missing": "unsupported_module_discovery ",
    "deprecated_module": "brittle_api_dependency ",
    "error_route.missing": "missing_error_strategy",
    ERROR_HANDLER_CHILD_INVALID_CODE: "incomplete_execution_risk",
    ERROR_HANDLER_EMPTY_CODE: "incomplete_execution_risk",
    ERROR_HANDLER_NESTED_UNSUPPORTED_CODE: "incomplete_execution_risk",
    "webhook.response_missing": "webhook_response_risk ",
    "semantic.operation_volume_review": "operation_limit_risk ",
    "route.empty_flow": "incomplete_execution_risk",
    ROUTES_ON_NON_ROUTER_CODE: "incomplete_execution_risk",
    "schedule.missing": "incomplete_execution_risk ",
    "schedule.empty": "incomplete_execution_risk ",
    "ai_agent.tools_missing": "ai_tool_contract_risk ",
    "ai_agent.provider_missing": "ai_tool_contract_risk ",
    "ai_agent.instructions_inputs_mixed": "ai_tool_contract_risk ",
    "ai_agent.scope_too_broad": "ai_tool_contract_risk ",
    "ai_agent.fallback_missing": "ai_tool_contract_risk ",
    "ai_agent.test_cases_missing": "ai_tool_contract_risk ",
    "ai_agent.knowledge_attachment_review": "ai_tool_contract_risk ",
    "ai_agent.tool_description_unclear": "ai_tool_contract_risk ",
    "ai_agent.tool_contract_missing": "ai_tool_contract_risk ",
    "ai_agent.tool_not_on_demand": "ai_tool_contract_risk ",
    "ai_agent.tool_output_missing": "ai_tool_contract_risk ",
    "importability.placeholder_unresolved": "data_validation_risk ",
    "importability.router_topology": "incomplete_execution_risk",
}


class RepairCandidate(NamedTuple):
    """One scoped repair candidate derived from blueprints.validation.

    evidence.
    """

    candidate_id: str
    severity: RepairSeverity
    category: RepairCategory
    source_finding_code: str
    node_id: str | None
    source_path: RepairSourcePath
    client_explanation: str
    internal_diagnostic: str
    preconditions: tuple[str, ...]
    rollback_notes: tuple[str, ...]
    applies_automatically: bool = False


class RepairDiagnosticsReport(NamedTuple):
    """Deterministic repair diagnostics derived from a validation report."""

    candidates: tuple[RepairCandidate, ...]

    def candidates_for_severity(
        self, severity: RepairSeverity
    ) -> tuple[RepairCandidate, ...]:
        """Return repair candidates for one severity."""
        return tuple(
            candidate
            for candidate in self.candidates
            if candidate.severity == severity
        )

    def categories(self) -> tuple[RepairCategory, ...]:
        """Return repair categories in deterministic candidate order."""
        return tuple(candidate.category for candidate in self.candidates)


def propose_repair_candidates(
    report: BlueprintValidationReport,
    *,
    max_candidates: int | None = None,
) -> RepairDiagnosticsReport:
    """Convert validation findings into deterministic repair candidates.

    Returns:
        The result produced by convert validation findings into deterministic
        repair candidates.

    Raises:
        ValueError: If an input value violates the documented contract.
    """
    candidates = [
        _candidate_for_finding(finding) for finding in report.findings
    ]
    candidates.extend(_repeated_error_candidates(report.findings))
    ordered_candidates = tuple(
        sorted(candidates, key=lambda candidate: candidate.candidate_id)
    )
    if max_candidates is not None:
        if max_candidates < 1:
            message = "Repair candidate limit must be positive."
            raise ValueError(message)
        ordered_candidates = ordered_candidates[:max_candidates]
    return RepairDiagnosticsReport(candidates=ordered_candidates)


def _candidate_for_finding(
    finding: BlueprintValidationFinding,
) -> RepairCandidate:
    """Return one repair candidate for a validation finding."""
    category = _category_for_code(finding.code)
    node_id = finding.node_id or "root"
    return RepairCandidate(
        candidate_id=f"repair:{finding.severity}:{finding.code}:{node_id}",
        severity=_repair_severity(finding.severity),
        category=category,
        source_finding_code=finding.code,
        node_id=finding.node_id,
        source_path=_source_path_for_finding(finding),
        client_explanation=_client_explanation_for_finding(finding, category),
        internal_diagnostic=finding.internal_message,
        preconditions=_preconditions_for_finding(finding, category),
        rollback_notes=NO_MUTATION_ROLLBACK,
    )


def _repeated_error_candidates(
    findings: tuple[BlueprintValidationFinding, ...],
) -> tuple[RepairCandidate, ...]:
    """Return candidates for repeated blocking finding patterns."""
    blocking_codes = [
        finding.code for finding in findings if finding.severity == "error"
    ]
    repeated_codes = sorted(
        code for code, count in Counter(blocking_codes).items() if count > 1
    )
    return tuple(_repeated_error_candidate(code) for code in repeated_codes)


def _repeated_error_candidate(code: str) -> RepairCandidate:
    """Return a repeated-error repair candidate."""
    return RepairCandidate(
        candidate_id=f"repair:hard_failure:repeated:{code}",
        severity="hard_failure",
        category="repeated_error_risk",
        source_finding_code=code,
        node_id=None,
        source_path=(),
        client_explanation=(
            "Several validation failures share the same pattern and should be "
            "fixed together."
        ),
        internal_diagnostic=f"Repeated blocking validation code: {code}.",
        preconditions=(
            "Group matching validation findings by code.",
            (
                "Review one representative fix before applying the same "
                "pattern "
                "elsewhere."
            ),
        ),
        rollback_notes=NO_MUTATION_ROLLBACK,
    )


def _repair_severity(severity: str) -> RepairSeverity:
    """Map validation severity to repair severity.

    Returns:
        The result produced by map validation severity to repair severity.
    """
    if severity == "error":
        return "hard_failure"
    if severity == "warning":
        return "warning"
    if severity == "optimization":
        return "optimization"
    return "explanation"


def _category_for_code(code: str) -> RepairCategory:
    """Map validation finding codes to repair categories.

    Returns:
        The result produced by map validation finding codes to repair
        categories.
    """
    if code.startswith("mapping."):
        return "data_validation_risk"
    return CODE_CATEGORIES.get(code, "general_validation_guidance")


def _source_path_for_finding(
    finding: BlueprintValidationFinding,
) -> RepairSourcePath:
    """Return the computed result for the caller."""
    if finding.code == ERROR_HANDLER_CHILD_INVALID_CODE:
        match = ERROR_HANDLER_CHILD_PATTERN.search(finding.internal_message)
        if match is None:
            return finding.source_path
        index = max(int(match.group("index")) - 1, 0)
        return (*finding.source_path, match.group("key"), index)
    if finding.code == ERROR_HANDLER_EMPTY_CODE:
        match = ERROR_HANDLER_EMPTY_PATTERN.search(finding.internal_message)
        if match is None:
            return finding.source_path
        return (*finding.source_path, match.group("key"))
    return finding.source_path


def _client_explanation_for_finding(
    finding: BlueprintValidationFinding,
    category: RepairCategory,
) -> str:
    """Return client-safe explanation text for one validation finding."""
    if finding.code == ROUTES_ON_NON_ROUTER_CODE:
        return (
            "Insert a BasicRouter node before the route branches and move "
            "those "
            ""
            "branches under that router."
        )
    if finding.code == ERROR_HANDLER_NESTED_UNSUPPORTED_CODE:
        return (
            "Flatten the nested error-handler path into a direct handler flow"
            "before handoff."
        )
    if finding.code == ERROR_HANDLER_CHILD_INVALID_CODE:
        return (
            "Replace the malformed error-handler entry with a handler module or"
            "flow wrapper."
        )
    if finding.code == ERROR_HANDLER_EMPTY_CODE:
        return "Remove the empty error-handler path or add a handler module."
    return _client_explanation(category)


def _client_explanation(category: RepairCategory) -> str:
    """Return client-safe explanation text for a repair category."""
    explanations: dict[RepairCategory, str] = {
        "unsupported_module_discovery": (
            "Add the missing Make app or module specification before creating "
            "an "
            "importable blueprint."
        ),
        "brittle_api_dependency": (
            "Replace or review the deprecated module before relying on this "
            "workflow."
        ),
        "missing_error_strategy": (
            "Add an error-handling path so failed module runs have a defined "
            "outcome."
        ),
        "data_validation_risk": (
            "Correct the mapped value or expression before rendering an "
            "importable blueprint."
        ),
        "webhook_response_risk": (
            "Define the webhook response behavior before handing off this "
            "workflow."
        ),
        "operation_limit_risk": (
            "Review branch and bundle volume before relying on this "
            "workflow at "
            "scale."
        ),
        "incomplete_execution_risk": (
            "Complete the missing flow or trigger detail before depending on "
            "execution."
        ),
        "repeated_error_risk": (
            "Fix repeated validation failures as one scoped cleanup pass."
        ),
        "ai_tool_contract_risk": (
            "Define the AI tool contract before enabling the agent step."
        ),
        "general_validation_guidance": (
            "Review the validation finding and decide whether a scoped change "
            "is needed."
        ),
    }
    return explanations[category]


def _preconditions_for_finding(
    finding: BlueprintValidationFinding,
    category: RepairCategory,
) -> tuple[str, ...]:
    """Return scoped preconditions for one validation finding."""
    if finding.code == ROUTES_ON_NON_ROUTER_CODE:
        return (
            "The misplaced routes are still attached to the source node.",
            (
                "A new builtin:BasicRouter node id can be allocated without "
                "colliding with existing node ids."
            ),
            "Branch filters and flow payloads are preserved under the router.",
        )
    if finding.code == ERROR_HANDLER_NESTED_UNSUPPORTED_CODE:
        return (
            (
                "The nested error-handler payload is still present at the "
                "reported "
                "source path."
            ),
            "The original onerror or on_error alias can be preserved.",
            (
                "Unknown fields from the nested handler payload remain "
                "available "
                "for review."
            ),
        )
    if finding.code == ERROR_HANDLER_CHILD_INVALID_CODE:
        return (
            (
                "The malformed error-handler child is still present at the "
                "reported "
                "source path."
            ),
            "The original onerror or on_error alias can be preserved.",
            (
                "Unknown fields from the malformed child remain available for "
                "review."
            ),
        )
    if finding.code == ERROR_HANDLER_EMPTY_CODE:
        return (
            (
                "The empty error-handler container is still present at the "
                "reported "
                "source path."
            ),
            "The original onerror or on_error alias can be preserved.",
        )
    return _preconditions(category)


def _preconditions(category: RepairCategory) -> tuple[str, ...]:
    """Return scoped preconditions for a repair category."""
    preconditions: dict[RepairCategory, tuple[str, ...]] = {
        "unsupported_module_discovery": (
            "Validated Make catalog record is available.",
            "Operator confirms the requested app or module is in scope.",
        ),
        "brittle_api_dependency": (
            "Replacement module or accepted deprecation waiver is documented.",
        ),
        "missing_error_strategy": (
            "Failure outcome is known: ignore, retry, compensate, or stop.",
        ),
        "data_validation_risk": (
            "Expected input and output data shapes are known.",
        ),
        "webhook_response_risk": (
            "Webhook caller response expectations are known.",
        ),
        "operation_limit_risk": (
            "Expected bundle count and branch volume are known.",
        ),
        "incomplete_execution_risk": (
            "Missing route, trigger, or flow behavior is specified.",
        ),
        "repeated_error_risk": (
            "Representative repair is validated before repeating it.",
        ),
        "ai_tool_contract_risk": (
            "Allowed tools, inputs, and outputs are specified.",
        ),
        "general_validation_guidance": (
            "Validation finding is reviewed by the operator.",
        ),
    }
    return preconditions[category]
