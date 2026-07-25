# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001032#repo.quality.no-silly-linter-bypasses
# - 001035#repo.workflow.todo-backlog-and-continue-contract
# - 001046#repo.blueprint-validation.import-shape-safety
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Reference model for Make note surfaces.

Boundary contract:
- Owns: non-gating note-surface definitions and deterministic surface
  classification helpers for future linter rule design.
- Must not: emit validation findings, rewrite notes, contact Make.com, or make
  every note example mandatory syntax.
- Allows: separating route/filter note evidence from module-detail note evidence
  when the local AST path or explicit note metadata proves the surface.
- Split when: note generation, note repair, or output rendering needs executable
  behavior.
- Merge when: another validation module owns the same note-surface reference.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Literal, NamedTuple, TypeGuard, cast

if TYPE_CHECKING:
    from blueprints.ast.models import AstPathPart, JsonObject

type NoteSurfaceKind = Literal[
    "connection_line_route_note ",
    "module_detail_note ",
    "unknown_note_surface",
]
type NoteGuidanceStatus = Literal[
    "candidate_rule ",
    "documentation_guidance ",
    "forbidden_content",
]


class NoteSurfaceDefinition(NamedTuple):
    """One conceptual Make note surface definition."""

    surface_kind: NoteSurfaceKind
    title: str
    primary_purpose: str
    analogy: str
    appropriate_topics: tuple[str, ...]
    forbidden_topics: tuple[str, ...]
    candidate_tags: tuple[str, ...]
    non_enforceable_guidance: tuple[str, ...]


class NoteGuidanceStatement(NamedTuple):
    """One imported-guide statement classified for future linter work."""

    statement_id: str
    status: NoteGuidanceStatus
    surface_kind: NoteSurfaceKind
    summary: str
    deterministic_evidence: tuple[str, ...]


NOTE_SURFACE_DEFINITIONS: Final[tuple[NoteSurfaceDefinition, ...]] = (
    NoteSurfaceDefinition(
        surface_kind="connection_line_route_note",
        title="Connection-line, filter, and route note",
        primary_purpose=(
            "Explain why a bundle passes, drops, or moves through a branch."
        ),
        analogy="Typed guard or if statement.",
        appropriate_topics=(
            "filter predicate ",
            "router branch rule ",
            "drop safety ",
            "fallback behavior ",
            "route exclusivity ",
            "retry or error classification ",
            "cost or anti-loop guard",
        ),
        forbidden_topics=(
            "module runbook ",
            "agent personality ",
            "connection setup instructions ",
            "API credentials ",
            "full payload example ",
            "customer-confidential data ",
            "internal rule ID ",
            "linter predicate internals ",
            "generic continues-to-next-module text",
        ),
        candidate_tags=(
            "Rule ",
            "Why ",
            "Drop Safety ",
            "Fallback ",
            "Edge Case ",
            "Action",
        ),
        non_enforceable_guidance=(
            "The guide examples are preferred patterns, not mandatory syntax.",
            (
                "Route notes do not need module input and output contracts "
                "unless a future "
                "rule is promoted."
            ),
        ),
    ),
    NoteSurfaceDefinition(
        surface_kind="module_detail_note",
        title="Module-click and module-detail note",
        primary_purpose=(
            "Explain module responsibility, contracts, side effects, and "
            "operations."
        ),
        analogy="Function contract.",
        appropriate_topics=(
            "module purpose ",
            "input contract ",
            "output contract ",
            "side effects ",
            "failure mode ",
            "remediation ",
            "runbook link ",
            "data classification ",
            "tool description",
        ),
        forbidden_topics=(
            "route predicate ",
            "branch exclusivity ",
            "fallback branch logic ",
            "API credentials ",
            "full payload dump ",
            "full customer document ",
            "internal rule ID ",
            "linter predicate internals ",
            "generic repetition of the module name",
        ),
        candidate_tags=(
            "Why ",
            "Input Contract ",
            "Output Contract ",
            "Impact ",
            "Failure Mode ",
            "Remediation",
        ),
        non_enforceable_guidance=(
            "Critical modules may need richer notes than noncritical modules.",
            (
                "Tool descriptions may use plain text when that is the "
                "Make-native "
                "field shape."
            ),
        ),
    ),
)

