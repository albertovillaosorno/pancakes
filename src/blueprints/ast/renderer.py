# Repository header: begin
# Provenance source mode: source_refs
# - 001044#repo.make-ast.contract-policy
# - 001047#repo.make-ast.renderer-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Compatibility import path for Make blueprint rendering.

Boundary contract:
- Owns: backward-compatible imports for older callers.
- Must not: implement Make-specific export rules, provider token translation, or
privacy policy.
- Allows: re-exporting the Make language adapter until callers migrate to
`languages.make`.
- Split when: this compatibility path can be removed.
- Merge when: another compatibility module re-exports the same Make adapter
surface.
"""

from __future__ import annotations

from languages.make.blueprint_export import (
    MakeBlueprintPrivateMetadataLeakError,
    MakeBlueprintRenderError,
    MakeBlueprintRenderMode,
    MakeBlueprintRenderReport,
    render_make_blueprint_json_text,
    render_make_blueprint_payload,
)

__all__ = (
    "MakeBlueprintPrivateMetadataLeakError",
    "MakeBlueprintRenderError",
    "MakeBlueprintRenderMode",
    "MakeBlueprintRenderReport",
    "render_make_blueprint_json_text",
    "render_make_blueprint_payload",
)
