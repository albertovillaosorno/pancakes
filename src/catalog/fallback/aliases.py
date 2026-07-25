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

"""Catalog module alias indexing.

Boundary contract:
- Owns: deterministic alias keys for catalog-only module selection.
- Must not: rank candidates, validate selections, plan goals, or perform IO.
- Allows: normalized aliases derived from app and module text fields.
- Split when: aliasing needs learned synonyms or external vocabulary data.
- Merge when: another module builds the same catalog alias index.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from catalog.fallback.text import normalize_text

if TYPE_CHECKING:
    from collections.abc import Iterator

    from catalog.models import CatalogApp, CatalogModule


def module_alias_index(
    apps: tuple[CatalogApp, ...],
) -> dict[str, tuple[str, ...]]:
    """Return normalized lookup aliases for catalog-only validation."""
    mutable_index: dict[str, set[str]] = {}
    for app in apps:
        for version in app.versions:
            for module in version.modules:
                for alias in module_aliases(app=app, module=module):
                    mutable_index.setdefault(alias, set()).add(module.module_id)
    return {
        alias: tuple(sorted(module_ids))
        for alias, module_ids in sorted(mutable_index.items())
    }


def module_aliases(*, app: CatalogApp, module: CatalogModule) -> Iterator[str]:
    """Yield normalized aliases for one module."""
    raw_aliases = (
        module.module_id,
        module.external_id,
        module.internal_name,
        module.display_name,
        f"{app.app_slug}:{module.internal_name}",
        f"{app.app_slug}:{module.display_name}",
        f"{app.app_slug}:{module.module_kind}:{module.internal_name}",
    )
    for raw_alias in raw_aliases:
        alias = normalize_text(raw_alias)
        if alias:
            yield alias
