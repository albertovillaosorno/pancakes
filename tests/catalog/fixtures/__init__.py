# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Catalog fixture support package.

Boundary contract:
- Owns: package identity for reusable catalog fixture helpers.
- Must not: define pytest fixtures, catalog policy, or live data sources.
- Allows: imports of deterministic synthetic fixture builders.
- Split when: fixture helpers need separate domain packages.
- Merge when: another package marker duplicates catalog fixture identity.
"""

from __future__ import annotations
