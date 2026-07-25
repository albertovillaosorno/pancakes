# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001042#repo.make-catalog.schema-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Shared Make raw-spec field collection contract.

Boundary contract:
- Owns: catalog field collection names and their normalized directions.
- Must not: compile raw specs, ingest SQLite rows, or validate
  catalog snapshots.
- Allows: immutable constants shared by compiler and knowledge storage.
- Split when: field collection policy becomes versioned or app-specific.
- Merge when: another catalog module owns this exact constant without drift.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from catalog.models import CatalogFieldDirection

FIELD_COLLECTIONS: Final[tuple[tuple[str, CatalogFieldDirection], ...]] = (
    ("parameters", "parameter"),
    ("expect", "expect"),
    ("interface", "interface"),
)
