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

"""Catalog-only module selection validation.

Boundary contract:
- Owns: deterministic validation of requested aliases against catalog truth.
- Must not: rank candidates, build plans, mutate catalogs, or perform IO.
- Allows: alias index lookup and fail-closed missing or ambiguous results.
- Split when: validation needs suggestions, repair actions, or external state.
- Merge when: another validator returns the same catalog-only selection result.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from catalog.fallback.aliases import module_alias_index
from catalog.fallback.results import CatalogOnlyValidationReport
from catalog.fallback.text import normalize_text

if TYPE_CHECKING:
    from collections.abc import Iterable

    from catalog.models import CatalogSnapshot


def validate_catalog_module_selection(
    *,
    snapshot: CatalogSnapshot,
    requested_modules: Iterable[str],
) -> CatalogOnlyValidationReport:
    """Validate requested module aliases against catalog truth only.

    Returns:
        The validated value.
    """
    requested = tuple(requested_modules)
    aliases = module_alias_index(snapshot.apps)
    resolved: set[str] = set()
    missing: list[str] = []
    ambiguous: dict[str, tuple[str, ...]] = {}
    for request in requested:
        matches = aliases.get(normalize_text(request))
        if matches is None:
            missing.append(request)
        elif len(matches) > 1:
            ambiguous[request] = matches
        elif not matches:
            missing.append(request)
        else:
            (module_id,) = matches
            resolved.add(module_id)
    return CatalogOnlyValidationReport(
        catalog_fingerprint=snapshot.fingerprint,
        requested_modules=requested,
        resolved_module_ids=tuple(sorted(resolved)),
        missing_modules=tuple(missing),
        ambiguous_modules=ambiguous,
        valid=not missing and not ambiguous,
    )
