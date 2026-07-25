# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 001040#repo.runtime.target-modular-layout.bounded-contexts
# - 001041#repo.make-scraper.raw-spec-refresh-policy
# - 001042#repo.make-catalog.catalog-only-fallback-utility
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Priority Make module-family metadata.

Boundary contract:
- Owns: private priority connector names, slug aliases, and local raw-spec
coverage posture.
- Must not: call Make.com, store credentials, infer dynamic RPC behavior, or
generate projectors.
- Allows: catalog scoring aliases, coverage tests, and offline planner
diagnostics.
- Split when: browser-confirmed dynamic RPC contracts become a separate
generated manifest.
- Merge when: another Make module owns the same priority connector registry.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, TypeGuard, cast

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from languages.make.raw_specs.models import RawSpecManifest, RawSpecRecord

JsonObject = dict[str, object]
PriorityMakeModuleFamilyStatus = Literal["catalog_badge", "module_family"]
PriorityMakeModuleFamilyTier = Literal["absolute", "badge", "standard"]

PRIORITY_MODULE_FAMILIES_ASSET: Final = "make_priority_module_families"
PRIORITY_MODULE_FAMILIES_PATH: Final = (
    Path(__file__).with_name("data") / "priority_module_families.json"
)


class PriorityMakeModuleFamily(NamedTuple):
    """One priority Make connector family from the operator backlog."""

    label: str
    status: PriorityMakeModuleFamilyStatus
    priority: PriorityMakeModuleFamilyTier
    app_slugs: tuple[str, ...]
    aliases: tuple[str, ...]
    source_occurrences: int = 1


class PriorityMakeModuleCoverage(NamedTuple):
    """Local raw-spec coverage posture for one priority family."""

    label: str
    status: PriorityMakeModuleFamilyStatus
    priority: PriorityMakeModuleFamilyTier
    app_slugs: tuple[str, ...]
    covered_app_slugs: tuple[str, ...]
    missing_app_slugs: tuple[str, ...]
    latest_versions: tuple[str, ...]
    module_count: int
    module_kinds: tuple[str, ...]
    coverage_status: str


def load_priority_make_module_family_payload() -> JsonObject:
    """Return the private priority Make module family payload.

    Raises:
        TypeError: If the payload is not a JSON object.
        ValueError: If the asset identifier does not match this loader.
    """
    payload = cast(
        "object",
        json.loads(PRIORITY_MODULE_FAMILIES_PATH.read_text(encoding="utf-8")),
    )
    if not _is_json_object(payload):
        message = (
            f"Expected priority module family object:"
            f"{PRIORITY_MODULE_FAMILIES_PATH}"
        )
        raise TypeError(message)
    if payload.get("asset") != PRIORITY_MODULE_FAMILIES_ASSET:
        message = (
            f"Unexpected priority module family asset: {payload.get('asset')!r}"
        )
        raise ValueError(message)
    return payload


def iter_priority_make_module_families() -> tuple[
    PriorityMakeModuleFamily, ...
]:
    """Return priority connector families in operator source order."""
    payload = load_priority_make_module_family_payload()
    records = _json_object_list(payload.get("records"), member_name="records")
    return tuple(_family_from_payload(record) for record in records)


def priority_make_app_search_terms(app_slug: str) -> tuple[str, ...]:
    """Return the computed result for the caller."""
    normalized = app_slug.casefold().strip()
    terms: list[str] = []
    for family in iter_priority_make_module_families():
        if (
            family.status != "module_family"
            or normalized not in family.app_slugs
        ):
            continue
        terms.append(family.label)
        terms.extend(family.aliases)
    return _dedupe(terms)


