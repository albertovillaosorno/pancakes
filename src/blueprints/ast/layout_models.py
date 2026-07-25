# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001044#repo.make-ast.contract-policy
# - 001060#repo.architecture.srp.extreme-one-responsibility
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Typed blueprint layout planning models.

Boundary contract:
- Owns: immutable records for blueprint designer layout plans.
- Must not: compute coordinates, mutate payloads, or analyze layout transitions.
- Allows: typed node layout and aggregate plan containers.
- Split when: layout record families gain independent lifecycle needs.
- Merge when: another model file duplicates these layout records exactly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from blueprints.ast.models import AstPathPart


class BlueprintNodeLayout(NamedTuple):
    """One deterministic designer position for a Make AST node."""

    node_id: str
    module_token: str
    depth: int
    lane: int
    x: int
    y: int
    source_path: tuple[AstPathPart, ...]


class BlueprintNoteLayout(NamedTuple):
    """One deterministic root note position."""

    note_index: int
    module_ids: tuple[str, ...]
    x: int
    y: int
    source_path: tuple[AstPathPart, ...]


class BlueprintLayoutPlan(NamedTuple):
    """A deterministic blueprint layout plan."""

    column_spacing: int
    row_spacing: int
    layouts: tuple[BlueprintNodeLayout, ...]
    notes: tuple[BlueprintNoteLayout, ...]
