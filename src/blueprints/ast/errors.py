# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001044#repo.make-ast.contract-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Typed Make AST parser errors.

Boundary contract:
- Owns: blueprint AST exception types shared by parser and callers.
- Must not: parse payloads, format diagnostics, or recover from errors.
- Allows: stable exception classes for typed failure boundaries.
- Split when: independent parser, renderer, or resolution errors need ownership.
- Merge when: another error file defines the same AST parse exception.
"""

from __future__ import annotations


class MakeAstParseError(ValueError):
    """Raised when Make blueprint JSON cannot be parsed into the typed AST."""
