# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001049#repo.blueprint-repair.offline-action-contract
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Typed offline blueprint repair outcome records.

Boundary contract:
- Owns: typed records for non-mutating offline repair outcomes.
- Must not: compute diagnostics, validate blueprints, or prepare staging input.
- Allows: immutable status and payload containers shared by repair workflows.
- Split when: outcome variants require distinct domain records.
- Merge when: another model file duplicates these outcome records exactly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, NamedTuple

if TYPE_CHECKING:
    from blueprints.repair.diagnostics import RepairDiagnosticsReport
    from blueprints.validation import (
        BlueprintValidationReport,
        HandoffPlaceholder,
    )

type BlueprintRepairStatus = Literal[
    "accepted_as_generated",
    "accepted_after_repair",
    "rejected_with_reasons",
    "not_applicable",
]


class BlueprintRepairOutcome(NamedTuple):
    """Explicit non-mutating offline repair outcome."""

    status: BlueprintRepairStatus
    validation_report: BlueprintValidationReport
    diagnostics: RepairDiagnosticsReport
    handoff_placeholders: tuple[HandoffPlaceholder, ...]
    repair_applied: bool = False
