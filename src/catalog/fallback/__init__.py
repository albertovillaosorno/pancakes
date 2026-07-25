# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001042#repo.make-catalog.catalog-only-fallback-utility
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Catalog-only fallback query surface.

Boundary contract:
- Owns: public exports for catalog-only fallback query and planning helpers.
- Must not: implement scoring, validation, planning, or normalization.
- Allows: re-exporting stable fallback APIs from focused sibling modules.
- Split when: exports need runtime branching or adapter-specific behavior.
- Merge when: another fallback package surface duplicates these exports.
"""

from __future__ import annotations

from catalog.fallback.intent import (
    ModulePlannerHints,
    SemanticRequirementPlan,
    build_semantic_requirement_plan,
)
from catalog.fallback.planning import build_catalog_planning_hints
from catalog.fallback.query import retrieve_catalog_modules
from catalog.fallback.results import (
    CatalogModuleCandidate,
    CatalogOnlyPlanningHints,
    CatalogOnlyRetrievalReport,
    CatalogOnlyValidationReport,
    CatalogRetrievalTruncatedError,
    require_complete_catalog_retrieval,
)
from catalog.fallback.validation import validate_catalog_module_selection

__all__ = (
    "CatalogModuleCandidate",
    "CatalogOnlyPlanningHints",
    "CatalogOnlyRetrievalReport",
    "CatalogOnlyValidationReport",
    "CatalogRetrievalTruncatedError",
    "ModulePlannerHints",
    "SemanticRequirementPlan",
    "build_catalog_planning_hints",
    "build_semantic_requirement_plan",
    "require_complete_catalog_retrieval",
    "retrieve_catalog_modules",
    "validate_catalog_module_selection",
)
