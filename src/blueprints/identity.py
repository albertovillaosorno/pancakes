# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001060#repo.architecture.ddd.bounded-context-source-layout
# - 001060#repo.architecture.ast.central-domain-boundary
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Blueprint AST package identity.

Boundary contract:
- Owns: stable package identity values for the blueprint AST bounded context.
- Must not: parse, render, validate, repair, or inspect blueprint payloads.
- Allows: immutable package identity constants for public import surfaces.
- Split when: identity needs versioning, aliases, or compatibility adapters.
- Merge when: another module owns the same blueprint AST package identity.
"""

from __future__ import annotations

from typing import Final

SLICE_NAME: Final[str] = "blueprints.ast"
