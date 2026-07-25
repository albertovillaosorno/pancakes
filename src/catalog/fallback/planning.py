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

"""Catalog-only planning hint assembly.

Boundary contract:
- Owns: deterministic planning hints assembled from catalog-only retrieval.
- Must not: score modules, validate aliases, mutate catalogs, or perform IO.
- Allows: collecting candidate apps, module IDs, and required parameters.
- Split when: hint assembly becomes provider, blueprint, or UI specific.
- Merge when: another planner returns the same catalog-only hint payload.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from catalog.fallback.query import retrieve_catalog_modules
from catalog.fallback.results import (
    CatalogOnlyPlanningHints,
    require_complete_catalog_retrieval,
)
from catalog.fallback.traversal import module_by_id

if TYPE_CHECKING:
    from catalog.models import CatalogSnapshot


def build_catalog_planning_hints(
    *,
    snapshot: CatalogSnapshot,
    goal_text: str,
    limit: int = 10,
    source_label: str | None = None,
) -> CatalogOnlyPlanningHints:
    """Build deterministic planning hints from catalog truth only.

    Returns:
        The constructed value.
    """
    retrieval = retrieve_catalog_modules(
        snapshot=snapshot,
        query_text=goal_text,
        limit=limit,
        source_label=source_label,
    )
    require_complete_catalog_retrieval(retrieval)
    required_parameter_ids: set[str] = set()
    for candidate in retrieval.candidates:
        module = module_by_id(snapshot.apps, candidate.module_id)
        required_parameter_ids.update(
            field.field_id for field in module.parameters if field.required
        )
    return CatalogOnlyPlanningHints(
        catalog_fingerprint=snapshot.fingerprint,
        goal_text=goal_text,
        fallback_mode="catalog_only",
        candidate_apps=tuple(
            sorted({item.app_slug for item in retrieval.candidates})
        ),
        candidate_module_ids=tuple(
            item.module_id for item in retrieval.candidates
        ),
        required_parameter_ids=tuple(sorted(required_parameter_ids)),
        candidate_modules=retrieval.candidates,
    )
