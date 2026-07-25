# ruff: noqa: E501
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001046#repo.blueprint-validation.validator-policy
# - 001060#repo.architecture.srp.extreme-one-responsibility
# - 001063#repo.architecture.file-boundary.contract-required
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Validation finding construction helpers.

Boundary contract:
- Owns: normalized BlueprintValidationFinding construction and message safety.
- Must not: decide validation rules, scan AST nodes, or inspect catalog records.
- Allows: typed finding fields and deterministic client-message path checks.
- Split when: finding IDs, message safety, or render formats evolve separately.
- Merge when: another module duplicates the same finding construction contract.
"""

from __future__ import annotations

import hashlib
from typing import Final, NamedTuple

from blueprints.validation.models import (
    BlueprintFindingSeverity,
    BlueprintValidationFinding,
)

CLIENT_PATH_TOKENS: Final[tuple[str, ...]] = (
    "\\",
    "/",
    "src/",
    "tests/",
    "Refactor",
    "C:",
)


class FindingIdentity(NamedTuple):
    """Data used to derive a stable validation finding ID."""

    code: str
    severity: BlueprintFindingSeverity
    node_id: str | None
    source_path: tuple[str | int, ...]
    catalog_module_id: str | None
    internal_message: str


class ValidationPattern(NamedTuple):
    """Stable identity for a recurrent validation failure shape."""

    pattern_id: str
    codes: tuple[str, ...]
    description: str
    suggested_fix: str


PATTERN_ROUTES_ON_NON_ROUTER: Final = "routes-on-non-router"
PATTERN_MISSING_ROUTER_FANOUT: Final = "missing-router-fanout"
PATTERN_UNRESOLVED_PLACEHOLDER: Final = "unresolved-placeholder"
PATTERN_MALFORMED_NOTE: Final = "malformed-note"
PATTERN_INVALID_FILTER_EXPRESSION: Final = "invalid-filter-expression"
PATTERN_METADATA_RESTORE_SHAPE: Final = "metadata-restore-shape"

ROUTES_ON_NON_ROUTER_CODE: Final = "route.routes_on_non_router"
MISSING_ROUTER_FANOUT_CODE: Final = "router.routes_missing"
UNRESOLVED_PLACEHOLDER_CODE: Final = "importability.placeholder_unresolved"
MALFORMED_NOTE_CODE: Final = "ast.note_invalid"
INVALID_FILTER_EXPRESSION_CODE: Final = "filter.empty_conditions"
METADATA_RESTORE_SHAPE_CODE: Final = "importability.metadata_invalid"
AST_METADATA_INVALID_CODE: Final = "ast.metadata_invalid"

VALIDATION_PATTERNS: Final[tuple[ValidationPattern, ...]] = (
    ValidationPattern(
        pattern_id=PATTERN_ROUTES_ON_NON_ROUTER,
        codes=(ROUTES_ON_NON_ROUTER_CODE,),
        description="A non-router module contains a Make route container.",
        suggested_fix=(
            "Move the route container under a BasicRouter node or normalize it "
            "into "
            "a plain child flow."
        ),
    ),
    ValidationPattern(
        pattern_id=PATTERN_MISSING_ROUTER_FANOUT,
        codes=(MISSING_ROUTER_FANOUT_CODE,),
        description="A router node has no route fanout.",
        suggested_fix=(
            "Add at least one route flow under the router before importable"
            "handoff."
        ),
    ),
    ValidationPattern(
        pattern_id=PATTERN_UNRESOLVED_PLACEHOLDER,
        codes=(UNRESOLVED_PLACEHOLDER_CODE,),
        description=(
            "A blueprint field still contains a handoff placeholder token."
        ),
        suggested_fix=(
            "Replace the placeholder with a client-provided value or register "
            "it "
            "in the handoff placeholder manifest."
        ),
    ),
    ValidationPattern(
        pattern_id=PATTERN_MALFORMED_NOTE,
        codes=(
            MALFORMED_NOTE_CODE,
            "ast.notes_invalid ",
            "ast.note_module_ids_invalid ",
            "ast.note_module_id_invalid ",
            "ast.note_module_id_unknown",
        ),
        description=(
            "Make-native metadata notes do not match the expected object shape."
        ),
        suggested_fix=(
            "Represent each note as an object with valid content and moduleIds"
            "anchors."
        ),
    ),
    ValidationPattern(
        pattern_id=PATTERN_INVALID_FILTER_EXPRESSION,
        codes=(INVALID_FILTER_EXPRESSION_CODE,),
        description=(
            "A route filter does not expose executable condition content."
        ),
        suggested_fix=(
            "Add a non-empty Make filter condition, rule, or expression to the"
            "route."
        ),
    ),
    ValidationPattern(
        pattern_id=PATTERN_METADATA_RESTORE_SHAPE,
        codes=(METADATA_RESTORE_SHAPE_CODE, AST_METADATA_INVALID_CODE),
        description=(
            "Metadata used for restore or import compatibility has an invalid "
            "container shape."
        ),
        suggested_fix=(
            "Keep metadata as a JSON object before validation, rendering, or"
            "handoff."
        ),
    ),
)
VALIDATION_PATTERN_IDS: Final[frozenset[str]] = frozenset(
    pattern.pattern_id for pattern in VALIDATION_PATTERNS
)
_VALIDATION_PATTERN_BY_CODE: Final[dict[str, ValidationPattern]] = {
    code: pattern for pattern in VALIDATION_PATTERNS for code in pattern.codes
}


def build_validation_finding(
    *,
    code: str,
    severity: BlueprintFindingSeverity,
    node: tuple[str | None, tuple[str | int, ...]],
    catalog_module_id: str | None,
    messages: tuple[str, str],
) -> BlueprintValidationFinding:
    """Build one finding and enforce client-safe message text.

    Returns:
        The constructed value.

    Raises:
        ValueError: If an input value violates the documented contract.
    """
    node_id, source_path = node
    client_message, internal_message = messages
    if any(token in client_message for token in CLIENT_PATH_TOKENS):
        message = (
            "Client validation message is not path-safe; raw client message "
            "is redacted."
        )
        raise ValueError(message)
    finding_id = _finding_id(
        FindingIdentity(
            code=code,
            severity=severity,
            node_id=node_id,
            source_path=source_path,
            catalog_module_id=catalog_module_id,
            internal_message=internal_message,
        )
    )
    return BlueprintValidationFinding(
        finding_id=finding_id,
        severity=severity,
        code=code,
        node_id=node_id,
        client_message=client_message,
        internal_message=internal_message,
        catalog_module_id=catalog_module_id,
        source_path=source_path,
    )


def validation_pattern_for_code(code: str) -> ValidationPattern | None:
    """Return the recurrent failure pattern for one finding code, if known."""
    return _VALIDATION_PATTERN_BY_CODE.get(code)


def validation_pattern_for_finding(
    finding: BlueprintValidationFinding,
) -> ValidationPattern | None:
    """Return the recurrent failure pattern for one validation finding, if.

    known.
    """
    return validation_pattern_for_code(finding.code)


def _finding_id(identity: FindingIdentity) -> str:
    """Return a stable finding ID for one finding identity."""
    fingerprint = hashlib.sha256(
        repr(
            (
                identity.source_path,
                identity.catalog_module_id,
                identity.internal_message,
            )
        ).encode("utf-8")
    ).hexdigest()[:12]
    return f"{identity.severity}:{identity.code}:{identity.node_id or 'root'}:{fingerprint}"
