# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Blueprint behavior test package.

Boundary contract:
- Owns: package identity for blueprint AST, validation, and repair tests.
- Must not: define shared fixtures or runtime behavior.
- Allows: importing nested blueprint test modules consistently.
- Split when: a blueprint slice needs domain-owned test support.
- Merge when: another package marker duplicates blueprint test identity.
"""

from __future__ import annotations
