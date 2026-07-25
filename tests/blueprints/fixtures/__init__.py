# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Blueprint fixture validation test package.

Boundary contract:
- Owns: package identity for sanitized blueprint fixture contract tests.
- Must not: own raw catalog fixtures or production data.
- Allows: imports for fixture validation modules near their test data.
- Split when: fixture suites require domain-specific support packages.
- Merge when: another marker duplicates blueprint fixture test identity.
"""

from __future__ import annotations
