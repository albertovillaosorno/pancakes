# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Language-neutral Pancakes intermediate representation boundary.

Boundary contract:
- Owns: public IR model and graph validation exports.
- Must not: parse Make JSON, render platform payloads, or call live services.
- Allows: stable DAG records shared by language adapters and blueprint contexts.
- Split when: lowering, rendering, or adapter projection gains runtime code.
- Merge when: another package marker duplicates this exact public IR surface.
"""

from __future__ import annotations

from ir.graph import IrGraphValidationFinding, validate_ir_graph
from ir.models import (
    IR_NODE_KINDS,
    IR_SCHEMA_VERSION,
    IrCapabilityRef,
    IrDocument,
    IrEdge,
    IrEdgeKind,
    IrGraph,
    IrNode,
    IrNodeKind,
    IrPathPart,
    IrPort,
    IrPortDirection,
    IrSourceRef,
    JsonObject,
)

__all__ = (
    "IR_NODE_KINDS",
    "IR_SCHEMA_VERSION",
    "IrCapabilityRef",
    "IrDocument",
    "IrEdge",
    "IrEdgeKind",
    "IrGraph",
    "IrGraphValidationFinding",
    "IrNode",
    "IrNodeKind",
    "IrPathPart",
    "IrPort",
    "IrPortDirection",
    "IrSourceRef",
    "JsonObject",
    "validate_ir_graph",
)
