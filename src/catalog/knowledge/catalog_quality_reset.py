# ruff: noqa: S608
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001064#repo.make-knowledge.structural-ssot
# - repo.catalog-plan-artifact.workspace-boundary
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end
# pyright: reportAny=false

"""Canonical catalog run helpers for the Make knowledge SQLite database.

Boundary contract:
- Owns: active catalog run seeding, priority ordering, notes, and progress
summaries.
- Must not: author semantic catalog answers, call providers, or inspect live
Make accounts.
- Allows: synthetic or local source manifests that describe future catalog work
units.
- Split when: lease-based catalog worker mutation tools become their own runtime
surface.
- Merge when: another module owns the same active canonical catalog contract.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Final, NamedTuple, cast

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterable

CATALOG_RESET_STRATEGY: Final = "canonical_catalog"
CATALOG_RUN_STATUS_ACTIVE: Final = "active"
CATALOG_RUN_STATUS_SUPERSEDED: Final = "superseded_obsolete_evidence"
CATALOG_OLD_SEMANTIC_STATUS: Final = "archived_obsolete_evidence"
CATALOG_INCOMPLETE_COVERAGE_POLICY: Final = "explicit_non_blocking"
CATALOG_UNIT_STATUS_QUEUED: Final = "queued"
CATALOG_UNIT_VALIDATION_PENDING: Final = "pending"
CATALOG_UNIT_COVERAGE_MISSING: Final = "missing"
CATALOG_COMPLETED_STATUS: Final = "completed"
CATALOG_COVERAGE_COMPLETE: Final = "complete"
CATALOG_COVERAGE_INCOMPLETE_NON_BLOCKING: Final = "incomplete_non_blocking"
CATALOG_RESET_SOURCE_KIND: Final = "catalog_quality_reset"
CATALOG_NOTE_STATUS_MISSING: Final = "missing"
MIN_COMPLEXITY_SCORE: Final = 1
DEFAULT_CATALOG_RESET_RUN_ID: Final = "catalog"
DEFAULT_CATALOG_RESET_SOURCE_REF: Final = (
    "sqlite:make_raw_spec_manifest_records/current"
)
CATALOG_RESET_SOURCE_PACKET_TARGET_BYTES: Final = 220_000
CATALOG_RESET_ESTIMATED_TOKEN_BYTE_DIVISOR: Final = 4

CATALOG_PRIORITY_BANDS: Final[tuple[str, ...]] = (
    "make_builtins_core ",
    "make_control_data_structures ",
    "make_ai_agents_tools_providers ",
    "popular_apps ",
    "alphabetical_remainder",
)
CATALOG_PRIORITY_BAND_RANK: Final[dict[str, int]] = {
    band: index for index, band in enumerate(CATALOG_PRIORITY_BANDS)
}
CATALOG_UNIT_TYPE_RANK: Final[dict[str, int]] = {
    "app_manifest": 0,
    "operation_batch": 1,
    "raw_spec": 2,
    "app_spec": 3,
    "control_structure": 3,
    "module": 4,
    "operation": 5,
    "field": 6,
    "note": 7,
}
UNKNOWN_UNIT_TYPE_RANK: Final = 100
BUILT_IN_APP_SLUG_PRIORITY: Final[tuple[str, ...]] = (
    "builtin ",
    "flow-control ",
    "util ",
    "tools ",
    "regexp ",
    "text-parser ",
    "gateway ",
    "webhooks ",
    "http ",
    "json ",
    "email ",
    "code ",
    "make-code ",
    "datastore ",
    "data-store ",
    "rss ",
    "phonenumber ",
    "phone-number ",
    "weather ",
    "scenario-service ",
    "scenarios ",
    "csv ",
    "markdown ",
    "ios ",
    "apple-ios ",
    "xml ",
    "image ",
    "ftp ",
    "math ",
    "sftp ",
    "archive ",
    "android ",
    "crypto ",
    "encryptor ",
    "currency ",
    "barcode ",
    "barcodes ",
    "xls ",
    "xlsx ",
    "xlsx-excel-files ",
    "iso ",
    "ssh ",
    "soap ",
    "mime ",
    "gps-tools ",
    "human-in-the-loop-enterprise ",
    "units ",
    "xmp",
)
BUILT_IN_APP_SLUG_ORDER: Final[dict[str, int]] = {
    slug: index for index, slug in enumerate(BUILT_IN_APP_SLUG_PRIORITY)
}
MAKE_CORE_APP_SLUGS: Final[frozenset[str]] = frozenset(
    BUILT_IN_APP_SLUG_PRIORITY
)
MAKE_CONTROL_DATA_APP_SLUGS: Final[frozenset[str]] = frozenset(
    (
        "error-handler ",
        "filter ",
        "router",
    )
)
MAKE_AI_APP_SLUG_PRIORITY: Final[tuple[str, ...]] = (
    "make-ai-agents ",
    "ai-agent ",
    "ai-local-agent ",
    "make-ai-toolkit ",
    "ai-tools ",
    "make-ai-web-search ",
    "make-ai-content-extractor ",
    "make-ai-content-extractors ",
    "make-ai-extractors",
)
MAKE_AI_APP_SLUG_ORDER: Final[dict[str, int]] = {
    slug: index for index, slug in enumerate(MAKE_AI_APP_SLUG_PRIORITY)
}
MAKE_AI_APP_SLUGS: Final[frozenset[str]] = frozenset(MAKE_AI_APP_SLUG_PRIORITY)
POPULAR_APP_SLUG_PRIORITY: Final[tuple[str, ...]] = (
    "facebook-pages ",
    "microsoft-365-email-outlook ",
    "microsoft-365-email ",
    "microsoft-email ",
    "anthropic-claude ",
    "instagram-for-business-facebook-login ",
    "instagram-business ",
    "monday-com ",
    "monday ",
    "tally ",
    "hubspot-crm ",
    "hubspotcrm ",
    "wordpress ",
    "google-forms ",
    "dropbox ",
    "make-ai-agents ",
    "ai-agent ",
    "shopify ",
    "clickup ",
    "linkedin ",
    "supabase ",
    "brevo ",
    "sendinblue ",
    "stripe ",
    "twilio ",
    "apify ",
    "youtube ",
    "make-ai-toolkit ",
    "ai-tools ",
    "discord ",
    "onedrive ",
    "pipedrive-crm ",
    "pipedrive ",
    "line ",
    "gohighlevel ",
    "highlevel ",
    "code ",
    "make-code ",
    "microsoft-365-excel ",
    "microsoft-excel ",
    "calendly ",
    "webflow ",
    "trello ",
    "buffer ",
    "pdf-co ",
    "woocommerce ",
    "make ",
    "whatsapp-business-cloud ",
    "perplexity-ai",
)
POPULAR_APP_SLUG_ORDER: Final[dict[str, int]] = {
    slug: index for index, slug in enumerate(POPULAR_APP_SLUG_PRIORITY)
}
POPULAR_APP_SLUGS: Final[frozenset[str]] = frozenset(POPULAR_APP_SLUG_PRIORITY)
CATALOG_UNKNOWN_APP_ORDER: Final = 10_000
CATALOG_RAW_SPEC_SOURCE_PREFIX: Final = "sqlite:make_raw_spec_payloads/"
CATALOG_CONTROL_SURFACE_SOURCE_PREFIX: Final = (
    "catalog-reset-policy:control-surfaces/"
)
CATALOG_UNIT_NOTE_SURFACES: Final[tuple[str, ...]] = (
    "error_handlers ",
    "filters ",
    "routers_control_structures ",
    "data_stores ",
    "data_structures ",
    "edge_cases ",
    "fallback_behavior ",
    "usage_guidance",
)
CATALOG_CONTROL_SURFACE_ORDER: Final[dict[str, int]] = {
    surface: index for index, surface in enumerate(CATALOG_UNIT_NOTE_SURFACES)
}
CATALOG_CONTROL_SURFACE_DESCRIPTIONS: Final[dict[str, str]] = {
    "error_handlers": (
        "Make scenario error-handler behavior, routing, retries, and fallbacks."
    ),
    "filters": (
        "Make filter behavior, condition semantics, and edge-case "
        "routing gates."
    ),
    "routers_control_structures": (
        "Routers, control structures, branch behavior, aggregators, iterators, "
        "and flow logic."
    ),
    "data_stores": (
        "Make data-store lifecycle, record operations, key/value "
        "semantics, and limits."
    ),
    "data_structures": (
        "Make data structures, typed records, bundles, arrays, and "
        "mapping shapes."
    ),
    "edge_cases": (
        "Cross-cutting scenario edge cases that affect importability "
        "and runtime safety."
    ),
    "fallback_behavior": (
        "Fallback and degradation behavior for incomplete or unavailable "
        "evidence."
    ),
    "usage_guidance": (
        "Practical usage guidance for choosing modules, edges, and scenario "
        "patterns."
    ),
}


class CatalogResetUnitInput(NamedTuple):
    """One fixed-contract catalog unit source for a new active run."""

    unit_id: str
    unit_type: str
    priority_band: str
    source_ref: str
    source_hash: str
    source_size_bytes: int
    complexity_score: int


class CatalogQualityResetRunReport(NamedTuple):
    """Summary for one canonical catalog run."""

    run_id: str
    unit_count: int
    total_complexity_score: int
    legacy_unit_count: int
    legacy_answer_count: int
    note_surface_count: int
    old_semantic_status: str
    incomplete_coverage_policy: str


class CatalogQualityProgressReport(NamedTuple):
    """Unit-count and weighted progress for one active catalog run."""

    run_id: str
    total_unit_count: int
    completed_unit_count: int
    total_complexity_score: int
    completed_complexity_score: int
    incomplete_unit_count: int
    unit_count_progress_ratio: float
    weighted_progress_ratio: float
    coverage_status: str
    catalog_usable: bool


class LegacySemanticCounts(NamedTuple):
    """Counts for old catalog-plan semantic evidence preserved as obsolete.

    input.
    """

    range_count: int
    unit_count: int
    answer_count: int
    quarantine_count: int


class OrderedCatalogUnit(NamedTuple):
    """One validated catalog reset unit with deterministic priority order."""

    source: CatalogResetUnitInput
    priority_order: int


class RawSpecOperationBatch(NamedTuple):
    """One complete operation slice from a raw Make app-version spec."""

    collection: str
    start_index: int
    operations: tuple[object, ...]


def start_catalog_quality_reset_run(
    *,
    connection: sqlite3.Connection,
    run_id: str,
    units: Iterable[CatalogResetUnitInput],
    source_ref: str,
    observed_at_utc: str,
) -> CatalogQualityResetRunReport:
    """Start a new active canonical catalog run without deleting legacy.

    evidence.

    Returns:
        The run report with preserved legacy semantic evidence counts.
    """
    _validate_non_empty_text("run_id", run_id)
    _validate_non_empty_text("source_ref", source_ref)
    _validate_non_empty_text("observed_at_utc", observed_at_utc)
    with connection:
        return start_catalog_quality_reset_run_in_transaction(
            connection=connection,
            run_id=run_id,
            units=units,
            source_ref=source_ref,
            observed_at_utc=observed_at_utc,
        )


def start_catalog_quality_reset_run_in_transaction(
    *,
    connection: sqlite3.Connection,
    run_id: str,
    units: Iterable[CatalogResetUnitInput],
    source_ref: str,
    observed_at_utc: str,
) -> CatalogQualityResetRunReport:
    """Start a reset run using the caller-owned SQLite transaction.

    Returns:
        The run report with preserved legacy semantic evidence counts.
    """
    _validate_non_empty_text("run_id", run_id)
    _validate_non_empty_text("source_ref", source_ref)
    _validate_non_empty_text("observed_at_utc", observed_at_utc)
    ordered_units = _ordered_units(tuple(units))
    total_complexity_score = sum(
        unit.source.complexity_score for unit in ordered_units
    )
    legacy_counts = _legacy_semantic_counts(connection)
    _supersede_other_active_runs(connection=connection, run_id=run_id)
    _insert_catalog_run(
        connection=connection,
        run_id=run_id,
        source_ref=source_ref,
        observed_at_utc=observed_at_utc,
        ordered_units=ordered_units,
    )
    _insert_legacy_archive(
        connection=connection,
        run_id=run_id,
        source_ref=source_ref,
        observed_at_utc=observed_at_utc,
        legacy_counts=legacy_counts,
    )
    _insert_catalog_units(
        connection=connection,
        run_id=run_id,
        ordered_units=ordered_units,
        observed_at_utc=observed_at_utc,
    )
    _insert_catalog_unit_note_surfaces(
        connection=connection,
        run_id=run_id,
        ordered_units=ordered_units,
        observed_at_utc=observed_at_utc,
    )
    return CatalogQualityResetRunReport(
        run_id=run_id,
        unit_count=len(ordered_units),
        total_complexity_score=total_complexity_score,
        legacy_unit_count=legacy_counts.unit_count,
        legacy_answer_count=legacy_counts.answer_count,
        note_surface_count=len(ordered_units) * len(CATALOG_UNIT_NOTE_SURFACES),
        old_semantic_status=CATALOG_OLD_SEMANTIC_STATUS,
        incomplete_coverage_policy=CATALOG_INCOMPLETE_COVERAGE_POLICY,
    )


def catalog_reset_units_from_raw_specs(
    *,
    connection: sqlite3.Connection,
) -> tuple[CatalogResetUnitInput, ...]:
    """Return fixed reset units from the current SQLite raw-spec manifest.

    Returns:
        The raw app-version units that can be leased by catalog.work.next.
    """
    if not _table_exists(
        connection=connection, table_name="make_raw_spec_manifest_records"
    ):
        return ()
    rows = connection.execute(
        """
        SELECT
          records.app_slug,
          records.app_version,
          records.app_label,
          records.sha256,
          records.size_bytes,
          records.module_count,
          payloads.sha256 AS payload_sha256,
          payloads.size_bytes AS payload_size_bytes,
          payloads.payload_json AS payload_json
        FROM make_raw_spec_manifest_records AS records
        LEFT JOIN make_raw_spec_payloads AS payloads
          ON payloads.app_slug = records.app_slug
         AND payloads.app_version = records.app_version
         AND payloads.valid_to IS NULL
        WHERE records.valid_to IS NULL
        ORDER BY records.app_slug, records.app_version
        """
    ).fetchall()
    raw_spec_units = tuple(
        unit for row in rows for unit in _raw_spec_units_from_row(row)
    )
    if not raw_spec_units:
        return ()
    return raw_spec_units + tuple(
        _control_surface_unit(surface) for surface in CATALOG_UNIT_NOTE_SURFACES
    )


def catalog_quality_progress(
    *,
    connection: sqlite3.Connection,
    run_id: str,
) -> CatalogQualityProgressReport:
    """Return count-based and weighted progress without requiring complete.

    coverage.

    Returns:
        The progress report for the requested run.

    Raises:
        ValueError: If the run id is unknown.
    """
    _validate_non_empty_text("run_id", run_id)
    row = connection.execute(
        """
        SELECT
          run_id,
          total_unit_count,
          completed_unit_count,
          total_complexity_score,
          completed_complexity_score,
          incomplete_unit_count,
          unit_count_progress_ratio,
          weighted_progress_ratio,
          coverage_status
        FROM catalog_run_progress
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()
    if row is None:
        message = f"Unknown catalog run: {run_id}"
        raise ValueError(message)
    coverage_status = str(row[8])
    return CatalogQualityProgressReport(
        run_id=str(row[0]),
        total_unit_count=int(row[1]),
        completed_unit_count=int(row[2]),
        total_complexity_score=int(row[3]),
        completed_complexity_score=int(row[4]),
        incomplete_unit_count=int(row[5]),
        unit_count_progress_ratio=float(row[6]),
        weighted_progress_ratio=float(row[7]),
        coverage_status=coverage_status,
        catalog_usable=coverage_status
        in {
            CATALOG_COVERAGE_COMPLETE,
            CATALOG_COVERAGE_INCOMPLETE_NON_BLOCKING,
        },
    )


