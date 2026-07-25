# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Blueprint optimization advisory test package.

Boundary contract:
- Owns: package identity for blueprint optimization advisory tests.
- Must not: own validation, repair, rendering, or catalog behavior checks.
- Allows: stable imports for optimization-focused test modules.
- Split when: optimization advice needs dedicated support helpers.
- Merge when: another marker duplicates optimization test identity.
"""

from __future__ import annotations
