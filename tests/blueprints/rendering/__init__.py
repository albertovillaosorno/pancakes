# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Blueprint rendering test package.

Boundary contract:
- Owns: package identity for blueprint rendering contract tests.
- Must not: validate parser, repair, or catalog behavior directly.
- Allows: stable imports for rendering-focused test modules.
- Split when: rendering tests need scenario-owned support packages.
- Merge when: another marker owns identical rendering test identity.
"""

from __future__ import annotations