def _ordered_units(
    units: tuple[CatalogResetUnitInput, ...],
) -> tuple[OrderedCatalogUnit, ...]:
    """Return validated units with deterministic priority ordering."""
    for unit in units:
        _validate_unit(unit)
    sorted_units = sorted(units, key=_catalog_unit_sort_key)
    return tuple(
        OrderedCatalogUnit(source=unit, priority_order=index)
        for index, unit in enumerate(sorted_units, start=1)
    )


def _catalog_unit_sort_key(
    unit: CatalogResetUnitInput,
) -> tuple[int, int, int, str, int, str, str]:
    """Return fixed priority ordering for one catalog reset unit."""
    return (
        CATALOG_PRIORITY_BAND_RANK[unit.priority_band],
        _catalog_unit_app_order(unit),
        CATALOG_UNIT_TYPE_RANK.get(unit.unit_type, UNKNOWN_UNIT_TYPE_RANK),
        _catalog_unit_app_slug(unit),
        -unit.complexity_score,
        unit.source_ref.casefold(),
        unit.unit_id,
    )


def _catalog_unit_app_order(unit: CatalogResetUnitInput) -> int:
    slug = _catalog_unit_app_slug(unit)
    if unit.priority_band == "make_builtins_core":
        return BUILT_IN_APP_SLUG_ORDER.get(slug, CATALOG_UNKNOWN_APP_ORDER)
    if unit.priority_band == "make_control_data_structures":
        return CATALOG_CONTROL_SURFACE_ORDER.get(
            _catalog_unit_control_surface(unit),
            CATALOG_UNKNOWN_APP_ORDER,
        )
    if unit.priority_band == "make_ai_agents_tools_providers":
        return MAKE_AI_APP_SLUG_ORDER.get(slug, CATALOG_UNKNOWN_APP_ORDER)
    if unit.priority_band == "popular_apps":
        return POPULAR_APP_SLUG_ORDER.get(slug, CATALOG_UNKNOWN_APP_ORDER)
    return CATALOG_UNKNOWN_APP_ORDER