NOTE_GUIDANCE_STATEMENTS: Final[tuple[NoteGuidanceStatement, ...]] = (
    NoteGuidanceStatement(
        statement_id="route-notes-own-control-flow",
        status="candidate_rule",
        surface_kind="connection_line_route_note",
        summary=(
            "Route/filter notes should describe branch logic and drop safety."
        ),
        deterministic_evidence=(
            "source path enters a route filter ",
            "note metadata explicitly marks the note as a filter note",
        ),
    ),
    NoteGuidanceStatement(
        statement_id="module-notes-own-contracts",
        status="candidate_rule",
        surface_kind="module_detail_note",
        summary=(
            "Module-detail notes should describe responsibility, contracts, "
            "and "
            "failure "
            "behavior."
        ),
        deterministic_evidence=(
            "source path enters a module metadata.notes list",
        ),
    ),
    NoteGuidanceStatement(
        statement_id="note-examples-are-not-mandatory-syntax",
        status="documentation_guidance",
        surface_kind="unknown_note_surface",
        summary=(
            "Imported examples remain guidance unless a future deterministic "
            "rule is promoted."
        ),
        deterministic_evidence=(),
    ),
    NoteGuidanceStatement(
        statement_id="notes-must-not-carry-secret-or-confidential-payloads",
        status="forbidden_content",
        surface_kind="unknown_note_surface",
        summary=(
            "Notes must not require secrets, full payloads, "
            "customer-confidential data, "
            "or internal linter predicate mechanics."
        ),
        deterministic_evidence=("local note content inspection",),
    ),
)

_ROUTE_CONTAINER_KEYS: Final[frozenset[str]] = frozenset(("routes", "branches"))


def note_surface_definitions() -> tuple[NoteSurfaceDefinition, ...]:
    """Return the non-gating Make note-surface reference definitions."""
    return NOTE_SURFACE_DEFINITIONS


def note_guidance_statements() -> tuple[NoteGuidanceStatement, ...]:
    """Return classified imported-guide statements for future linter work."""
    return NOTE_GUIDANCE_STATEMENTS


def note_surface_definition_by_kind(
    surface_kind: NoteSurfaceKind,
) -> NoteSurfaceDefinition:
    """Return one note-surface definition.

    Raises:
        ValueError: If the surface has no concrete definition.
    """
    for definition in NOTE_SURFACE_DEFINITIONS:
        if definition.surface_kind == surface_kind:
            return definition
    message = f"No concrete note-surface definition for {surface_kind!r}."
    raise ValueError(message)


def classify_note_surface(
    *,
    source_path: tuple[AstPathPart, ...],
    note_payload: object | None = None,
) -> NoteSurfaceKind:
    """Classify a note surface only when local evidence is deterministic.

    Returns:
        The route/filter surface, module-detail surface, or unknown surface.
    """
    if _explicit_filter_note_payload(note_payload):
        return "connection_line_route_note"
    if _is_module_metadata_note_path(source_path):
        return "module_detail_note"
    if _is_route_filter_path(source_path):
        return "connection_line_route_note"
    return "unknown_note_surface"


def _explicit_filter_note_payload(value: object | None) -> bool:
    note = _object_or_empty(value)
    metadata = _object_or_empty(note.get("metadata"))
    return (
        note.get("isFilterNote") is True or metadata.get("isFilterNote") is True
    )


def _is_module_metadata_note_path(path: tuple[AstPathPart, ...]) -> bool:
    for index in range(2, len(path) - 1):
        if path[index] != "metadata" or path[index + 1] != "notes":
            continue
        if path[index - 2] == "flow" and isinstance(path[index - 1], int):
            return True
    return False


def _is_route_filter_path(path: tuple[AstPathPart, ...]) -> bool:
    for index, part in enumerate(path):
        if part != "filter":
            continue
        route_prefix = path[:index]
        if any(segment in _ROUTE_CONTAINER_KEYS for segment in route_prefix):
            return True
    return False


def _object_or_empty(value: object | None) -> JsonObject:
    return value if _is_json_object(value) else {}


def _is_json_object(value: object | None) -> TypeGuard[JsonObject]:
    if not isinstance(value, dict):
        return False
    raw = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in raw)
