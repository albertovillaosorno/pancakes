# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001060#repo.architecture.context-responsibility-map
# - 001064#repo.make-knowledge.optimizer-hints
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Execution paths for non-mutating blueprint optimization advice.

Boundary contract:
- Owns: path expansion needed by optimization advice.
- Must not: parse, validate, render, or rewrite blueprint ASTs.
- Allows: route, branch, and tool flow expansion for advisory scans.
- Split when: path scoring or mutating planning becomes active.
- Merge when: AST traversal owns execution-path semantics directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from blueprints.ast.execution_paths import iter_ast_execution_paths

if TYPE_CHECKING:
    from blueprints.ast.models import MakeAstNode, MakeAstRoot


def iter_optimization_paths(
    root: MakeAstRoot,
) -> tuple[tuple[MakeAstNode, ...], ...]:
    """Return possible node paths for non-mutating optimization scans."""
    return iter_ast_execution_paths(root)