def _catalog_unit_app_slug(unit: CatalogResetUnitInput) -> str:
    if unit.source_ref.startswith(CATALOG_RAW_SPEC_SOURCE_PREFIX):
        raw_slug = unit.source_ref[len(CATALOG_RAW_SPEC_SOURCE_PREFIX) :].split(
            "__", 1
        )[0]
        return raw_slug.casefold()
    if unit.unit_id.startswith("raw-spec:"):
        return unit.unit_id.split(":", 2)[1].casefold()
    return unit.source_ref.casefold()


def _catalog_unit_control_surface(unit: CatalogResetUnitInput) -> str:
    if unit.source_ref.startswith(CATALOG_CONTROL_SURFACE_SOURCE_PREFIX):
        return unit.source_ref[
            len(CATALOG_CONTROL_SURFACE_SOURCE_PREFIX) :
        ].casefold()
    if unit.unit_id.startswith("control-surface:"):
        return unit.unit_id.removeprefix("control-surface:").casefold()
    return unit.source_ref.casefold()


def _validate_unit(unit: CatalogResetUnitInput) -> None:
    """Validate one fixed catalog unit contract before it reaches SQLite.

    Raises:
        ValueError: If the fixed unit contract is incomplete or invalid.
    """
    _validate_non_empty_text("unit_id", unit.unit_id)
    _validate_non_empty_text("unit_type", unit.unit_type)
    _validate_non_empty_text("priority_band", unit.priority_band)
    _validate_non_empty_text("source_ref", unit.source_ref)
    _validate_non_empty_text("source_hash", unit.source_hash)
    if unit.priority_band not in CATALOG_PRIORITY_BAND_RANK:
        message = f"Unknown catalog priority band: {unit.priority_band}"
        raise ValueError(message)
    if unit.source_size_bytes < 0:
        message = f"Catalog source size must not be negative: {unit.unit_id}"
        raise ValueError(message)
    if unit.complexity_score < MIN_COMPLEXITY_SCORE:
        message = f"Catalog complexity score must be positive: {unit.unit_id}"
        raise ValueError(message)


