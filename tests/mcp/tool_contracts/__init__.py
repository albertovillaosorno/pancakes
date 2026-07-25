# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""MCP tool contract test package.

Boundary contract:
- Owns: package identity for MCP tool contract tests.
- Must not: own transport infrastructure outside the MCP slice.
- Allows: stable imports for MCP tool test modules.
- Split when: tool families need dedicated support packages.
- Merge when: another marker duplicates MCP tool test identity.
"""

from __future__ import annotations
