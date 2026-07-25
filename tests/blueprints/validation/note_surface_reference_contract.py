# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contract tests for the Make note-surface reference model.

Boundary contract:
- Owns: non-gating note-surface reference behavior and fixture-level
  distinction between route/filter notes and module-detail notes.
- Must not: emit validation findings, require live Make behavior, or make guide
  examples mandatory syntax.
- Allows: deterministic path and metadata classification fixtures.
- Split when: promoted note linter rules start emitting findings.
- Merge when: the validation note module owns the same reference model.
"""

from __future__ import annotations

from blueprints.validation import (
    NoteSurfaceKind,
    classify_note_surface,
    note_guidance_statements,
    note_surface_definition_by_kind,
    note_surface_definitions,
)


def test_note_surface_definitions_keep_route_9a8e8ad6() -> None:
    """Route notes and module notes keep separate responsibilities."""
    route = note_surface_definition_by_kind("connection_line_route_note")
    module = note_surface_definition_by_kind("module_detail_note")

    assert not ("filter predicate" not in route.appropriate_topics), (
        f"Route note topics lost filter predicate guidance: {route}"
    )
    assert not ("input contract" not in module.appropriate_topics), (
        f"Module note topics lost input contract guidance: {module}"
    )
    assert not ("module runbook" not in route.forbidden_topics), (
        f"Route notes must not own module runbooks: {route}"
    )
    assert not ("route predicate" not in module.forbidden_topics), (
        f"Module notes must not own route predicates: {module}"
    )


def test_explicit_filter_note_metadata_selects_route_surface() -> None:
    """Make-native filter-note metadata is deterministic route-note evidence."""
    surface = classify_note_surface(
        source_path=("metadata", "notes", 0),
        note_payload={
            "content": "<b>Rule:</b> Only pass paid invoices.",
            "metadata": {"isFilterNote": True},
        },
    )

    assert surface == "connection_line_route_note", (
        f"Explicit filter note metadata was misclassified: {surface}"
    )


def test_route_filter_path_selects_route_surface() -> None:
    """Route filter paths are not mistaken for module-detail notes."""
    surface = classify_note_surface(
        source_path=("flow", 0, "routes", 1, "filter", "conditions", 0),
    )

    assert surface == "connection_line_route_note", (
        f"Route filter source path was misclassified: {surface}"
    )


def test_module_metadata_note_path_selects_module_detail_surface() -> None:
    """Module metadata notes are not mistaken for route/filter notes."""
    surface = classify_note_surface(
        source_path=("flow", 2, "metadata", "notes", 0),
        note_payload={
            "content": "<b>Why:</b> Posts the final customer message."
        },
    )

    assert surface == "module_detail_note", (
        f"Module metadata note source path was misclassified: {surface}"
    )


def test_ambiguous_root_note_is_not_forced_into_either_surface() -> None:
    """Unmarked root notes remain unknown until deterministic evidence.

    exists.
    """
    surface = classify_note_surface(
        source_path=("metadata", "notes", 0),
        note_payload={"content": "Canvas note for reviewer orientation."},
    )

    assert surface == "unknown_note_surface", (
        f"Ambiguous root note should not be forced into a surface: {surface}"
    )


def test_guidance_statements_preserve_candidates_without_new_gating_rules() -> (
    None
):
    """Imported guide statements are classified without creating hidden lint.

    output.
    """
    statuses = {
        statement.statement_id: statement.status
        for statement in note_guidance_statements()
    }

    expected = {
        "route-notes-own-control-flow": "candidate_rule ",
        "module-notes-own-contracts": "candidate_rule ",
        "note-examples-are-not-mandatory-syntax": "documentation_guidance ",
        "notes-must-not-carry-secret-or-confidential-payloads": (
            "forbidden_content"
        ),
    }
    assert statuses == expected, (
        f"Note guidance classification drifted: {statuses}"
    )


def test_note_surface_reference_keeps_forbidden_24268183() -> None:
    """Both concrete surfaces forbid sensitive content and internal linter.

    mechanics.
    """
    missing: list[NoteSurfaceKind] = []
    for definition in note_surface_definitions():
        forbidden_text = " ".join(definition.forbidden_topics).casefold()
        if (
            "credential" not in forbidden_text
            and "confidential" not in forbidden_text
        ) or "linter predicate" not in forbidden_text:
            missing.append(definition.surface_kind)

    assert not (missing), (
        f"Concrete note surfaces lost sensitive-content boundaries: {missing}"
    )
