# Repository header: begin
# Provenance source mode: source_refs
# - 001044#repo.make-ast.contract-policy
# - 001047#repo.make-ast.renderer-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Compatibility import path for Make render validation.

Boundary contract:
- Owns: backward-compatible imports for older callers.
- Must not: implement Make-specific export validation or generic AST semantics.
- Allows: re-exporting the Make adapter until callers migrate.
- Split when: this compatibility path can be removed.
- Merge when another compatibility module re-exports the Make adapter.
"""

from __future__ import annotations

from languages.make.render_validation import (
    MakeBlueprintRenderValidationMode,
    MakeBlueprintRenderValidationReport,
    render_and_validate_blueprint,
)

__all__ = (
    "MakeBlueprintRenderValidationMode",
    "MakeBlueprintRenderValidationReport",
    "render_and_validate_blueprint",
)
