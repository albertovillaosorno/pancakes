# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Blueprint AST contract test package.

Boundary contract:
- Owns: package identity for AST parser, renderer-input, and estimator tests.
- Must not: provide fixture factories or validate non-AST contexts.
- Allows: stable imports for AST contract test modules.
- Split when: AST behavior groups need dedicated support packages.
- Merge when: another marker owns identical AST test package identity.
"""

from __future__ import annotations
