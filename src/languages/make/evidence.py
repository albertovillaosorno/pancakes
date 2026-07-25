# ruff: noqa: PLR0913
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001040#repo.runtime.target-modular-layout.bounded-contexts
# - 001060#repo.architecture.ports-adapters.boundary-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Internal Make-native evidence ledger helpers.

Boundary contract:
- Owns: compact private evidence rows for Make-native parity, diff, and
readiness judgments.
- Must not: call Make.com, store secrets, write artifacts, or embed evidence in
customer
  blueprints.
- Allows: internal debugging of false positives/negatives through opt-in MCP
debug output.
- Split when: evidence persistence becomes a separate storage service.
- Merge when: Make-native diff/export code owns the same ledger schema directly.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from blueprints.ast.models import JsonObject

MAKE_INTERNAL_EVIDENCE_SCHEMA_VERSION: Final = 1
MAKE_INTERNAL_EVIDENCE_VISIBILITY: Final = "internal"
MAKE_EVIDENCE_AVAILABLE_VISIBILITY: Final = "internal_available"
MAKE_EVIDENCE_SUPPORTED_TYPES: Final[frozenset[str]] = frozenset(
    (
        "canonicalizer_rule",
        "damp_lineage_test",
        "fixture_family",
        "make_reexport_evidence",
        "module_projector_manifest",
        "parity_confidence",
        "pass_through_unknown_module",
        "raw_spec_record",
        "risk_model_rule",
        "semantic_diff_category",
        "zero_trace_rule",
    )
)
MAKE_EVIDENCE_SECRET_MARKERS: Final[tuple[str, ...]] = (
    "access token",
    "access_token",
    "apikey",
    "api key",
    "authorization:",
    "bearer ",
    "client_secret",
    "credential value",
    "password",
    "private_key",
    "refresh_token",
    "secret",
)


def make_evidence_entry(
    *,
    evidence_type: str,
    judgment: str,
    source_id: str,
    rule_id: str | None = None,
    module: str | None = None,
    category: str | None = None,
    confidence: str | None = None,
    path: str | None = None,
    detail: Mapping[str, object] | None = None,
) -> JsonObject:
    """Return one validated internal evidence ledger entry."""
    evidence_type = _required_supported_text("evidence_type", evidence_type)
    entry: JsonObject = {
        "schema_version": MAKE_INTERNAL_EVIDENCE_SCHEMA_VERSION,
        "visibility": MAKE_INTERNAL_EVIDENCE_VISIBILITY,
        "evidence_type": evidence_type,
        "judgment": _required_safe_text("judgment", judgment),
        "source_id": _required_safe_text("source_id", source_id),
    }
    _set_optional_text(entry, "rule_id", rule_id)
    _set_optional_text(entry, "module", module)
    _set_optional_text(entry, "category", category)
    _set_optional_text(entry, "confidence", confidence)
    _set_optional_text(entry, "path", path)
    if detail is not None:
        entry["detail"] = _safe_json_mapping(detail)
    return entry


def make_internal_evidence_ledger(
    entries: Sequence[Mapping[str, object]],
) -> JsonObject:
    """Return one internal evidence ledger payload."""
    safe_entries = tuple(_safe_json_mapping(entry) for entry in entries)
    return {
        "schema_version": MAKE_INTERNAL_EVIDENCE_SCHEMA_VERSION,
        "visibility": MAKE_INTERNAL_EVIDENCE_VISIBILITY,
        "entry_count": len(safe_entries),
        "type_counts": _type_counts(safe_entries),
        "entries": safe_entries,
    }


def make_internal_evidence_availability(
    ledger: Mapping[str, object],
) -> JsonObject:
    """Return a public-safe signal that internal evidence exists."""
    entry_count = ledger.get("entry_count")
    if not isinstance(entry_count, int):
        entries = ledger.get("entries")
        if isinstance(entries, tuple | list):
            entry_count = len(cast("Sequence[object]", entries))
        else:
            entry_count = 0
    return {
        "schema_version": MAKE_INTERNAL_EVIDENCE_SCHEMA_VERSION,
        "visibility": MAKE_EVIDENCE_AVAILABLE_VISIBILITY,
        "available": entry_count > 0,
        "entry_count": entry_count,
        "contains_internal_details": False,
        "request_internal_details": (
            "Set include_internal_evidence=true for private debug output."
        ),
    }


def _type_counts(entries: Sequence[Mapping[str, object]]) -> JsonObject:
    counts = Counter(
        str(entry.get("evidence_type") or "unknown") for entry in entries
    )
    return dict(sorted(counts.items()))


def _required_supported_text(field: str, value: str) -> str:
    text = _required_safe_text(field, value)
    if text not in MAKE_EVIDENCE_SUPPORTED_TYPES:
        message = f"Unsupported Make evidence type: {text}"
        raise ValueError(message)
    return text


def _set_optional_text(
    entry: JsonObject, field: str, value: str | None
) -> None:
    if value is None:
        return
    text = _required_safe_text(field, value)
    if text:
        entry[field] = text


def _required_safe_text(field: str, value: object) -> str:
    if not isinstance(value, str):
        message = f"Evidence field {field} must be a string."
        raise TypeError(message)
    text = value.strip()
    if not text:
        message = f"Evidence field {field} must not be empty."
        raise ValueError(message)
    if _looks_secret_like(text):
        message = f"Evidence field {field} resembles secret-bearing material."
        raise ValueError(message)
    return text


def _safe_json_mapping(value: Mapping[str, object]) -> JsonObject:
    safe: JsonObject = {}
    for key, item in value.items():
        key_text = _required_safe_text("key", str(key))
        safe[key_text] = _safe_json_value(item)
    return safe


def _safe_json_value(value: object) -> object:
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return _required_safe_text("value", value)
    if isinstance(value, tuple | list):
        return tuple(
            _safe_json_value(item) for item in cast("Sequence[object]", value)
        )
    if isinstance(value, dict):
        return _safe_json_mapping(cast("Mapping[str, object]", value))
    message = f"Unsupported evidence value type: {type(value).__name__}"
    raise TypeError(message)


def _looks_secret_like(value: str) -> bool:
    normalized = value.casefold()
    return any(marker in normalized for marker in MAKE_EVIDENCE_SECRET_MARKERS)
