# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Catalog contract test package.

Boundary contract:
- Owns: package identity for catalog schema and fixture tests.
- Must not: own raw-spec transport behavior outside catalog ownership.
- Allows: stable imports for catalog test modules.
- Split when: catalog fixtures need dedicated support packages.
- Merge when: another marker duplicates catalog test identity.
"""

from __future__ import annotations