def _validate_non_empty_text(field_name: str, value: str) -> None:
    """Reject empty text for required fixed-contract fields.

    Raises:
        ValueError: If the field value is empty.
    """
    if not value.strip():
        message = f"Catalog reset {field_name} must not be empty."
        raise ValueError(message)


def _legacy_semantic_counts(
    connection: sqlite3.Connection,
) -> LegacySemanticCounts:
    """Return counts for preserved legacy catalog-plan semantic surfaces."""
    return LegacySemanticCounts(
        range_count=_count_rows(connection, "catalog_plan_ranges"),
        unit_count=_count_rows(connection, "catalog_plan_units"),
        answer_count=_count_rows(connection, "catalog_plan_semantic_answers"),
        quarantine_count=_count_rows(
            connection, "catalog_plan_quarantine_records"
        ),
    )


def _raw_spec_units_from_row(
    row: sqlite3.Row,
) -> tuple[CatalogResetUnitInput, ...]:
    """Return bounded reset units from a current raw-spec manifest row."""
    payload = _raw_spec_payload_from_row(row)
    if payload is None:
        return (_raw_spec_unit_from_row(row),)
    manifest_unit = _raw_spec_manifest_unit_from_row(row=row, payload=payload)
    operation_units = tuple(
        _raw_spec_operation_batch_unit_from_row(row=row, batch=batch)
        for batch in _raw_spec_operation_batches(payload)
    )
    if not operation_units:
        return (manifest_unit,)
    return (manifest_unit, *operation_units)


