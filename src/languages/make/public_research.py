# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001040#repo.runtime.target-modular-layout.bounded-contexts
# - 001041#repo.make-scraper.raw-spec-refresh-policy
# - 001042#repo.make-catalog.catalog-only-fallback-utility
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Public Make research evidence ledger.

Boundary contract:
- Owns: compact public/sanitized source accounting for Make catalog research.
- Must not: call Make.com, store authenticated browser state, or
  promote customer payloads.
- Allows: offline lookup of evidence families, public source IDs, gates,
  and local surfaces.
- Split when: live Browser maintenance produces redacted generated
  evidence ledgers.
- Merge when: a broader Make evidence compiler owns every non-raw
  evidence surface.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple, TypeGuard, cast

if TYPE_CHECKING:
    from collections.abc import Mapping

JsonObject = dict[str, object]

PUBLIC_RESEARCH_EVIDENCE_ASSET: Final = "make_public_research_evidence"
PUBLIC_RESEARCH_EVIDENCE_PATH: Final = (
    Path(__file__).with_name("data") / "public_research_evidence.json"
)


class MakePublicResearchEvidenceRecord(NamedTuple):
    """One compact Make catalog research evidence family."""

    family_id: str
    title: str
    source_kinds: tuple[str, ...]
    public_source_ids: tuple[str, ...]
    local_surfaces: tuple[str, ...]
    ingestion_status: str
    promotion_gate: str
    live_browser_follow_up: str
    validation_tests: tuple[str, ...]


def load_make_public_research_evidence_payload() -> JsonObject:
    """Return the private Make public-research evidence payload.

    Raises:
        TypeError: If the payload is not a JSON object.
        ValueError: If the payload does not have the expected asset identifier.
    """
    payload = cast(
        "object",
        json.loads(PUBLIC_RESEARCH_EVIDENCE_PATH.read_text(encoding="utf-8")),
    )
    if not _is_json_object(payload):
        prefix = "Expected public Make research evidence object"
        message = f"{prefix}: {PUBLIC_RESEARCH_EVIDENCE_PATH}"
        raise TypeError(message)
    if payload.get("asset") != PUBLIC_RESEARCH_EVIDENCE_ASSET:
        message = (
            f"Unexpected public Make research asset: {payload.get('asset')!r}"
        )
        raise ValueError(message)
    return payload


def make_public_research_evidence_records() -> tuple[
    MakePublicResearchEvidenceRecord, ...
]:
    """Return compact public Make research evidence records in source order."""
    payload = load_make_public_research_evidence_payload()
    return tuple(
        _record_from_payload(record)
        for record in _json_object_list(
            payload.get("records"), member_name="records"
        )
    )


def make_public_research_evidence_record(
    family_id: str,
) -> MakePublicResearchEvidenceRecord | None:
    """Return one public Make research evidence record by family ID."""
    normalized = family_id.casefold().strip()
    for record in make_public_research_evidence_records():
        if record.family_id.casefold() == normalized:
            return record
    return None


def make_public_research_source_ids() -> tuple[str, ...]:
    """Return official/public source IDs retained by the compact ledger."""
    payload = load_make_public_research_evidence_payload()
    sources = _json_object_list(
        payload.get("public_sources"), member_name="public_sources"
    )
    return tuple(_required_text(source, "source_id") for source in sources)


def _record_from_payload(
    payload: JsonObject,
) -> MakePublicResearchEvidenceRecord:
    return MakePublicResearchEvidenceRecord(
        family_id=_required_text(payload, "family_id"),
        title=_required_text(payload, "title"),
        source_kinds=_required_text_list(payload, "source_kinds"),
        public_source_ids=_required_text_list(payload, "public_source_ids"),
        local_surfaces=_required_text_list(payload, "local_surfaces"),
        ingestion_status=_required_text(payload, "ingestion_status"),
        promotion_gate=_required_text(payload, "promotion_gate"),
        live_browser_follow_up=_required_text(
            payload, "live_browser_follow_up"
        ),
        validation_tests=_required_text_list(payload, "validation_tests"),
    )


def _json_object_list(
    value: object, *, member_name: str
) -> tuple[JsonObject, ...]:
    if not isinstance(value, list):
        message = (
            f"Expected list at Make public research member {member_name!r}."
        )
        raise TypeError(message)
    items: list[JsonObject] = []
    for item in cast("list[object]", value):
        if not _is_json_object(item):
            prefix = "Expected object in Make public research member"
            message = f"{prefix} {member_name!r}."
            raise TypeError(message)
        items.append(item)
    return tuple(items)


def _required_text(payload: JsonObject, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        message = f"Missing Make public research text field {key!r}."
        raise ValueError(message)
    return value.strip()


def _required_text_list(payload: JsonObject, key: str) -> tuple[str, ...]:
    raw = payload.get(key)
    if not isinstance(raw, list):
        message = f"Expected list at Make public research field {key!r}."
        raise TypeError(message)
    values: list[str] = []
    for item in cast("list[object]", raw):
        if not isinstance(item, str) or not item.strip():
            prefix = "Expected non-empty string at Make research field"
            message = f"{prefix} {key!r}."
            raise TypeError(message)
        values.append(item.strip())
    return tuple(values)


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    if not isinstance(value, dict):
        return False
    raw = cast("Mapping[object, object]", value)
    return all(isinstance(key, str) for key in raw)
