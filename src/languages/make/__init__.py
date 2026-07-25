# ruff: noqa: RUF067
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001040#repo.runtime.target-modular-layout.bounded-contexts
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Make.com language adapter and source data boundary."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from languages.make.blueprint_export import (
        MakeBlueprintPrivateMetadataLeakError,
        MakeBlueprintRenderError,
        MakeBlueprintRenderMode,
        MakeBlueprintRenderReport,
        render_make_blueprint_json_text,
        render_make_blueprint_payload,
    )
    from languages.make.render_validation import (
        MakeBlueprintRenderValidationMode,
        MakeBlueprintRenderValidationReport,
        render_and_validate_blueprint,
    )
    from languages.make.translation import (
        MAKE_BLUEPRINT_OUTPUT_LANGUAGE_ID,
        MAKE_LANGUAGE_ID,
        PANCAKES_AST_MODEL_ID,
        MakeAdapterProjection,
        parse_make_blueprint_to_pancakes_ast,
        render_pancakes_ast_to_make_blueprint_payload,
        translate_make_blueprint_to_ir,
        translate_make_blueprint_to_pancakes_projection,
        translate_pancakes_ast_to_ir,
    )

_TRANSLATION_EXPORTS: Final = frozenset(
    (
        "MAKE_BLUEPRINT_OUTPUT_LANGUAGE_ID",
        "MAKE_LANGUAGE_ID",
        "PANCAKES_AST_MODEL_ID",
        "MakeAdapterProjection",
        "parse_make_blueprint_to_pancakes_ast",
        "render_pancakes_ast_to_make_blueprint_payload",
        "translate_make_blueprint_to_ir",
        "translate_make_blueprint_to_pancakes_projection",
        "translate_pancakes_ast_to_ir",
    )
)
_BLUEPRINT_EXPORTS: Final = frozenset(
    (
        "MakeBlueprintPrivateMetadataLeakError",
        "MakeBlueprintRenderError",
        "MakeBlueprintRenderMode",
        "MakeBlueprintRenderReport",
        "render_make_blueprint_json_text",
        "render_make_blueprint_payload",
    )
)
_RENDER_VALIDATION_EXPORTS: Final = frozenset(
    (
        "MakeBlueprintRenderValidationMode",
        "MakeBlueprintRenderValidationReport",
        "render_and_validate_blueprint",
    )
)

__all__ = (
    "MAKE_BLUEPRINT_OUTPUT_LANGUAGE_ID",
    "MAKE_LANGUAGE_ID",
    "PANCAKES_AST_MODEL_ID",
    "MakeAdapterProjection",
    "MakeBlueprintPrivateMetadataLeakError",
    "MakeBlueprintRenderError",
    "MakeBlueprintRenderMode",
    "MakeBlueprintRenderReport",
    "MakeBlueprintRenderValidationMode",
    "MakeBlueprintRenderValidationReport",
    "parse_make_blueprint_to_pancakes_ast",
    "render_and_validate_blueprint",
    "render_make_blueprint_json_text",
    "render_make_blueprint_payload",
    "render_pancakes_ast_to_make_blueprint_payload",
    "translate_make_blueprint_to_ir",
    "translate_make_blueprint_to_pancakes_projection",
    "translate_pancakes_ast_to_ir",
)


def __getattr__(name: str) -> object:
    """Load translation exports lazily to keep raw-spec imports acyclic.

    Returns:
        The requested translation export.

    Raises:
        AttributeError: If the requested name is not exported here.
    """
    if name in _BLUEPRINT_EXPORTS:
        module = importlib.import_module("languages.make.blueprint_export")
    elif name in _RENDER_VALIDATION_EXPORTS:
        module = importlib.import_module("languages.make.render_validation")
    elif name in _TRANSLATION_EXPORTS:
        module = importlib.import_module("languages.make.translation")
    else:
        message = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(message)
    value = cast("object", getattr(module, name))
    globals()[name] = value
    return value
