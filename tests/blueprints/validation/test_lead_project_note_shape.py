# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Lead-routing project asset metadata note shape tests.

Boundary contract:
- Owns: lead-routing source project and importable fixture note shape
  regression tests.
- Must not: claim live Make importability, mutate topology, or validate
  credentials.
- Allows: offline source/fixture JSON loading and exact note text
  preservation checks.
- Split when: lead-routing source cleanup gains broader asset validation.
- Merge when: another lead-routing test owns source note normalization.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from blueprints.ast import JsonObject, parse_make_ast_json_text
from blueprints.validation import BlueprintValidationFinding, validate_blueprint
from catalog.json_payloads import normalize_json_object

from tests.catalog.test_module_token_resolution import native_module_snapshot
from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from pathlib import Path

REPO_ROOT = repo_root()
SOURCE_PROJECT_ASSET = (
    REPO_ROOT
    / "tests"
    / "blueprints"
    / "fixtures"
    / "portfolio_projects"
    / "lead-routing-data-store-mvp"
    / "scenario.json"
)
FIXTURE_ROOT = REPO_ROOT / "tests" / "blueprints" / "fixtures" / "importability"
IMPORTABLE_LEAD_FIXTURES = (
    FIXTURE_ROOT / "valid_lead_routing_importable_candidate.json",
    FIXTURE_ROOT / "valid_lead_routing_router.json",
)
ORIGINAL_SOURCE_NOTE_TEXT = (
    "Offline portfolio draft for fake lead intake and routing. "
    "No credentials or production endpoints are embedded."
)


def test_lead_project_notes_are_object_shaped_or_known_draft_blockers() -> None:
    """The source project keeps draft blockers explicit."""
    payload = load_json_object(SOURCE_PROJECT_ASSET)
    notes = root_notes(payload)

    assert_object_notes(notes, SOURCE_PROJECT_ASSET)

    report = validate_blueprint(
        root=parse_make_ast_json_text(json.dumps(payload, sort_keys=True)),
        catalog=native_module_snapshot(),
    )
    note_findings = note_shape_findings(report.findings)
    assert not (note_findings), (
        f"Lead project notes produced shape findings: {note_findings}"
    )


def test_importable_lead_fixture_does_not_use_string_notes() -> None:
    """Importable lead fixtures must not use string metadata notes."""
    for path in IMPORTABLE_LEAD_FIXTURES:
        payload = load_json_object(path)
        for note_path, notes in iter_metadata_notes(payload):
            assert_object_notes(notes, path, note_path=note_path)


def test_note_normalization_preserves_original_text() -> None:
    """The source note text survives normalization exactly once."""
    payload = load_json_object(SOURCE_PROJECT_ASSET)
    note = root_notes(payload)[0]
    assert isinstance(note, dict), (
        f"Lead project note is not an object: {note!r}"
    )
    normalized_note = normalize_json_object(cast("Mapping[str, object]", note))

    assert normalized_note.get("content") == ORIGINAL_SOURCE_NOTE_TEXT, (
        f"Lead project note text changed: {normalized_note!r}"
    )
    metadata = normalized_note.get("metadata")
    assert isinstance(metadata, dict), (
        f"Lead project note metadata must be an object: {normalized_note!r}"
    )
    normalized_metadata = normalize_json_object(
        cast("Mapping[str, object]", metadata)
    )
    expected_metadata = {
        "scope": "source_draft",
        "source": "lead-routing-data-store-mvp",
    }
    for key, expected in expected_metadata.items():
        if normalized_metadata.get(key) != expected:
            prefix = f"Lead project note metadata lost {key!r}={expected!r}"
            assert normalized_metadata.get(key) == expected, (
                f"{prefix}: {normalized_metadata!r}"
            )


def load_json_object(path: Path) -> JsonObject:
    """Load a JSON object from disk.

    Returns:
        The loaded JSON object.
    """
    payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(payload, dict), f"{path} must contain a JSON object."
    return normalize_json_object(cast("Mapping[str, object]", payload))


def root_notes(payload: JsonObject) -> list[object]:
    """Return root metadata.notes from a lead-routing payload.

    Returns:
        The root metadata.notes list.
    """
    metadata = payload.get("metadata")
    assert isinstance(metadata, dict), (
        f"Lead-routing payload metadata must be an object: {payload!r}"
    )
    metadata_object = normalize_json_object(
        cast("Mapping[str, object]", metadata)
    )
    notes = metadata_object.get("notes")
    assert isinstance(notes, list), (
        "Lead-routing payload metadata.notes must be a list: "
        f"{metadata_object!r}"
    )
    return cast("list[object]", notes)


def iter_metadata_notes(
    value: object,
    *,
    path: tuple[str | int, ...] = (),
) -> Iterator[tuple[tuple[str | int, ...], list[object]]]:
    """Yield every metadata.notes list in a JSON-like value.

    Yields:
        Metadata note paths with their notes list.
    """
    if isinstance(value, dict):
        mapping = cast("dict[object, object]", value)
        metadata = mapping.get("metadata")
        if isinstance(metadata, dict):
            metadata_mapping = cast("dict[object, object]", metadata)
            notes = metadata_mapping.get("notes")
            if isinstance(notes, list):
                yield (*path, "metadata", "notes"), cast("list[object]", notes)
        for key, child in mapping.items():
            if isinstance(key, str):
                yield from iter_metadata_notes(child, path=(*path, key))
    elif isinstance(value, list):
        for index, child in enumerate(cast("list[object]", value)):
            yield from iter_metadata_notes(child, path=(*path, index))


def assert_object_notes(
    notes: list[object],
    file_path: Path,
    *,
    note_path: tuple[str | int, ...] = ("metadata", "notes"),
) -> None:
    """Assert every note item is an object."""
    for index, note in enumerate(notes):
        assert isinstance(note, dict), (
            f"{file_path} note at {(*note_path, index)!r} "
            f"must be an object: {note!r}"
        )


def note_shape_findings(
    findings: tuple[BlueprintValidationFinding, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Return note-shape validation findings.

    Returns:
        Note-specific AST validation findings.
    """
    return tuple(
        finding for finding in findings if finding.code.startswith("ast.note")
    )
