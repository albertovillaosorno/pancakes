# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001044#repo.make-ast.contract-policy
# - 001045#repo.make-ast.module-resolution-policy
# - 001046#repo.blueprint-validation.validator-policy
# - 001066#repo.make-linter.secondary-linter-advisory-gate
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Typed finding model for Make blueprint validation.

Boundary contract:
- Owns: immutable validation finding, report, and generation gate records.
- Must not: compute validation findings, inspect AST nodes,
  or render blueprints.
- Allows: typed status literals and read-only convenience accessors.
- Split when: model families gain independent lifecycle or dependency needs.
- Merge when: another model file duplicates these validation records exactly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Literal, NamedTuple

if TYPE_CHECKING:
    from catalog.knowledge import MakeSecondaryLinterReport

type BlueprintFindingSeverity = Literal[
    "error", "warning", "optimization", "explanation"
]
type BlueprintDeltaCategory = Literal[
    "semantic",
    "designer-layout",
    "metadata",
    "placeholder",
    "connection",
    "module-version",
    "route/filter",
    "unknown",
]
type BlueprintGenerationGateStatus = Literal["allowed", "blocked"]

FINDING_SEVERITIES: Final[frozenset[str]] = frozenset(
    ("error", "warning", "optimization", "explanation")
)
BLOCKING_FINDING_SEVERITIES: Final[frozenset[str]] = frozenset(("error",))
ADVISORY_FINDING_SEVERITIES: Final[frozenset[str]] = (
    FINDING_SEVERITIES - BLOCKING_FINDING_SEVERITIES
)
BLUEPRINT_DELTA_CATEGORIES: Final[frozenset[str]] = frozenset(
    (
        "semantic",
        "designer-layout",
        "metadata",
        "placeholder",
        "connection",
        "module-version",
        "route/filter",
        "unknown",
    )
)


class BlueprintValidationFinding(NamedTuple):
    """One validation finding with client-safe and internal diagnostics."""

    finding_id: str
    severity: BlueprintFindingSeverity
    code: str
    node_id: str | None
    client_message: str
    internal_message: str
    catalog_module_id: str | None = None
    source_path: tuple[str | int, ...] = ()


class BlueprintValidationReport(NamedTuple):
    """Validation report for one parsed Make blueprint AST."""

    catalog_fingerprint: str
    findings: tuple[BlueprintValidationFinding, ...]

    @property
    def has_errors(self) -> bool:
        """Return whether validation produced blocking errors."""
        return bool(self.blocking_findings())

    def findings_for_severity(
        self,
        severity: BlueprintFindingSeverity,
    ) -> tuple[BlueprintValidationFinding, ...]:
        """Return findings for one severity in original validation order."""
        return tuple(
            finding for finding in self.findings if finding.severity == severity
        )

    def blocking_findings(self) -> tuple[BlueprintValidationFinding, ...]:
        """Return findings that block strict render or importability claims."""
        return tuple(
            finding
            for finding in self.findings
            if finding.severity in BLOCKING_FINDING_SEVERITIES
        )

    def advisory_findings(self) -> tuple[BlueprintValidationFinding, ...]:
        """Return nonblocking findings in original validation order."""
        return tuple(
            finding
            for finding in self.findings
            if finding.severity in ADVISORY_FINDING_SEVERITIES
        )

    def codes(self) -> tuple[str, ...]:
        """Return finding codes in original validation order."""
        return tuple(finding.code for finding in self.findings)


class RuntimePlaceholderRegistryEntry(NamedTuple):
    """One typed project runtime placeholder registry entry."""

    placeholder: str
    kind: str
    target_path: str
    required: bool
    expected_type: str
    handoff_instructions: str
    source_path: tuple[str | int, ...]


class BlueprintGenerationBlocker(NamedTuple):
    """One blocker that prevents blueprint rendering or generation."""

    blocker_id: str
    code: str
    node_id: str | None
    requested_module: str | None
    client_explanation: str
    internal_detail: str
    needed_evidence: tuple[str, ...]


class BlueprintGenerationGateReport(NamedTuple):
    """Pre-render gate result for a generated or assembled blueprint."""

    status: BlueprintGenerationGateStatus
    validation_report: BlueprintValidationReport
    blockers: tuple[BlueprintGenerationBlocker, ...]
    secondary_linter: MakeSecondaryLinterReport | None = None

    @property
    def can_render(self) -> bool:
        """Return whether a renderer is allowed to emit blueprint JSON."""
        return self.status == "allowed"
