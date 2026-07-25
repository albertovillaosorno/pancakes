# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001060#repo.architecture.ports-adapters.boundary-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Make-native note constants.

Boundary contract:
- Owns: Make note color constants for rendering and MCP note tools.
- Must not: validate notes, render blueprint payloads, or mutate drafts.
- Allows: a single source of truth for the supported Make note palette.
- Split when: Make exposes per-account/custom note palettes.
- Merge when: another Make module owns the exact same color constants.
"""

from __future__ import annotations

from typing import Final

MAKE_NOTE_COLOR_PALETTE: Final[frozenset[str]] = frozenset(
    (
        "#9138FE",
        "#E34FD4",
        "#22B8B8",
        "#7DBE45",
        "#F5C542",
        "#FF8A80",
    )
)
MAKE_NOTE_DEFAULT_COLOR: Final = "#9138FE"
MAKE_MODULE_NOTE_COLOR: Final = "#9138FE"
MAKE_CONNECTION_NOTE_COLOR: Final = "#22B8B8"
