# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001042#repo.make-catalog.schema-policy
# - 001061#repo.delivery.claims.exact-dynamic-surface-only
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Offline catalog generation audit summaries.

Boundary contract:
- Owns: read-only audit summaries for catalog-backed generation candidates.
- Must not: generate blueprints, call providers, validate raw specs, or perform
IO.
- Allows: deterministic counts, status labels, and shadow event records.
- Split when: audits need external evidence, rendering, or mutation decisions.
- Merge when: another audit module reports the same catalog generation summary.
"""

from __future__ import annotations

from itertools import starmap
from typing import TYPE_CHECKING, NamedTuple, Protocol, cast

if TYPE_CHECKING:
    from catalog.models import CatalogModule, CatalogSnapshot

REDACTED_CREDENTIAL: str = "[redacted:credential]"
REDACTED_PLACEHOLDER: str = "[redacted:placeholder]"
SECRET_FIELD_MARKERS: tuple[str, ...] = (
    "access_token ",
    "api_key ",
    "api_token ",
    "authorization ",
    "bearer ",
    "credential ",
    "password ",
    "secret",
)
PLACEHOLDER_MARKERS: tuple[str, ...] = ("{{", "__todo__", "<todo", "todo:")
MAX_TELEMETRY_VALUE_LENGTH = 240


class CatalogPlanShadowEntry(NamedTuple):
    """One local shadow telemetry event for catalog-backed planning.

    decisions.
    """

    sequence: int
    source: str
    decision: str
    rule: str
    outcome: str
    inputs: tuple[tuple[str, object], ...]
    provenance: tuple[tuple[str, object], ...] = ()


class CatalogPlanShadowSink(Protocol):
    """Injected sink for local shadow telemetry events."""

    def record_shadow_event(self, event: CatalogPlanShadowEntry) -> None:
        """Record one local shadow telemetry event."""
        ...


class InMemoryCatalogPlanShadowSink:
    """Test-only in-memory sink for local shadow telemetry events."""

    def __init__(self) -> None:
        """Initialize an empty in-memory event buffer."""
        self._events: list[CatalogPlanShadowEntry] = []

    @property
    def events(self) -> tuple[CatalogPlanShadowEntry, ...]:
        """Return recorded events in deterministic insertion order."""
        return tuple(self._events)

    def record_shadow_event(self, event: CatalogPlanShadowEntry) -> None:
        """Record one local shadow telemetry event."""
        self._events.append(event._replace(sequence=len(self._events)))


def emit_catalog_plan_shadow_event(
    sink: CatalogPlanShadowSink | None,
    event: CatalogPlanShadowEntry,
) -> None:
    """Emit one local shadow event when a sink is explicitly supplied."""
    if sink is None:
        return
    sink.record_shadow_event(_redacted_shadow_event(event))


def _redacted_shadow_event(
    event: CatalogPlanShadowEntry,
) -> CatalogPlanShadowEntry:
    """Return one event with secret-safe field values."""
    return CatalogPlanShadowEntry(
        sequence=event.sequence,
        source=event.source,
        decision=event.decision,
        rule=event.rule,
        outcome=event.outcome,
        inputs=tuple(starmap(catalog_plan_shadow_field, event.inputs)),
        provenance=tuple(starmap(catalog_plan_shadow_field, event.provenance)),
    )


def catalog_plan_shadow_field(key: str, value: object) -> tuple[str, str]:
    """Return one redacted shadow telemetry field."""
    return (key, redact_catalog_plan_shadow_value(key=key, value=value))


def redact_catalog_plan_shadow_value(*, key: str, value: object) -> str:
    """Return a deterministic, secret-safe telemetry field value."""
    text = _telemetry_text(value)
    if _is_secret_field(key) or _looks_like_credential(text):
        return REDACTED_CREDENTIAL
    if _looks_like_placeholder(text):
        return REDACTED_PLACEHOLDER
    if len(text) > MAX_TELEMETRY_VALUE_LENGTH:
        overflow = len(text) - MAX_TELEMETRY_VALUE_LENGTH
        return f"{text[:MAX_TELEMETRY_VALUE_LENGTH]}...[truncated:{overflow}]"
    return text


class CatalogGenerationAuditEntry(NamedTuple):
    """One audited catalog module surface."""

    module_id: str
    app_slug: str
    module_kind: str
    deprecated: bool
    required_parameter_count: int
    rpc_dependency_count: int
    status: str


class CatalogGenerationAuditBlocker(NamedTuple):
    """One hard blocker for requested catalog generation."""

    requested_module_id: str
    code: str
    severity: str
    blocking: bool
    message: str


class CatalogGenerationAuditReport(NamedTuple):
    """Offline audit over catalog-backed generation candidates."""

    catalog_fingerprint: str
    status: str
    requested_module_count: int
    audited_module_count: int
    deprecated_module_count: int
    dynamic_selector_module_count: int
    malformed_raw_spec_count: int
    blocker_count: int
    entries: tuple[CatalogGenerationAuditEntry, ...]
    blockers: tuple[CatalogGenerationAuditBlocker, ...]


def build_catalog_generation_audit(
    *,
    snapshot: CatalogSnapshot,
    requested_module_ids: tuple[str, ...] = (),
) -> CatalogGenerationAuditReport:
    """Return an offline generation audit over catalog module IDs."""
    modules = _selected_modules(snapshot, requested_module_ids)
    entries = tuple(_entry(module) for module in modules)
    blockers = _missing_module_blockers(
        requested_module_ids=requested_module_ids,
        entries=entries,
    )
    return CatalogGenerationAuditReport(
        catalog_fingerprint=snapshot.fingerprint,
        status="blocked" if blockers else "ok",
        requested_module_count=len(requested_module_ids) or len(modules),
        audited_module_count=len(entries),
        deprecated_module_count=sum(1 for entry in entries if entry.deprecated),
        dynamic_selector_module_count=sum(
            1 for entry in entries if entry.rpc_dependency_count > 0
        ),
        malformed_raw_spec_count=sum(
            1
            for diagnostic in snapshot.diagnostics
            if diagnostic.code == "raw_spec.module_collection_empty"
        ),
        blocker_count=len(blockers),
        entries=entries,
        blockers=blockers,
    )


def _selected_modules(
    snapshot: CatalogSnapshot,
    requested_module_ids: tuple[str, ...],
) -> tuple[CatalogModule, ...]:
    """Return requested modules or the full catalog."""
    modules = _catalog_modules(snapshot)
    if not requested_module_ids:
        return modules
    requested = set(requested_module_ids)
    return tuple(module for module in modules if module.module_id in requested)


def _catalog_modules(snapshot: CatalogSnapshot) -> tuple[CatalogModule, ...]:
    """Return all catalog modules in deterministic order."""
    return tuple(
        sorted(
            (
                module
                for app in snapshot.apps
                for version in app.versions
                for module in version.modules
            ),
            key=lambda module: module.module_id,
        )
    )


def _entry(module: CatalogModule) -> CatalogGenerationAuditEntry:
    """Return one audit entry."""
    return CatalogGenerationAuditEntry(
        module_id=module.module_id,
        app_slug=module.app_slug,
        module_kind=module.module_kind,
        deprecated=module.deprecated,
        required_parameter_count=sum(
            1 for field in module.parameters if field.required
        ),
        rpc_dependency_count=len(module.rpc_dependencies),
        status="deprecated" if module.deprecated else "catalog_backed",
    )


def _missing_module_blockers(
    *,
    requested_module_ids: tuple[str, ...],
    entries: tuple[CatalogGenerationAuditEntry, ...],
) -> tuple[CatalogGenerationAuditBlocker, ...]:
    """Return hard blockers for requested module IDs that are absent from the.

    catalog.
    """
    if not requested_module_ids:
        return ()
    audited_module_ids = {entry.module_id for entry in entries}
    blockers: list[CatalogGenerationAuditBlocker] = []
    seen_missing: set[str] = set()
    for requested_module_id in requested_module_ids:
        if (
            requested_module_id in audited_module_ids
            or requested_module_id in seen_missing
        ):
            continue
        seen_missing.add(requested_module_id)
        blockers.append(
            CatalogGenerationAuditBlocker(
                requested_module_id=requested_module_id,
                code="catalog.module_missing",
                severity="error",
                blocking=True,
                message=(
                    "Requested module is not present in the local Make "
                    "catalog; "
                    ""
                    "offline generation cannot use this module without catalog "
                    "evidence."
                ),
            )
        )
    return tuple(blockers)


def _telemetry_text(value: object) -> str:
    if value is None:
        return "none"
    if isinstance(value, tuple):
        tuple_value = cast("tuple[object, ...]", value)
        return ".".join(_telemetry_text(item) for item in tuple_value)
    if isinstance(value, list):
        list_value = cast("list[object]", value)
        return ".".join(_telemetry_text(item) for item in list_value)
    return str(value)


def _is_secret_field(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return any(marker in normalized for marker in SECRET_FIELD_MARKERS)


def _looks_like_credential(value: str) -> bool:
    normalized = value.casefold()
    return any(
        marker in normalized
        for marker in ("bearer ", "authorization:", "api_key=")
    )


def _looks_like_placeholder(value: str) -> bool:
    normalized = value.casefold()
    return any(marker in normalized for marker in PLACEHOLDER_MARKERS)