def _raw_spec_unit_from_row(row: sqlite3.Row) -> CatalogResetUnitInput:
    """Return one fallback reset unit from a current raw-spec manifest row."""
    app_slug = _row_text(row, "app_slug")
    app_version = _row_text(row, "app_version")
    app_label = _row_text(row, "app_label")
    source_size_bytes = _row_int_or_default(
        row,
        "payload_size_bytes",
        default=_row_int_or_default(
            row, "size_bytes", default=MIN_COMPLEXITY_SCORE
        ),
    )
    source_hash = _row_text(row, "payload_sha256") or _row_text(row, "sha256")
    module_count = _row_int_or_default(
        row, "module_count", default=MIN_COMPLEXITY_SCORE
    )
    complexity_score = max(
        source_size_bytes, module_count * 1_000, MIN_COMPLEXITY_SCORE
    )
    return CatalogResetUnitInput(
        unit_id=f"raw-spec:{app_slug}:{app_version}",
        unit_type="raw_spec",
        priority_band=_priority_band_for_raw_spec(
            app_slug=app_slug, app_label=app_label
        ),
        source_ref=f"sqlite:make_raw_spec_payloads/{app_slug}__{app_version}",
        source_hash=source_hash,
        source_size_bytes=source_size_bytes,
        complexity_score=complexity_score,
    )


def _raw_spec_manifest_unit_from_row(
    *,
    row: sqlite3.Row,
    payload: dict[str, object],
) -> CatalogResetUnitInput:
    """Return one app-level manifest unit that excludes oversized operation.

    arrays.
    """
    app_slug = _row_text(row, "app_slug")
    app_version = _row_text(row, "app_version")
    app_label = _row_text(row, "app_label")
    packet = _raw_spec_manifest_packet(payload)
    packet_text = json.dumps(packet, ensure_ascii=True, sort_keys=True)
    source_size_bytes = len(packet_text.encode("utf-8"))
    return CatalogResetUnitInput(
        unit_id=f"raw-spec-manifest:{app_slug}:{app_version}",
        unit_type="app_manifest",
        priority_band=_priority_band_for_raw_spec(
            app_slug=app_slug, app_label=app_label
        ),
        source_ref=f"sqlite:make_raw_spec_payloads/{app_slug}__{app_version}#manifest",
        source_hash=_fingerprint(packet),
        source_size_bytes=source_size_bytes,
        complexity_score=max(
            _estimated_token_count(source_size_bytes),
            MIN_COMPLEXITY_SCORE,
        ),
    )


