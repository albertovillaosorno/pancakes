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

"""Catalog traversal helpers for fallback flows.

Boundary contract:
- Owns: minimal catalog traversal helpers for fallback flows.
- Must not: score modules, normalize text, validate aliases, or do IO.
- Allows: iterating app/module pairs and exact module lookup by ID.
- Split when: traversal needs indexes, caching, graph edges, or mutation.
- Merge when another traversal module exposes fallback iteration helpers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

    from catalog.models import CatalogApp, CatalogModule


def iter_app_modules(
    apps: tuple[CatalogApp, ...],
) -> Iterator[tuple[CatalogApp, CatalogModule]]:
    """Yield each module with its owning app."""
    for app in apps:
        for version in app.versions:
            for module in version.modules:
                yield app, module


def module_by_id(
    apps: tuple[CatalogApp, ...],
    module_id: str,
) -> CatalogModule:
    """Return one module by ID or fail closed.

    Raises:
        LookupError: If a required lookup cannot be resolved.
    """
    for _, module in iter_app_modules(apps):
        if module.module_id == module_id:
            return module
    message = f"Catalog module does not exist: {module_id}"
    raise LookupError(message)
