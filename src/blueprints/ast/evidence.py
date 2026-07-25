# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001044#repo.make-ast.contract-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Local evidence summaries for typed Make AST payloads.

Boundary contract:
- Owns: local opaque-field and designer-message evidence summaries.
- Must not: validate runtime correctness, compute deltas, or inspect live data.
- Allows: deterministic evidence paths and JSON-ready report projection.
- Split when: evidence families need independent reporting or policy.
- Merge when: another evidence file emits the same summary identically.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, NamedTuple, cast

from blueprints.ast.orphans import extract_designer_orphan_groups
from blueprints.ast.traversal import iter_ast_nodes

if TYPE_CHECKING:
    from blueprints.ast.models import JsonObject, MakeAstNode, MakeAstRoot

MAKE_FIELD_COLLECTION_METADATA_KEYS: Final[tuple[str, ...]] = (
    "parameters",
    "expect",
    "interface",
)
MAKE_OBJECT_METADATA_KEYS: Final[tuple[str, ...]] = ("restore",)
KNOWN_METADATA_KEYS: Final[frozenset[str]] = frozenset(
    (
        "designer",
        "scenario",
        *MAKE_OBJECT_METADATA_KEYS,
        *MAKE_FIELD_COLLECTION_METADATA_KEYS,
        "notes",
        "resolution",
        "forecast",
        "latency_forecast",
        "mapping_suggestions",
        "placeholder_registry",
    )
)


class MakeAstEvidenceReport(NamedTuple):
    """Deterministic evidence summary for one AST root."""

    opaque_field_paths: tuple[str, ...]
    designer_message_paths: tuple[str, ...]

    @property
    def designer_message_count(self) -> int:
        """Return how many designer message lists were found."""
        return len(self.designer_message_paths)

    def as_dict(self) -> JsonObject:
        """Return a JSON-ready evidence report."""
        return {
            "opaque_field_paths": list(self.opaque_field_paths),
            "designer_message_paths": list(self.designer_message_paths),
            "designer_message_count": self.designer_message_count,
        }


def ast_evidence_report(root: MakeAstRoot) -> MakeAstEvidenceReport:
    """Return deterministic local evidence paths for one AST root."""
    return MakeAstEvidenceReport(
        opaque_field_paths=_opaque_field_paths(root),
        designer_message_paths=_designer_message_paths(root),
    )


def _opaque_field_paths(root: MakeAstRoot) -> tuple[str, ...]:
    paths = [f"$.{key}" for key in root.unknown_fields]
    paths.extend(_unknown_metadata_paths(root.scenario.metadata, "$.metadata"))
    for node in iter_ast_nodes(root):
        node_path = _node_json_path(node)
        paths.extend(f"{node_path}.{key}" for key in node.unknown_fields)
        metadata = node.raw_payload.get("metadata")
        if isinstance(metadata, dict):
            paths.extend(
                _unknown_metadata_paths(
                    cast("JsonObject", metadata), f"{node_path}.metadata"
                )
            )
    return tuple(sorted(set(paths)))


def _designer_message_paths(root: MakeAstRoot) -> tuple[str, ...]:
    paths: list[str] = []
    _append_designer_path(
        paths, root.scenario.metadata, "$.metadata.designer.messages"
    )
    for node in iter_ast_nodes(root):
        metadata = node.raw_payload.get("metadata")
        if isinstance(metadata, dict):
            _append_designer_path(
                paths,
                cast("JsonObject", metadata),
                f"{_node_json_path(node)}.metadata.designer.messages",
            )
    for group in extract_designer_orphan_groups(root):
        for node_index, node in enumerate(group.nodes):
            metadata = node.raw_payload.get("metadata")
            if isinstance(metadata, dict):
                _append_designer_path(
                    paths,
                    cast("JsonObject", metadata),
                    (
                        "$.metadata.designer.orphans"
                        f"[{group.group_index}][{node_index}].metadata.designer.messages"
                    ),
                )
    return tuple(sorted(set(paths)))


def _unknown_metadata_paths(metadata: JsonObject, path: str) -> list[str]:
    return [
        f"{path}.{key}"
        for key in sorted(metadata)
        if key not in KNOWN_METADATA_KEYS
    ]


def _append_designer_path(
    paths: list[str], metadata: JsonObject, path: str
) -> None:
    designer = metadata.get("designer")
    if not isinstance(designer, dict):
        return
    designer_payload = cast("JsonObject", designer)
    if isinstance(designer_payload.get("messages"), list):
        paths.append(path)


def _node_json_path(node: MakeAstNode) -> str:
    rendered = "$"
    for part in node.source_trace.path:
        rendered += f"[{part}]" if isinstance(part, int) else f".{part}"
    return rendered