def priority_make_module_coverage(
    manifest: RawSpecManifest,
) -> tuple[PriorityMakeModuleCoverage, ...]:
    """Return local raw-spec coverage for every priority connector family."""
    records_by_slug: dict[str, tuple[RawSpecRecord, ...]] = {}
    for app_slug in _all_priority_app_slugs():
        matching = tuple(
            record for record in manifest.records if record.app_slug == app_slug
        )
        if matching:
            records_by_slug[app_slug] = matching

    coverage: list[PriorityMakeModuleCoverage] = []
    for family in iter_priority_make_module_families():
        if family.status == "catalog_badge":
            coverage.append(_badge_coverage(family))
            continue
        covered = tuple(
            slug for slug in family.app_slugs if slug in records_by_slug
        )
        missing = tuple(
            slug for slug in family.app_slugs if slug not in records_by_slug
        )
        records = tuple(
            record
            for slug in covered
            for record in records_by_slug.get(slug, ())
            if record.latest
        )
        coverage.append(
            PriorityMakeModuleCoverage(
                label=family.label,
                status=family.status,
                priority=family.priority,
                app_slugs=family.app_slugs,
                covered_app_slugs=covered,
                missing_app_slugs=missing,
                latest_versions=tuple(
                    f"{record.app_slug}@{record.app_version}"
                    for record in records
                ),
                module_count=sum(record.module_count for record in records),
                module_kinds=_dedupe(
                    kind for record in records for kind in record.module_kinds
                ),
                coverage_status="raw_spec_backed"
                if covered
                else "raw_spec_missing",
            )
        )
    return tuple(coverage)


def _family_from_payload(payload: JsonObject) -> PriorityMakeModuleFamily:
    status = _required_status(payload, "status")
    priority = _required_priority(payload, "priority")
    source_occurrences = _positive_int(
        payload.get("source_occurrences"), default=1
    )
    return PriorityMakeModuleFamily(
        label=_required_text(payload, "label"),
        status=status,
        priority=priority,
        app_slugs=_optional_text_list(payload, "app_slugs"),
        aliases=_optional_text_list(payload, "aliases"),
        source_occurrences=source_occurrences,
    )


def _badge_coverage(
    family: PriorityMakeModuleFamily,
) -> PriorityMakeModuleCoverage:
    return PriorityMakeModuleCoverage(
        label=family.label,
        status=family.status,
        priority=family.priority,
        app_slugs=family.app_slugs,
        covered_app_slugs=(),
        missing_app_slugs=(),
        latest_versions=(),
        module_count=0,
        module_kinds=(),
        coverage_status="not_a_module_family",
    )


def _all_priority_app_slugs() -> tuple[str, ...]:
    return _dedupe(
        slug
        for family in iter_priority_make_module_families()
        for slug in family.app_slugs
    )


def _json_object_list(
    value: object, *, member_name: str
) -> tuple[JsonObject, ...]:
    if not isinstance(value, list):
        message = (
            f"Expected list at priority module family member {member_name!r}."
        )
        raise TypeError(message)
    items: list[JsonObject] = []
    for item in cast("list[object]", value):
        if not _is_json_object(item):
            message = (
                f"Expected object in priority module family member"
                f"{member_name!r}."
            )
            raise TypeError(message)
        items.append(item)
    return tuple(items)


def _required_text(payload: JsonObject, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        message = f"Missing priority module family text field {key!r}."
        raise ValueError(message)
    return value.strip()


def _required_status(
    payload: JsonObject, key: str
) -> PriorityMakeModuleFamilyStatus:
    value = _required_text(payload, key)
    if value not in {"catalog_badge", "module_family"}:
        message = f"Unsupported priority module family status {value!r}."
        raise ValueError(message)
    return cast("PriorityMakeModuleFamilyStatus", value)


def _required_priority(
    payload: JsonObject, key: str
) -> PriorityMakeModuleFamilyTier:
    value = _required_text(payload, key)
    if value not in {"absolute", "badge", "standard"}:
        message = f"Unsupported priority module family tier {value!r}."
        raise ValueError(message)
    return cast("PriorityMakeModuleFamilyTier", value)


def _optional_text_list(payload: JsonObject, key: str) -> tuple[str, ...]:
    raw = payload.get(key)
    if raw is None:
        return ()
    if not isinstance(raw, list):
        message = f"Expected list at priority module family field {key!r}."
        raise TypeError(message)
    values: list[str] = []
    for item in cast("list[object]", raw):
        if not isinstance(item, str):
            message = (
                f"Expected string at priority module family field {key!r}."
            )
            raise TypeError(message)
        text = item.strip()
        if text:
            values.append(text)
    return tuple(values)


def _positive_int(value: object, *, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        message = (
            "Priority module family source_occurrences must be a positive"
            "integer."
        )
        raise TypeError(message)
    return value


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        key = value.casefold().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return tuple(deduped)


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    if not isinstance(value, dict):
        return False
    raw = cast("Mapping[object, object]", value)
    return all(isinstance(key, str) for key in raw)
