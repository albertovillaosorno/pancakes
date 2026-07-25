# ruff: noqa: S105
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001046#repo.blueprint-validation.semantic-module-usage-rules
# - 001079#repo.make-linter.rule-intake-manual-gate
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Validate deterministic sensitive-content hazards in Make metadata notes.

Boundary contract:
- Owns: local note-content checks for static personal identifier and secret
literals.
- Must not: classify real customer data, infer account ownership, parse linter
  suppressions, or call services.
- Allows: deterministic scans over root and module metadata notes with redacted
findings.
- Split when: note rendering or provider-specific customer-data policy needs
richer state.
- Merge when: another validation slice owns the same note-content security
predicate.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final, TypeGuard, cast

from blueprints.validation.findings import build_validation_finding

if TYPE_CHECKING:
    from blueprints.ast.models import (
        AstPathPart,
        JsonObject,
        MakeAstNode,
        MakeAstRoot,
    )
    from blueprints.validation.models import BlueprintValidationFinding

NOTES_STATIC_PERSONAL_LITERAL_CODE: Final = "notes.static_personal_literal"
NOTES_STATIC_SECRET_LITERAL_CODE: Final = "notes.static_secret_literal"
NOTES_INSECURE_LINK_LITERAL_CODE: Final = "notes.insecure_link_literal"
NOTES_INTERNAL_LINTER_MARKER_CODE: Final = "notes.internal_linter_marker"
NOTE_CONTENT_KEYS: Final[tuple[str, ...]] = ("content", "html", "text")
SAFE_SECRET_PLACEHOLDER_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "changeme ",
        "dummy ",
        "example ",
        "placeholder ",
        "redacted ",
        "sample",
    )
)
EMAIL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)
PHONE_LIKE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?<![\w])(?:\+?\d[\d .()/-]{8,}\d)(?![\w])"
)
SECRET_VALUE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
    ),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
)
LINK_SCHEME_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*):(?://|[A-Za-z0-9+/=,%._~#?&-]+)",
    re.IGNORECASE,
)
INTERNAL_RULE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b[A-Z]{3}-\d{3}\b"
)
INTERNAL_LINTER_MARKERS: Final[tuple[str, ...]] = (
    "candidate id ",
    "candidate_id ",
    "corpus count ",
    "corpus_count ",
    "deterministic predicate ",
    "linter predicate ",
    "predicate:",
    "rule corpus ",
    "rule-corpus",
)
MIN_PHONE_DIGITS: Final = 10


def validate_note_content_security(
    *,
    root: MakeAstRoot,
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Return deterministic note-content security findings."""
    findings: list[BlueprintValidationFinding] = []
    findings.extend(
        _note_container_findings(
            value=root.scenario.metadata.get("notes"),
            node_id=None,
            path=("metadata", "notes"),
        )
    )
    for node in nodes:
        metadata = node.raw_payload.get("metadata")
        if not _is_json_object(metadata):
            continue
        findings.extend(
            _note_container_findings(
                value=metadata.get("notes"),
                node_id=node.node_id,
                path=(*node.source_trace.path, "metadata", "notes"),
            )
        )
    return tuple(findings)


def _note_container_findings(
    *,
    value: object,
    node_id: str | None,
    path: tuple[AstPathPart, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    if not isinstance(value, list):
        return ()
    findings: list[BlueprintValidationFinding] = []
    for index, item in enumerate(cast("list[object]", value)):
        if not _is_json_object(item):
            continue
        note_path = (*path, index)
        for key in NOTE_CONTENT_KEYS:
            content = item.get(key)
            if isinstance(content, str) and _static_personal_literal(content):
                findings.append(
                    build_validation_finding(
                        code=NOTES_STATIC_PERSONAL_LITERAL_CODE,
                        severity="warning",
                        node=(node_id, (*note_path, key)),
                        catalog_module_id=None,
                        messages=(
                            (
                                "A metadata note contains static personal "
                                "identifier text."
                            ),
                            (
                                "Note content contains email-like or "
                                "phone-like "
                                "text; "
                                "raw values are redacted."
                            ),
                        ),
                    )
                )
            if isinstance(content, str) and _static_secret_literal(content):
                findings.append(
                    build_validation_finding(
                        code=NOTES_STATIC_SECRET_LITERAL_CODE,
                        severity="warning",
                        node=(node_id, (*note_path, key)),
                        catalog_module_id=None,
                        messages=(
                            "A metadata note contains static secret-like text.",
                            (
                                "Note content contains secret-like text; raw "
                                "values "
                                "are redacted."
                            ),
                        ),
                    )
                )
            if isinstance(content, str) and _insecure_link_literal(content):
                findings.append(
                    build_validation_finding(
                        code=NOTES_INSECURE_LINK_LITERAL_CODE,
                        severity="warning",
                        node=(node_id, (*note_path, key)),
                        catalog_module_id=None,
                        messages=(
                            (
                                "A metadata note contains a non-HTTPS link "
                                "literal."
                            ),
                            (
                                "Note content contains an insecure or local "
                                "link scheme; "
                                "raw values are redacted."
                            ),
                        ),
                    )
                )
            if isinstance(content, str) and _internal_linter_marker(content):
                findings.append(
                    build_validation_finding(
                        code=NOTES_INTERNAL_LINTER_MARKER_CODE,
                        severity="warning",
                        node=(node_id, (*note_path, key)),
                        catalog_module_id=None,
                        messages=(
                            (
                                "A metadata note contains internal linter "
                                "mechanics."
                            ),
                            (
                                "Note content references internal rule IDs or "
                                "predicate "
                                "mechanics; raw values are redacted."
                            ),
                        ),
                    )
                )
    return tuple(findings)


def _static_personal_literal(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return False
    return EMAIL_PATTERN.search(
        stripped
    ) is not None or _contains_phone_like_value(stripped)


def _contains_phone_like_value(value: str) -> bool:
    for match in PHONE_LIKE_PATTERN.finditer(value):
        digits = "".join(
            character for character in match.group(0) if character.isdigit()
        )
        if len(digits) >= MIN_PHONE_DIGITS:
            return True
    return False


def _static_secret_literal(value: str) -> bool:
    stripped = value.strip()
    if not stripped or "{{" in stripped or "}}" in stripped:
        return False
    if _safe_secret_placeholder(stripped):
        return False
    return any(
        pattern.search(stripped) is not None
        for pattern in SECRET_VALUE_PATTERNS
    )


def _insecure_link_literal(value: str) -> bool:
    stripped = value.strip()
    if not stripped or "{{" in stripped or "}}" in stripped:
        return False
    for match in LINK_SCHEME_PATTERN.finditer(stripped):
        scheme = match.group("scheme").casefold()
        if scheme != "https":
            return True
    return False


def _internal_linter_marker(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return False
    if INTERNAL_RULE_ID_PATTERN.search(stripped) is not None:
        return True
    normalized = stripped.casefold().replace("\\", "/")
    return any(marker in normalized for marker in INTERNAL_LINTER_MARKERS)


def _safe_secret_placeholder(value: str) -> bool:
    normalized = "".join(
        character for character in value.casefold() if character.isalnum()
    )
    return normalized in SAFE_SECRET_PLACEHOLDER_TOKENS


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    if not isinstance(value, dict):
        return False
    raw_mapping = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in raw_mapping)
