# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Shared test support package.

Boundary contract:
- Owns: package identity for deterministic test support helpers.
- Must not: define fixtures, test behavior, or repository policy assertions.
- Allows: imports of focused helper modules used by sliced tests.
- Split when: support helpers need domain-owned packages near their test slice.
- Merge when: another support package marker duplicates this package identity.
"""

from __future__ import annotations
