# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 001061#repo.delivery.manual-capture-template
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Validation helpers for manual assisted-delivery capture packets.

Boundary contract:
- Owns: shape and content validation for manual assisted-delivery captures.
- Must not: validate blueprint AST semantics or mutate captured payloads.
- Allows: deterministic schema, forbidden-scope, and blocker checks.
- Split when: capture sections need independently owned validation policies.
- Merge when another capture validator reports the same packet rules.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final, NamedTuple, cast

if TYPE_CHECKING:
    from collections.abc import Mapping

CAPTURE_SCHEMA_VERSION = "assisted_delivery_capture.v1"
REQUIRED_SECTIONS = (
    "session",
    "mcp_surface",
    "planning",
    "blueprint",
    "handoff",
    "media",
    "decision",
)
REQUIRED_ACCEPTED_VERDICTS: Final = frozenset(
    (
        "accepted_as_generated",
        "accepted_after_repair",
        "rejected_with_reasons",
    )
)
FORBIDDEN_SCOPE_TERMS = (
    "Ax" + "iom",
    "GraphRAG",
    "Nerve",
    "TigerGraph",
    "Notion",
    "Life Engine",
)
FORBIDDEN_PATH_MARKERS = (
    ":\\",
    "/Users/",
    "/home/",
    "Desktop/Repositories",
    "source/repos",
)


class AssistedDeliveryCaptureValidation(NamedTuple):
    """Validation outcome for one manual assisted-delivery capture packet."""

    valid: bool
    errors: tuple[str, ...]
    blockers: tuple[str, ...]


def validate_assisted_delivery_capture(
    payload: Mapping[str, object],
) -> AssistedDeliveryCaptureValidation:
    """Validate the current-scope manual assisted-delivery capture shape.

    Returns:
        The validated value.
    """
    errors: list[str] = []
    blockers: list[str] = []
    _validate_schema(payload, errors)
    _validate_required_sections(payload, errors)
    _validate_forbidden_content(payload, errors)
    _validate_decision(payload, errors, blockers)
    return AssistedDeliveryCaptureValidation(
        valid=not errors,
        errors=tuple(errors),
        blockers=tuple(blockers),
    )


def _validate_schema(payload: Mapping[str, object], errors: list[str]) -> None:
    if payload.get("schema_version") != CAPTURE_SCHEMA_VERSION:
        errors.append(f"schema_version must be {CAPTURE_SCHEMA_VERSION!r}.")


def _validate_required_sections(
    payload: Mapping[str, object], errors: list[str]
) -> None:
    errors.extend(
        f"{section} must be an object."
        for section in REQUIRED_SECTIONS
        if not isinstance(payload.get(section), dict)
    )


def _validate_forbidden_content(
    payload: Mapping[str, object], errors: list[str]
) -> None:
    serialized = json.dumps(payload, sort_keys=True)
    normalized = serialized.casefold()
    forbidden_terms = [
        term for term in FORBIDDEN_SCOPE_TERMS if term.casefold() in normalized
    ]
    if forbidden_terms:
        errors.append(
            f"capture reintroduces obsolete scope terms: {forbidden_terms}."
        )
    forbidden_paths = [
        marker for marker in FORBIDDEN_PATH_MARKERS if marker in serialized
    ]
    if forbidden_paths:
        errors.append(
            f"capture contains hardcoded local path markers: {forbidden_paths}."
        )


def _validate_decision(
    payload: Mapping[str, object],
    errors: list[str],
    blockers: list[str],
) -> None:
    decision = _mapping(payload.get("decision"))
    session = _mapping(payload.get("session"))
    if decision is None or session is None:
        return
    accepted_verdicts = _accepted_verdicts(
        decision.get("accepted_verdicts"), errors
    )
    status = decision.get("status")
    if isinstance(status, str) and status not in accepted_verdicts:
        errors.append(
            f"decision.status is not accepted by this template: {status!r}."
        )
    if session.get("blocked") is True:
        blocker = session.get("blocker")
        if not isinstance(blocker, str) or not blocker.strip():
            errors.append("blocked captures must record session.blocker.")
        else:
            blockers.append(blocker)


def _mapping(value: object) -> Mapping[str, object] | None:
    return (
        cast("Mapping[str, object]", value) if isinstance(value, dict) else None
    )


def _accepted_verdicts(value: object, errors: list[str]) -> frozenset[str]:
    if not isinstance(value, list):
        errors.append("decision.accepted_verdicts must be a list of strings.")
        return frozenset()
    verdicts: list[str] = []
    for item in cast("list[object]", value):
        if not isinstance(item, str) or not item.strip():
            errors.append(
                "decision.accepted_verdicts must contain non-empty strings."
            )
            return frozenset()
        verdicts.append(item.strip())
    accepted = frozenset(verdicts)
    if not accepted:
        errors.append("decision.accepted_verdicts must not be empty.")
        return accepted
    missing = sorted(REQUIRED_ACCEPTED_VERDICTS - accepted)
    if missing:
        errors.append(
            f"decision.accepted_verdicts missing required verdicts: {missing}."
        )
    return accepted
