# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001064#repo.make-knowledge.optimizer-hints
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Blueprint optimization advisory package surface.

Boundary contract:
- Owns: public imports for deterministic blueprint optimization advice.
- Must not: validate catalog truth, render blueprints, or read course evidence.
- Allows: re-exporting advisory records and builders from focused modules.
- Split when: optimization becomes a planner or mutating repair flow.
- Merge when: another package surface duplicates these exact exports.
"""

from __future__ import annotations

from blueprints.optimization.advisory import (
    BlueprintOptimizationAdvice,
    build_blueprint_optimization_advice,
)

__all__ = (
    "BlueprintOptimizationAdvice",
    "build_blueprint_optimization_advice",
)