def _raw_spec_operation_batch_unit_from_row(
    *,
    row: sqlite3.Row,
    batch: RawSpecOperationBatch,
) -> CatalogResetUnitInput:
    """Return one complete operation-batch unit from a raw app-version spec."""
    app_slug = _row_text(row, "app_slug")
    app_version = _row_text(row, "app_version")
    app_label = _row_text(row, "app_label")
    batch_size_bytes = len(
        json.dumps(batch.operations, ensure_ascii=True, sort_keys=True).encode(
            "utf-8"
        )
    )
    end_index = batch.start_index + len(batch.operations) - 1
    batch_id = f"{batch.collection}:{batch.start_index:04d}-{end_index:04d}"
    return CatalogResetUnitInput(
        unit_id=f"raw-spec-operations:{app_slug}:{app_version}:{batch_id}",
        unit_type="operation_batch",
        priority_band=_priority_band_for_raw_spec(
            app_slug=app_slug, app_label=app_label
        ),
        source_ref=(
            f"sqlite:make_raw_spec_payloads/{app_slug}__{app_version}"
            f"#operations/{batch.collection}/{batch.start_index}-{end_index}"
        ),
        source_hash=_fingerprint(
            {
                "app_slug": app_slug,
                "app_version": app_version,
                "batch": batch_id,
                "operations": batch.operations,
            }
        ),
        source_size_bytes=batch_size_bytes,
        complexity_score=max(
            _estimated_token_count(batch_size_bytes),
            len(batch.operations) * 250,
            MIN_COMPLEXITY_SCORE,
        ),
    )


def _raw_spec_payload_from_row(row: sqlite3.Row) -> dict[str, object] | None:
    value = _row_text(row, "payload_json")
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return {
        str(key): item
        for key, item in cast("dict[object, object]", parsed).items()
    }


def _raw_spec_manifest_packet(payload: dict[str, object]) -> dict[str, object]:
    app = payload.get("app")
    if not isinstance(app, dict):
        return payload
    app_payload = {
        str(key): item
        for key, item in cast("dict[object, object]", app).items()
    }
    manifest: dict[str, object] = {}
    operation_collections: dict[str, dict[str, int]] = {}
    for key, value in app_payload.items():
        if isinstance(value, list):
            operation_values = cast("list[object]", value)
            operation_collections[key] = {
                "operation_count": len(operation_values)
            }
            continue
        manifest[key] = value
    return {
        "app_manifest": manifest,
        "operation_collections": operation_collections,
    }


def _raw_spec_operation_batches(
    payload: dict[str, object],
) -> tuple[RawSpecOperationBatch, ...]:
    app = payload.get("app")
    if not isinstance(app, dict):
        return ()
    app_payload = {
        str(key): item
        for key, item in cast("dict[object, object]", app).items()
    }
    batches: list[RawSpecOperationBatch] = []
    for collection in sorted(app_payload):
        value = app_payload[collection]
        if not isinstance(value, list):
            continue
        operations = tuple(cast("list[object]", value))
        current: list[object] = []
        current_start = 0
        current_size = 0
        for index, operation in enumerate(operations):
            operation_size = len(
                json.dumps(operation, ensure_ascii=True, sort_keys=True).encode(
                    "utf-8"
                )
            )
            if (
                current
                and current_size + operation_size
                > CATALOG_RESET_SOURCE_PACKET_TARGET_BYTES
            ):
                batches.append(
                    RawSpecOperationBatch(
                        collection=collection,
                        start_index=current_start,
                        operations=tuple(current),
                    )
                )
                current = []
                current_start = index
                current_size = 0
            current.append(operation)
            current_size += operation_size
        if current:
            batches.append(
                RawSpecOperationBatch(
                    collection=collection,
                    start_index=current_start,
                    operations=tuple(current),
                )
            )
    return tuple(batches)


def _estimated_token_count(byte_count: int) -> int:
    """Return a conservative token estimate for ASCII-heavy JSON payloads."""
    return max(
        (byte_count + CATALOG_RESET_ESTIMATED_TOKEN_BYTE_DIVISOR - 1)
        // CATALOG_RESET_ESTIMATED_TOKEN_BYTE_DIVISOR,
        MIN_COMPLEXITY_SCORE,
    )


