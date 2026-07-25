# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001040#repo.runtime.target-modular-layout.bounded-contexts
# - 001049#repo.blueprint-repair.diagnostics-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Make blueprint repair diagnostics slice boundary.

Boundary contract:
- Owns: the public import surface for offline blueprint repair capabilities.
- Must not: implement repair logic, validation, staging, or live service access.
- Allows: re-exporting stable repair models and functions from owned modules.
- Split when: exports require compatibility adapters or optional integrations.
- Merge when: another package marker duplicates this exact repair API surface.
"""

from __future__ import annotations

from blueprints.repair.diagnostics import (
    RepairCandidate,
    RepairCategory,
    RepairDiagnosticsReport,
    RepairSeverity,
    propose_repair_candidates,
)
from blueprints.repair.diff_learning import (
    DiffLearningSuggestion,
    draft_diff_learning_suggestions,
)
from blueprints.repair.identity import SLICE_NAME
from blueprints.repair.migration import (
    ModuleMigrationAssessment,
    assess_module_migration,
)
from blueprints.repair.offline import repair_blueprint_offline
from blueprints.repair.outcome import (
    BlueprintRepairOutcome,
    BlueprintRepairStatus,
)
from blueprints.repair.staging import (
    PLACEHOLDER_DEFAULTS,
    prepare_blueprint_for_staging_import,
)

__all__ = (
    "PLACEHOLDER_DEFAULTS",
    "SLICE_NAME",
    "BlueprintRepairOutcome",
    "BlueprintRepairStatus",
    "DiffLearningSuggestion",
    "ModuleMigrationAssessment",
    "RepairCandidate",
    "RepairCategory",
    "RepairDiagnosticsReport",
    "RepairSeverity",
    "assess_module_migration",
    "draft_diff_learning_suggestions",
    "prepare_blueprint_for_staging_import",
    "propose_repair_candidates",
    "repair_blueprint_offline",
)
