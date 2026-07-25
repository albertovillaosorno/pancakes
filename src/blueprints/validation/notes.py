# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001044#repo.make-ast.contract-policy
# - 001046#repo.blueprint-validation.validator-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Root Make metadata note validation.

Boundary contract:
- Owns: root metadata.notes shape and note-anchor import-safety findings.
- Must not: validate node metadata, render notes, or inspect live Make
scenarios.
- Allows: deterministic path-aware note findings over parsed AST metadata.
- Split when: draft-mode legacy notes become a separate explicit validation
mode.
- Merge when: top-level validator owns every note rule without duplication.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeGuard, cast

from blueprints.validation.findings import build_validation_finding

if TYPE_CHECKING:
    from blueprints.ast.models import AstPathPart, JsonObject
    from blueprints.validation.models import BlueprintValidationFinding

NOTE_PATH: tuple[str, str] = ("metadata", "notes")


def validate_root_notes(
    value: object,
    node_ids: set[str],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate root metadata.notes.

    Returns:
        Path-aware validation findings for Make-native root notes.
    """
    if value is None:
        return ()
    if not isinstance(value, list):
        return (
            _note_finding(
                code="ast.notes_invalid",
                path=NOTE_PATH,
                internal_message="Scenario notes must be a list.",
            ),
        )
    findings: list[BlueprintValidationFinding] = []
    for index, note in enumerate(cast("list[object]", value)):
        note_path = (*NOTE_PATH, index)
        if not _is_json_object(note):
            findings.append(
                _note_finding(
                    code="ast.note_invalid",
                    path=note_path,
                    internal_message=(
                        f"Scenario note {index + 1} must be an object."
                    ),
                )
            )
            continue
        findings.extend(
            _validate_structured_note(note=note, index=index, node_ids=node_ids)
        )
    return tuple(findings)


def _validate_structured_note(
    *,
    note: JsonObject,
    index: int,
    node_ids: set[str],
) -> tuple[BlueprintValidationFinding, ...]:
    findings: list[BlueprintValidationFinding] = []
    path = (*NOTE_PATH, index)
    content = note.get("content")
    if content is not None and not _is_non_empty_string(content):
        findings.append(
            _note_finding(
                code="ast.note_content_invalid",
                path=(*path, "content"),
                internal_message=(
                    f"Note {index + 1} content must be a non-empty string."
                ),
            )
        )
    metadata = note.get("metadata")
    if metadata is not None and not _is_json_object(metadata):
        findings.append(
            _note_finding(
                code="ast.note_metadata_invalid",
                path=(*path, "metadata"),
                internal_message=(
                    f"Note {index + 1} metadata must be an object."
                ),
            )
        )
    findings.extend(
        _validate_note_module_ids(note=note, index=index, node_ids=node_ids)
    )
    return tuple(findings)


def _validate_note_module_ids(
    *,
    note: JsonObject,
    index: int,
    node_ids: set[str],
) -> tuple[BlueprintValidationFinding, ...]:
    module_ids = note.get("moduleIds")
    if module_ids is None:
        return ()
    path = (*NOTE_PATH, index, "moduleIds")
    if not isinstance(module_ids, list):
        return (
            _note_finding(
                code="ast.note_module_ids_invalid",
                path=path,
                internal_message=f"Note {index + 1} anchors must be a list.",
            ),
        )
    findings: list[BlueprintValidationFinding] = []
    for module_index, module_id in enumerate(cast("list[object]", module_ids)):
        anchor_path = (*path, module_index)
        if not _valid_note_module_id(module_id):
            findings.append(
                _note_finding(
                    code="ast.note_module_id_invalid",
                    path=anchor_path,
                    internal_message=(
                        f"Note {index + 1} anchor {module_index + 1} "
                        "must be a string or integer ID."
                    ),
                )
            )
            continue
        normalized = str(module_id).strip()
        if normalized not in node_ids:
            findings.append(
                _note_finding(
                    code="ast.note_module_id_unknown",
                    path=anchor_path,
                    internal_message=(
                        f"Note {index + 1} anchor {module_index + 1} "
                        f"references missing node {normalized!r}."
                    ),
                )
            )
    return tuple(findings)


def _note_finding(
    *,
    code: str,
    path: tuple[AstPathPart, ...],
    internal_message: str,
) -> BlueprintValidationFinding:
    return build_validation_finding(
        code=code,
        severity="error",
        node=(None, path),
        catalog_module_id=None,
        messages=(
            "Scenario metadata has an invalid Make import shape.",
            internal_message,
        ),
    )


def _valid_note_module_id(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value > 0
    return _is_non_empty_string(value)


def _is_non_empty_string(value: object) -> TypeGuard[str]:
    return isinstance(value, str) and bool(value.strip())


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    if not isinstance(value, dict):
        return False
    raw_mapping = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in raw_mapping)
