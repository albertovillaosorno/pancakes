# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Blueprint repair diagnostics test package.

Boundary contract:
- Owns: package identity for repair diagnostic contract tests.
- Must not: own validator or catalog behavior checks.
- Allows: stable imports for repair-focused test modules.
- Split when: repair diagnostics need dedicated support helpers.
- Merge when: another marker duplicates repair test identity.
"""

from __future__ import annotations
