# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Data boundary test package.

Boundary contract:
- Owns: package identity for persistent data boundary tests.
- Must not: provide shared runtime data or generated artifacts.
- Allows: stable imports for data-surface test modules.
- Split when: a data domain needs dedicated support packages.
- Merge when: another marker duplicates data test identity.
"""

from __future__ import annotations