def _control_surface_unit(surface: str) -> CatalogResetUnitInput:
    """Return the computed result for the caller."""
    payload = catalog_control_surface_payload(surface)
    source_size_bytes = len(
        json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    )
    return CatalogResetUnitInput(
        unit_id=f"control-surface:{surface}",
        unit_type="note",
        priority_band="make_control_data_structures",
        source_ref=f"{CATALOG_CONTROL_SURFACE_SOURCE_PREFIX}{surface}",
        source_hash=_fingerprint(payload),
        source_size_bytes=source_size_bytes,
        complexity_score=max(source_size_bytes, MIN_COMPLEXITY_SCORE),
    )


def catalog_control_surface_payload(surface: str) -> dict[str, object]:
    """Return the evidence payload for a first-class Make control/data surface.

    unit.

    Raises:
        ValueError: If the surface is not part of the fixed reset control
        contract.
    """
    normalized_surface = surface.casefold()
    description = CATALOG_CONTROL_SURFACE_DESCRIPTIONS.get(normalized_surface)
    if description is None:
        message = f"Unknown catalog control surface: {surface}"
        raise ValueError(message)
    return {
        "evidence_kind": "catalog_reset_control_surface_policy ",
        "priority_band": "make_control_data_structures",
        "surface": normalized_surface,
        "description": description,
        "semantic_work": (
            "Map this global Make surface into semantic guidance plus graph "
            "nodes and edges. "
            "Preserve weak assumptions in quarantine instead of omitting them."
        ),
        "required_output_notes": (
            "Cover behavior, dependencies, upstream/downstream workflow edges, "
            "graph roles, "
            "edge cases, fallback behavior, and usage guidance."
        ),
    }


def _priority_band_for_raw_spec(*, app_slug: str, app_label: str) -> str:
    """Return the reset priority band for one raw app-version spec."""
    normalized_slug = app_slug.casefold()
    normalized_label = app_label.casefold()
    if normalized_slug in MAKE_CORE_APP_SLUGS:
        return "make_builtins_core"
    if normalized_slug in MAKE_CONTROL_DATA_APP_SLUGS:
        return "make_control_data_structures"
    if (
        normalized_slug in POPULAR_APP_SLUGS
        and normalized_slug not in MAKE_AI_APP_SLUGS
    ):
        return "popular_apps"
    if normalized_slug in MAKE_AI_APP_SLUGS or normalized_label.startswith(
        "make ai "
    ):
        return "make_ai_agents_tools_providers"
    if normalized_slug in POPULAR_APP_SLUGS:
        return "popular_apps"
    return "alphabetical_remainder"


def _count_rows(connection: sqlite3.Connection, table_name: str) -> int:
    """Return a row count for one trusted schema table."""
    row = cast(
        "tuple[int]",
        connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone(),
    )
    return int(row[0])


