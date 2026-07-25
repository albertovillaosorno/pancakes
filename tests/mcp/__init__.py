# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""MCP contract test package.

Boundary contract:
- Owns: package identity for repository MCP surface tests.
- Must not: own source package, media, or Windows service behavior checks.
- Allows: stable imports for MCP test modules.
- Split when: MCP tool groups need dedicated support packages.
- Merge when: another marker duplicates MCP test identity.
"""

from __future__ import annotations