def _table_exists(*, connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type IN ('table', 'view') AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _row_text(row: sqlite3.Row, key: str) -> str:
    value = row[key]
    return "" if value is None else str(value)


def _row_int_or_default(row: sqlite3.Row, key: str, *, default: int) -> int:
    value = row[key]
    if value is None:
        return default
    if isinstance(value, bool):
        message = f"Catalog reset row {key} must be an integer."
        raise TypeError(message)
    if isinstance(value, int):
        return value
    message = f"Catalog reset row {key} must be an integer."
    raise TypeError(message)


def _supersede_other_active_runs(
    *, connection: sqlite3.Connection, run_id: str
) -> None:
    _ = connection.execute(
        """
        UPDATE catalog_runs
        SET run_status = ?
        WHERE run_status = ?
          AND run_id != ?
        """,
        (CATALOG_RUN_STATUS_SUPERSEDED, CATALOG_RUN_STATUS_ACTIVE, run_id),
    )


def _insert_catalog_run(
    *,
    connection: sqlite3.Connection,
    run_id: str,
    source_ref: str,
    observed_at_utc: str,
    ordered_units: tuple[OrderedCatalogUnit, ...],
) -> None:
    unit_count = len(ordered_units)
    total_complexity_score = sum(
        unit.source.complexity_score for unit in ordered_units
    )
    priority_policy_json = _priority_policy_json()
    fingerprint = _fingerprint(
        {
            "incomplete_coverage_policy": CATALOG_INCOMPLETE_COVERAGE_POLICY,
            "old_semantic_status": CATALOG_OLD_SEMANTIC_STATUS,
            "priority_policy_json": priority_policy_json,
            "reset_strategy": CATALOG_RESET_STRATEGY,
            "run_id": run_id,
            "source_ref": source_ref,
            "total_complexity_score": total_complexity_score,
            "unit_count": unit_count,
        }
    )
    _ = connection.execute(
        """
        INSERT OR REPLACE INTO catalog_runs (
          run_id, run_status, reset_strategy, priority_policy_json,
          old_semantic_status,
          incomplete_coverage_policy, created_at_utc, source_kind, source_ref,
          fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            CATALOG_RUN_STATUS_ACTIVE,
            CATALOG_RESET_STRATEGY,
            priority_policy_json,
            CATALOG_OLD_SEMANTIC_STATUS,
            CATALOG_INCOMPLETE_COVERAGE_POLICY,
            observed_at_utc,
            CATALOG_RESET_SOURCE_KIND,
            source_ref,
            fingerprint,
        ),
    )


def _insert_legacy_archive(
    *,
    connection: sqlite3.Connection,
    run_id: str,
    source_ref: str,
    observed_at_utc: str,
    legacy_counts: LegacySemanticCounts,
) -> None:
    archive_payload = {
        "legacy_answer_count": legacy_counts.answer_count,
        "legacy_quarantine_count": legacy_counts.quarantine_count,
        "legacy_range_count": legacy_counts.range_count,
        "legacy_unit_count": legacy_counts.unit_count,
        "obsolete_status": CATALOG_OLD_SEMANTIC_STATUS,
        "run_id": run_id,
    }
    _ = connection.execute(
        """
        INSERT OR REPLACE INTO catalog_legacy_semantic_archives (
          archive_id, run_id, obsolete_status, legacy_range_count,
          legacy_unit_count,
          legacy_answer_count, legacy_quarantine_count, archived_at_utc,
          source_ref,
          fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _stable_id("catalog-legacy-semantic-archive", run_id, source_ref),
            run_id,
            CATALOG_OLD_SEMANTIC_STATUS,
            legacy_counts.range_count,
            legacy_counts.unit_count,
            legacy_counts.answer_count,
            legacy_counts.quarantine_count,
            observed_at_utc,
            source_ref,
            _fingerprint(archive_payload),
        ),
    )


def _insert_catalog_units(
    *,
    connection: sqlite3.Connection,
    run_id: str,
    ordered_units: tuple[OrderedCatalogUnit, ...],
    observed_at_utc: str,
) -> None:
    _ = connection.executemany(
        """
        INSERT OR REPLACE INTO catalog_units (
          run_id, unit_id, unit_type, priority_band, priority_order, source_ref,
          source_hash, source_size_bytes, complexity_score, status, locked_by,
          locked_at_utc, lease_expires_at_utc, lease_token, attempt_count,
          completed_at_utc, validation_status, coverage_status, created_at_utc,
          updated_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, 0, NULL,
        ?, ?, ?, ?)
        """,
        [
            (
                run_id,
                ordered.source.unit_id,
                ordered.source.unit_type,
                ordered.source.priority_band,
                ordered.priority_order,
                ordered.source.source_ref,
                ordered.source.source_hash,
                ordered.source.source_size_bytes,
                ordered.source.complexity_score,
                CATALOG_UNIT_STATUS_QUEUED,
                CATALOG_UNIT_VALIDATION_PENDING,
                CATALOG_UNIT_COVERAGE_MISSING,
                observed_at_utc,
                observed_at_utc,
            )
            for ordered in ordered_units
        ],
    )


def _insert_catalog_unit_note_surfaces(
    *,
    connection: sqlite3.Connection,
    run_id: str,
    ordered_units: tuple[OrderedCatalogUnit, ...],
    observed_at_utc: str,
) -> None:
    _ = connection.executemany(
        """
        INSERT OR REPLACE INTO catalog_unit_notes (
          run_id, unit_id, note_surface, note_text, note_status, updated_at_utc
        ) VALUES (?, ?, ?, '', ?, ?)
        """,
        [
            (
                run_id,
                ordered.source.unit_id,
                note_surface,
                CATALOG_NOTE_STATUS_MISSING,
                observed_at_utc,
            )
            for ordered in ordered_units
            for note_surface in CATALOG_UNIT_NOTE_SURFACES
        ],
    )


def _priority_policy_json() -> str:
    """Return the computed result for the caller."""
    return json.dumps(
        {
            "built_in_app_slug_priority": list(BUILT_IN_APP_SLUG_PRIORITY),
            "make_ai_app_slug_priority": list(MAKE_AI_APP_SLUG_PRIORITY),
            "popular_app_slug_priority": list(POPULAR_APP_SLUG_PRIORITY),
            "priority_bands": list(CATALOG_PRIORITY_BANDS),
            "unit_type_order": CATALOG_UNIT_TYPE_RANK,
            "note_surfaces": list(CATALOG_UNIT_NOTE_SURFACES),
            "weighted_progress_basis": [
                "source_size_bytes ",
                "raw_spec_size ",
                "complexity_score",
            ],
        },
        ensure_ascii=True,
        sort_keys=True,
    )


def _fingerprint(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True)
    return _sha256_text(payload)


def _stable_id(*parts: object) -> str:
    payload = json.dumps(parts, ensure_ascii=True, sort_keys=True)
    return _sha256_text(payload)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
