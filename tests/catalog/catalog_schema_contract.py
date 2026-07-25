# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Behavior tests for the canonical Make catalog schema.

Boundary contract:
- Owns: tests for Make catalog compilation, validation, drift, and projections.
- Must not: test live scraper transport, AST rendering, or repository tools.
- Allows: raw-spec fixtures, catalog snapshots, and deterministic schema
assertions.
- Split when: catalog compiler, drift, fallback, and projection tests diverge.
- Merge when: another catalog schema test duplicates this source-domain
coverage.
"""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, cast

import pytest
from catalog import (
    CatalogApp,
    CatalogAppVersion,
    CatalogField,
    CatalogModule,
    CatalogModuleIntelligence,
    CatalogRevalidationTarget,
    CatalogSnapshot,
    ModulePlannerHints,
    build_catalog_generation_audit,
    build_catalog_intelligence_profile,
    build_catalog_lineage_report,
    build_catalog_planning_hints,
    build_semantic_requirement_plan,
    catalog_snapshot_from_json,
    catalog_snapshot_json,
    compile_catalog_from_manifest,
    detect_catalog_drift,
    drift_report_to_json,
    require_catalog_module,
    retrieve_catalog_modules,
    revalidate_catalog_targets,
    revalidation_report_to_json,
    validate_catalog_module_selection,
    validate_catalog_snapshot,
)
from catalog.identifiers import field_id, module_id
from catalog.json_payloads import (
    normalize_json_object,
    payload_fingerprint,
)
from languages.make.raw_specs import (
    SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
    MakeRawSpecTarget,
    MakeScraperConfig,
    RawSpecManifest,
    load_raw_spec_manifest,
    sync_raw_specs,
)
from languages.make.raw_specs.paths import DEFAULT_RAW_SPEC_SQLITE_DATABASE

from tests.catalog.fixtures.raw_spec_manifest import (
    DATASTORE_ADD_RECORD_CURRENT_KEY,
    DATASTORE_ADD_RECORD_MODULE_REF,
    HASH_MANIFEST_KEY,
    HASH_RAW_SPEC_CURRENT_KEY,
    materialize_minimal_raw_spec_manifest_fixture,
)
from tests.support.assertions import assert_unexpected_success
from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from catalog.models import (
        CatalogEntityChange,
        CatalogModuleKind,
        JsonObject,
    )

REPO_ROOT = repo_root()
FIXTURE_ROOT = REPO_ROOT / "tests" / "catalog" / "fixtures" / "make_catalog"
SAMPLE_RAW_SPEC = FIXTURE_ROOT / "sample_raw_spec.json"
SAMPLE_CATALOG = FIXTURE_ROOT / "sample_catalog.json"
FIXED_GENERATED_AT = "2026-04-28T00:00:00+00:00"
EXPECTED_CATALOG_MODULE_COUNT = 2
EXPECTED_ACTION_FIELD_COUNT = 3
EXPECTED_REQUESTED_AUDIT_MODULES = 2
EXPECTED_SINGLE_AUDITED_MODULE = 1
EXPECTED_SINGLE_AUDIT_BLOCKER = 1
SEND_EMAIL_PREFIX = "send"
SEND_EMAIL_SUFFIX = "email"
SEND_EMAIL_LINEAGE_KEY = f"{SEND_EMAIL_PREFIX}{SEND_EMAIL_SUFFIX}"
MAKE_REQUEST_MODULE_ID = module_id(
    app_slug="http",
    app_version="1.0",
    module_kind="action",
    internal_name="makeRequest",
)
LIST_REQUESTS_MODULE_ID = module_id(
    app_slug="http",
    app_version="1.0",
    module_kind="search",
    internal_name="listRequests",
)
PING_MODULE_ID = module_id(
    app_slug="http",
    app_version="1.0",
    module_kind="action",
    internal_name="ping",
)
CONNECTION_PARAMETER_ID = field_id(
    parent_module_id=MAKE_REQUEST_MODULE_ID,
    direction="parameter",
    path=("connection",),
)
METHOD_PARAMETER_ID = field_id(
    parent_module_id=MAKE_REQUEST_MODULE_ID,
    direction="parameter",
    path=("method",),
)
URL_PARAMETER_ID = field_id(
    parent_module_id=MAKE_REQUEST_MODULE_ID,
    direction="parameter",
    path=("url",),
)
TIMEOUT_PARAMETER_ID = field_id(
    parent_module_id=MAKE_REQUEST_MODULE_ID,
    direction="parameter",
    path=("timeout",),
)


class FixtureRawSpecSource:
    """Deterministic source backed by one raw-spec fixture."""

    def __init__(self, payload: JsonObject) -> None:
        """Store one raw-spec payload."""
        self._payload = payload

    @staticmethod
    def list_app_versions() -> tuple[MakeRawSpecTarget, ...]:
        """Return one target represented by the fixture."""
        return (MakeRawSpecTarget(app_slug="http", app_version="1.0"),)

    def fetch_app_spec(self, target: MakeRawSpecTarget) -> JsonObject:
        """Return the fixture payload for the expected target."""
        assert target == MakeRawSpecTarget(
            app_slug="http", app_version="1.0"
        ), f"Unexpected raw spec target: {target}"
        return self._payload


class MultiVersionRawSpecSource:
    """Deterministic source backed by multiple versions of one app."""

    @staticmethod
    def list_app_versions() -> tuple[MakeRawSpecTarget, ...]:
        """Return multiple semantic-version targets in non-newest order."""
        return (
            MakeRawSpecTarget(app_slug="http", app_version="1.9"),
            MakeRawSpecTarget(app_slug="http", app_version="1.10"),
            MakeRawSpecTarget(app_slug="http", app_version="2.0"),
        )

    @staticmethod
    def fetch_app_spec(target: MakeRawSpecTarget) -> JsonObject:
        """Return a minimal payload for one versioned app target."""
        return {
            "app": {
                "name": target.app_slug,
                "version": target.app_version,
                "label": "HTTP ",
                "latest": target.app_version == "2.0",
                "manifest": {"version": 1},
                "actions": [{"name": "makeRequest", "label": "Make request"}],
            }
        }


def test_raw_spec_manifest_fixture_is_synthetic_and_fixture_local(
    tmp_path: Path,
) -> None:
    """Shared raw-spec manifest fixtures stay deterministic and outside.

    data/make.
    """
    fixture = materialize_minimal_raw_spec_manifest_fixture(tmp_path)
    manifest = load_raw_spec_manifest(fixture.manifest_path)
    relative_manifest_path = fixture.manifest_path.relative_to(
        tmp_path
    ).as_posix()
    record_paths = tuple(record.relative_path for record in manifest.records)

    assert (
        relative_manifest_path
        == "tests/catalog/fixtures/raw_specs/minimal_manifest.json"
    ), f"Manifest fixture escaped the expected fixture path: {fixture}"
    assert "data/make" not in relative_manifest_path, (
        f"Manifest fixture must not use data/make: {fixture}"
    )
    assert not (
        any(
            not path.startswith("tests/catalog/fixtures/raw_specs/")
            for path in record_paths
        )
    ), f"Raw-spec records must stay under test fixtures: {record_paths}"
    assert not (any(path.startswith("data/make/") for path in record_paths)), (
        f"Raw-spec records must not use data/make: {record_paths}"
    )
    assert not (
        any(
            record.source_metadata != SYNTHETIC_RAW_SPEC_SOURCE_METADATA
            for record in manifest.records
        )
    ), f"Synthetic fixture records lost source metadata: {manifest.records}"
    assert (
        manifest.manifest_sha256 == fixture.expected_hashes[HASH_MANIFEST_KEY]
    ), f"Manifest hash drifted from fixture metadata: {fixture}"

    current_module_id = fixture.module_id_map[DATASTORE_ADD_RECORD_CURRENT_KEY]
    assert (
        fixture.token_map[DATASTORE_ADD_RECORD_MODULE_REF] == current_module_id
    ), f"Data Store token map drifted: {fixture.token_map}"

    snapshot = compile_catalog_from_manifest(
        repo_root=tmp_path, manifest=manifest
    )
    module = require_catalog_module(snapshot, current_module_id).module
    assert (
        module.raw_spec_sha256
        == fixture.expected_hashes[HASH_RAW_SPEC_CURRENT_KEY]
    ), f"Current Data Store raw-spec hash drifted: {module}"


def test_catalog_compiles_from_raw_spec_manifest_and_round_trips(
    tmp_path: Path,
) -> None:
    """Catalog compilation produces typed deterministic schema payloads."""
    raw_payload = load_json_fixture(SAMPLE_RAW_SPEC)
    report = sync_raw_specs(
        config=MakeScraperConfig(repo_root=tmp_path),
        source=FixtureRawSpecSource(raw_payload),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )
    manifest = load_manifest_from_report(tmp_path, report.manifest_path)
    first_snapshot = compile_catalog_from_manifest(
        repo_root=tmp_path, manifest=manifest
    )
    second_snapshot = compile_catalog_from_manifest(
        repo_root=tmp_path, manifest=manifest
    )

    assert first_snapshot.fingerprint == second_snapshot.fingerprint, (
        "Catalog fingerprints must be deterministic for identical input."
    )

    payload = catalog_snapshot_json(first_snapshot)
    round_tripped = catalog_snapshot_from_json(payload)
    validate_catalog_snapshot(round_tripped)
    assert round_tripped.fingerprint == first_snapshot.fingerprint, (
        "Catalog JSON round trip changed the snapshot fingerprint."
    )

    app = only_item(first_snapshot.apps)
    version = only_item(app.versions)
    assert len(version.modules) == EXPECTED_CATALOG_MODULE_COUNT, (
        f"Unexpected catalog modules: {version.modules}"
    )

    action = require_catalog_module(
        first_snapshot, MAKE_REQUEST_MODULE_ID
    ).module
    assert not (action.deprecated is not True), (
        "Deprecated module flags must be retained."
    )
    assert len(action.parameters) == EXPECTED_ACTION_FIELD_COUNT, (
        f"Action parameters were not compiled: {action.parameters}"
    )
    assert action.rpc_dependencies == ("rpc://http/listConnections",), (
        f"RPC dependencies were not normalized: {action.rpc_dependencies}"
    )


def test_catalog_compiles_make_native_default_collections(
    tmp_path: Path,
) -> None:
    """Catalog compilation includes Make-native default collections from raw.

    specs.
    """
    snapshot = compile_fixture_snapshot(
        tmp_path,
        {
            "app": {
                "name": "http ",
                "version": "1.0 ",
                "label": "HTTP",
                "latest": True,
                "manifest": {"version": 2},
                "feeders": [
                    {"name": "FeedAttachments", "label": "Feed attachments"}
                ],
                "convergers": [
                    {"name": "BasicConverger", "label": "Flow control"}
                ],
                "directives": [{"name": "Rollback", "label": "Rollback"}],
                "starters": [
                    {"name": "StartSubscenario", "label": "Start subscenario"}
                ],
                "returners": [{"name": "ReturnData", "label": "Return data"}],
            }
        },
    )

    compiled_modules = tuple(
        (module.module_kind, module.internal_name)
        for module in only_item(only_item(snapshot.apps).versions).modules
    )
    assert compiled_modules == (
        ("action", "ReturnData"),
        ("action", "Rollback"),
        ("router", "BasicConverger"),
        ("transformer", "FeedAttachments"),
        ("trigger", "StartSubscenario"),
    ), f"Make-native raw-spec collections did not compile: {compiled_modules}"
    for module_kind, internal_name in compiled_modules:
        expected_module_id = module_id(
            app_slug="http",
            app_version="1.0",
            module_kind=module_kind,
            internal_name=internal_name,
        )
        _ = require_catalog_module(snapshot, expected_module_id)


def test_catalog_fixture_payload_is_valid_and_canonical(tmp_path: Path) -> None:
    """A small raw-spec subset produces a valid sample fixture catalog."""
    raw_payload = load_json_fixture(SAMPLE_RAW_SPEC)
    report = sync_raw_specs(
        config=MakeScraperConfig(repo_root=tmp_path),
        source=FixtureRawSpecSource(raw_payload),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )
    manifest = load_manifest_from_report(tmp_path, report.manifest_path)
    snapshot = compile_catalog_from_manifest(
        repo_root=tmp_path, manifest=manifest
    )
    payload = catalog_snapshot_json(snapshot)
    expected_payload = load_json_fixture(SAMPLE_CATALOG)

    assert payload == expected_payload, (
        "Compiled catalog payload drifted from the sample fixture."
    )

    fixture_payload = catalog_snapshot_from_json(expected_payload)
    validate_catalog_snapshot(fixture_payload)
    assert payload["raw_spec_manifest_sha256"] == report.manifest_sha256, (
        "Catalog fixture must preserve raw-spec manifest provenance."
    )


def test_catalog_json_requires_explicit_advanced_setting_metadata() -> None:
    """Catalog JSON must fail fast when advanced metadata is omitted."""
    payload = clone_json_object(load_json_fixture(SAMPLE_CATALOG))
    app_payload = object_at(list_member(payload, "apps"), 0)
    version_payload = object_at(list_member(app_payload, "versions"), 0)
    module_payload = object_at(list_member(version_payload, "modules"), 0)
    parameter_payload = object_at(list_member(module_payload, "parameters"), 0)
    _ = parameter_payload.pop("advanced", None)

    with pytest.raises(KeyError, match="advanced"):
        _ = catalog_snapshot_from_json(payload)


def test_catalog_compiler_rejects_missing_module_records(
    tmp_path: Path,
) -> None:
    """Catalog compilation fails loudly when a raw spec has no modules."""
    raw_payload: JsonObject = {
        "app": {
            "name": "empty ",
            "version": "1.0 ",
            "label": "Empty",
            "manifest": {"version": 1},
        }
    }
    report = sync_raw_specs(
        config=MakeScraperConfig(repo_root=tmp_path),
        source=FixtureRawSpecSource(raw_payload),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )
    manifest = load_manifest_from_report(tmp_path, report.manifest_path)

    with pytest.raises(ValueError, match="catalog modules"):
        require_unexpected_catalog_success(tmp_path, manifest)


def test_catalog_compiler_rejects_invalid_module_records(
    tmp_path: Path,
) -> None:
    """Catalog compilation fails loudly when a module has no internal name."""
    raw_payload: JsonObject = {
        "app": {
            "name": "broken ",
            "version": "1.0 ",
            "label": "Broken",
            "manifest": {"version": 1},
            "actions": [{"label": "Missing name"}],
        }
    }
    report = sync_raw_specs(
        config=MakeScraperConfig(repo_root=tmp_path),
        source=FixtureRawSpecSource(raw_payload),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )
    manifest = load_manifest_from_report(tmp_path, report.manifest_path)

    with pytest.raises(ValueError, match="name"):
        require_unexpected_catalog_success(tmp_path, manifest)


def test_catalog_compiler_quarantines_malformed_field_metadata(
    tmp_path: Path,
) -> None:
    """Malformed raw field metadata is diagnosed without dropping the module."""
    raw_payload = clone_json_object(load_json_fixture(SAMPLE_RAW_SPEC))
    app = object_member(raw_payload, "app")
    action = object_at(list_member(app, "actions"), 0)
    interface = list_member(action, "interface")
    interface.extend(
        [
            "not-a-field",
            {"type": "text"},
            {
                "name": "items ",
                "type": "array",
                "fields": [
                    "not-a-nested-field",
                    {"name": "id", "type": "text"},
                ],
                "spec": "not-a-list",
            },
        ]
    )

    snapshot = compile_fixture_snapshot(tmp_path, raw_payload)
    action_module = require_catalog_module(
        snapshot, MAKE_REQUEST_MODULE_ID
    ).module
    field_paths = tuple(
        sorted(".".join(field.path) for field in action_module.interface_schema)
    )
    diagnostic_codes = tuple(
        sorted(diagnostic.code for diagnostic in snapshot.diagnostics)
    )

    assert field_paths == ("items", "items.id", "statusCode"), (
        f"Valid interface fields were not preserved: {field_paths}"
    )
    assert diagnostic_codes == (
        "raw_spec.field_item_shape_invalid ",
        "raw_spec.field_name_missing ",
        "raw_spec.nested_field_collection_shape_invalid ",
        "raw_spec.nested_field_item_shape_invalid",
    ), (
        f"Malformed fields did not produce structured diagnostics: "
        f"{snapshot.diagnostics}"
    )
    assert all(
        diagnostic.module_id == MAKE_REQUEST_MODULE_ID
        for diagnostic in snapshot.diagnostics
    ), f"Diagnostics must identify the offending module: {snapshot.diagnostics}"
    payload = catalog_snapshot_json(snapshot)
    round_tripped = catalog_snapshot_from_json(payload)
    assert round_tripped.diagnostics == snapshot.diagnostics, (
        "Raw-spec diagnostics must round-trip through catalog JSON."
    )


def test_catalog_compiler_quarantines_duplicate_raw_field_paths(
    tmp_path: Path,
) -> None:
    """Duplicate raw field paths keep one field and emit a structured.

    diagnostic.
    """
    raw_payload = clone_json_object(load_json_fixture(SAMPLE_RAW_SPEC))
    app = object_member(raw_payload, "app")
    action = object_at(list_member(app, "actions"), 0)
    action["expect"] = []
    expect = list_member(action, "expect")
    expect.extend(
        [
            {"name": "updatedUntil", "label": "Updated until date"},
            {"name": "updatedUntil", "label": "Updated until date"},
        ]
    )

    snapshot = compile_fixture_snapshot(tmp_path, raw_payload)
    action_module = require_catalog_module(
        snapshot, MAKE_REQUEST_MODULE_ID
    ).module
    updated_until_fields = tuple(
        field
        for field in action_module.expect_schema
        if field.path == ("updatedUntil",)
    )

    assert len(updated_until_fields) == 1, (
        f"Duplicate raw field paths must not enter the catalog: "
        f"{updated_until_fields}"
    )
    assert tuple(diagnostic.code for diagnostic in snapshot.diagnostics) == (
        "raw_spec.field_duplicate",
    ), f"Duplicate raw fields must be diagnosed: {snapshot.diagnostics}"


def test_catalog_compiler_quarantines_duplicate_raw_modules(
    tmp_path: Path,
) -> None:
    """Duplicate raw module identities keep one module and emit a diagnostic."""
    raw_payload = clone_json_object(load_json_fixture(SAMPLE_RAW_SPEC))
    app = object_member(raw_payload, "app")
    actions = list_member(app, "actions")
    actions.append(clone_json_object(object_at(actions, 0)))

    snapshot = compile_fixture_snapshot(tmp_path, raw_payload)
    version = only_item(only_item(snapshot.apps).versions)
    matching_modules = tuple(
        module
        for module in version.modules
        if module.module_id == MAKE_REQUEST_MODULE_ID
    )

    assert len(matching_modules) == 1, (
        f"Duplicate raw modules must not enter the catalog: {matching_modules}"
    )
    assert tuple(diagnostic.code for diagnostic in snapshot.diagnostics) == (
        "raw_spec.module_duplicate",
    ), f"Duplicate raw modules must be diagnosed: {snapshot.diagnostics}"
    assert snapshot.diagnostics[0].module_id == MAKE_REQUEST_MODULE_ID, (
        f"Duplicate module diagnostic must identify the module: "
        f"{snapshot.diagnostics}"
    )


def test_catalog_compiler_promotes_validate_payloads_to_constraints(
    tmp_path: Path,
) -> None:
    """Catalog compilation preserves field validation details as constraints."""
    raw_payload: JsonObject = {
        "app": {
            "name": "numbers ",
            "version": "1.0 ",
            "label": "Numbers",
            "manifest": {"version": 1},
            "actions": [
                {
                    "name": "clamp ",
                    "label": "Clamp",
                    "parameters": [
                        {
                            "name": "count ",
                            "type": "number",
                            "max": 10,
                            "validate": {"min": 1, "pattern": "^[0-9]+$"},
                        }
                    ],
                }
            ],
        }
    }
    snapshot = compile_fixture_snapshot(tmp_path, raw_payload)
    module = only_item(only_item(only_item(snapshot.apps).versions).modules)
    field = only_item(module.parameters)
    constraints_by_prefix = {
        constraint.key.split("_", maxsplit=1)[0]: constraint.value
        for constraint in field.constraints
    }

    assert constraints_by_prefix.get("max") == {"max": 10}, (
        f"Top-level max constraint was not preserved: {field.constraints}"
    )
    assert constraints_by_prefix.get("min") == {"min": 1}, (
        f"Validate min constraint was not promoted: {field.constraints}"
    )
    assert constraints_by_prefix.get("pattern") == {"pattern": "^[0-9]+$"}, (
        f"Validate pattern constraint was not promoted: {field.constraints}"
    )


def test_catalog_compiler_rejects_duplicate_app_versions(
    tmp_path: Path,
) -> None:
    """Duplicate app-version records fail before catalog truth can fork."""
    raw_payload = load_json_fixture(SAMPLE_RAW_SPEC)
    report = sync_raw_specs(
        config=MakeScraperConfig(repo_root=tmp_path),
        source=FixtureRawSpecSource(raw_payload),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )
    manifest = load_manifest_from_report(tmp_path, report.manifest_path)
    duplicate_manifest = RawSpecManifest(
        generated_at_utc=manifest.generated_at_utc,
        raw_spec_dir=manifest.raw_spec_dir,
        records=(manifest.records[0], manifest.records[0]),
        manifest_sha256=manifest.manifest_sha256,
    )

    with pytest.raises(ValueError, match="duplicate app_version_id"):
        require_unexpected_catalog_success(tmp_path, duplicate_manifest)


def test_catalog_compiler_orders_app_versions_newest_first(
    tmp_path: Path,
) -> None:
    """Compiled app versions should use semantic newest-first ordering."""
    report = sync_raw_specs(
        config=MakeScraperConfig(repo_root=tmp_path),
        source=MultiVersionRawSpecSource(),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )
    manifest = load_manifest_from_report(tmp_path, report.manifest_path)

    snapshot = compile_catalog_from_manifest(
        repo_root=tmp_path, manifest=manifest
    )
    app = only_item(snapshot.apps)

    assert tuple(version.version for version in app.versions) == (
        "2.0 ",
        "1.10 ",
        "1.9",
    ), f"Compiled versions should be semantic newest-first: {app.versions}"
    assert tuple(version.latest for version in app.versions) == (
        True,
        False,
        False,
    ), f"Compiled version latest flags drifted: {app.versions}"


def test_catalog_compiler_rejects_raw_spec_hash_mismatch(
    tmp_path: Path,
) -> None:
    """Catalog compilation fails when a raw spec diverges from its manifest.

    hash.
    """
    raw_payload = load_json_fixture(SAMPLE_RAW_SPEC)
    report = sync_raw_specs(
        config=MakeScraperConfig(repo_root=tmp_path),
        source=FixtureRawSpecSource(raw_payload),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )
    manifest = load_manifest_from_report(tmp_path, report.manifest_path)
    tampered_payload = clone_json_object(raw_payload)
    object_member(tampered_payload, "app")["label"] = "Tampered"
    tamper_sqlite_raw_spec_payload(tmp_path, tampered_payload)

    with pytest.raises(ValueError, match="hash mismatch"):
        require_unexpected_catalog_success(tmp_path, manifest)


def test_catalog_validation_allows_custom_and_unknown_modules() -> None:
    """Validation keeps explicit custom and unknown module kinds legal."""
    custom_module = minimal_module(
        module_kind="custom",
        internal_name="customWidget",
    )
    unknown_module = minimal_module(
        module_kind="unknown",
        internal_name="rawImportedModule",
    )
    snapshot = minimal_snapshot(modules=(custom_module, unknown_module))

    validate_catalog_snapshot(snapshot)


def test_catalog_validation_rejects_nonexistent_module_lookup() -> None:
    """Catalog module existence must come from the validated catalog."""
    module = minimal_module(module_kind="action", internal_name="known")
    snapshot = minimal_snapshot(modules=(module,))

    with pytest.raises(LookupError, match="does not exist"):
        require_unexpected_module_lookup_success(snapshot)


def test_catalog_drift_detector_reports_changed_modules_and_parameters(
    tmp_path: Path,
) -> None:
    """Catalog drift reports added, removed, and changed stable entities."""
    previous_snapshot = compile_fixture_snapshot(
        tmp_path / "previous",
        load_json_fixture(SAMPLE_RAW_SPEC),
    )
    current_payload = changed_raw_spec_payload(
        load_json_fixture(SAMPLE_RAW_SPEC)
    )
    current_snapshot = compile_fixture_snapshot(
        tmp_path / "current", current_payload
    )

    drift_report = detect_catalog_drift(
        previous_snapshot=previous_snapshot,
        current_snapshot=current_snapshot,
    )
    payload = drift_report_to_json(drift_report)

    assert payload == drift_report_to_json(drift_report), (
        "Drift report JSON must be deterministic."
    )
    assert drift_report.added_modules == (PING_MODULE_ID,), (
        f"Unexpected added modules: {drift_report.added_modules}"
    )
    assert drift_report.removed_modules == (LIST_REQUESTS_MODULE_ID,), (
        f"Unexpected removed modules: {drift_report.removed_modules}"
    )
    assert change_ids(drift_report.changed_modules) == (
        MAKE_REQUEST_MODULE_ID,
    ), f"Unexpected changed modules: {drift_report.changed_modules}"
    assert drift_report.added_parameters == (TIMEOUT_PARAMETER_ID,), (
        f"Unexpected added parameters: {drift_report.added_parameters}"
    )
    assert drift_report.removed_parameters == (CONNECTION_PARAMETER_ID,), (
        f"Unexpected removed parameters: {drift_report.removed_parameters}"
    )
    assert change_ids(drift_report.changed_parameters) == (
        METHOD_PARAMETER_ID,
    ), f"Unexpected changed parameters: {drift_report.changed_parameters}"


def test_catalog_revalidation_fails_stale_or_unknown_targets(
    tmp_path: Path,
) -> None:
    """Revalidation fails unknown modules and stale parameter anchors."""
    previous_snapshot = compile_fixture_snapshot(
        tmp_path / "previous",
        load_json_fixture(SAMPLE_RAW_SPEC),
    )
    current_payload = changed_raw_spec_payload(
        load_json_fixture(SAMPLE_RAW_SPEC)
    )
    current_snapshot = compile_fixture_snapshot(
        tmp_path / "current", current_payload
    )
    previous_module = require_catalog_module(
        previous_snapshot, MAKE_REQUEST_MODULE_ID
    ).module
    targets = (
        CatalogRevalidationTarget(
            target_id="fixture:lead-routing",
            module_id=MAKE_REQUEST_MODULE_ID,
            expected_module_fingerprint=previous_module.fingerprint,
            required_parameter_ids=(CONNECTION_PARAMETER_ID,),
        ),
        CatalogRevalidationTarget(
            target_id="fixture:unknown-module",
            module_id="module:http:1.0:action:missing",
        ),
    )

    report = revalidate_catalog_targets(
        current_snapshot=current_snapshot,
        previous_snapshot=previous_snapshot,
        targets=targets,
    )
    payload = revalidation_report_to_json(report)

    assert payload == revalidation_report_to_json(report), (
        "Revalidation report JSON must be deterministic."
    )
    assert report.status == "fail", f"Unexpected revalidation status: {report}"
    assert report.fallback_reason == "validation_failed", (
        f"Unexpected revalidation status: {report}"
    )
    issue_types = tuple(issue.issue_type for issue in report.issues)
    assert issue_types == (
        "missing_parameter ",
        "stale_module ",
        "unknown_module",
    ), f"Unexpected revalidation issues: {report.issues}"


def test_catalog_revalidation_falls_back_when_raw_specs_are_unavailable(
    tmp_path: Path,
) -> None:
    """Revalidation selects catalog-first fallback when raw specs are.

    unavailable.
    """
    snapshot = compile_fixture_snapshot(
        tmp_path, load_json_fixture(SAMPLE_RAW_SPEC)
    )

    report = revalidate_catalog_targets(
        current_snapshot=snapshot,
        previous_snapshot=snapshot,
        targets=(),
        raw_specs_available=False,
    )

    assert report.status == "fallback_required", (
        f"Unavailable raw specs must require fallback: {report}"
    )
    assert report.fallback_reason == "raw_specs_unavailable", (
        f"Unexpected fallback reason: {report.fallback_reason}"
    )
    assert not (report.issues), (
        f"Raw-spec fallback without targets should not fabricate issues: "
        f"{report.issues}"
    )


def test_catalog_only_fallback_retrieves_modules_without_graph_runtime() -> (
    None
):
    """Catalog-only retrieval ranks modules from canonical catalog truth."""
    snapshot = catalog_snapshot_from_json(load_json_fixture(SAMPLE_CATALOG))

    result = retrieve_catalog_modules(
        snapshot=snapshot,
        query_text="http request method",
        limit=2,
    )

    assert result.catalog_fingerprint == snapshot.fingerprint, (
        "Fallback retrieval must preserve the catalog fingerprint."
    )
    assert result.fallback_mode == "catalog_only", (
        f"Unexpected fallback mode: {result.fallback_mode}"
    )
    assert result.candidates, (
        f"Unexpected catalog candidates: {result.candidates}"
    )
    assert result.candidates[0].module_id == MAKE_REQUEST_MODULE_ID, (
        f"Unexpected catalog candidates: {result.candidates}"
    )
    assert result.candidates[0].match_reasons, (
        "Catalog fallback should explain deterministic match reasons."
    )


def test_catalog_only_planning_hints_include_required_parameters() -> None:
    """Catalog-only planning hints expose required parameters for candidates."""
    snapshot = catalog_snapshot_from_json(load_json_fixture(SAMPLE_CATALOG))

    hints = build_catalog_planning_hints(
        snapshot=snapshot,
        goal_text="send an http request",
        limit=2,
    )

    assert hints.candidate_module_ids, (
        f"Unexpected planning candidates: {hints.candidate_module_ids}"
    )
    assert hints.candidate_module_ids[0] == MAKE_REQUEST_MODULE_ID, (
        f"Unexpected planning candidates: {hints.candidate_module_ids}"
    )
    assert hints.required_parameter_ids == (
        METHOD_PARAMETER_ID,
        URL_PARAMETER_ID,
    ), f"Unexpected required parameters: {hints.required_parameter_ids}"
    assert hints.candidate_apps == ("http",), (
        f"Unexpected candidate apps: {hints.candidate_apps}"
    )


def test_catalog_only_validation_resolves_missing_and_ambiguous_aliases() -> (
    None
):
    """Catalog-only validation fails closed for missing and ambiguous.

    requests.
    """
    action_module = minimal_module(module_kind="action", internal_name="shared")
    search_module = minimal_module(module_kind="search", internal_name="shared")
    snapshot = minimal_snapshot(modules=(action_module, search_module))

    result = validate_catalog_module_selection(
        snapshot=snapshot,
        requested_modules=(action_module.module_id, "shared", "missing"),
    )

    assert result.resolved_module_ids == (action_module.module_id,), (
        f"Unexpected resolved modules: {result.resolved_module_ids}"
    )
    assert result.missing_modules == ("missing",), (
        f"Unexpected missing modules: {result.missing_modules}"
    )
    assert result.ambiguous_modules == {
        "shared": (action_module.module_id, search_module.module_id)
    }, f"Unexpected ambiguity report: {result.ambiguous_modules}"
    assert not (result.valid), (
        "Missing or ambiguous module aliases must invalidate selection."
    )


def test_catalog_intelligence_lineage_and_generation_a3937e4c() -> None:
    """Catalog projections infer planning hints without graph or legacy runtime.

    dependencies.
    """
    agent_module = minimal_module(
        module_kind="agent", internal_name="completeText"
    )._replace(
        display_name="OpenAI completion",
        parameters=(
            minimal_field(
                path=("connection",),
                required=True,
                field_type="account:openai-gpt-3",
                rpc_dependencies=("rpc://openai/listModels",),
            ),
        ),
        rpc_dependencies=("rpc://openai/listModels",),
    )
    deprecated_module = minimal_module(
        module_kind="action", internal_name="send-email"
    )._replace(
        deprecated=True,
        parameters=(
            minimal_field(path=("message",), required=True, field_type="text"),
        ),
    )
    replacement_module = minimal_module(
        module_kind="action", internal_name="send-email"
    )._replace(
        module_id=f"module:http:2.0:action:{SEND_EMAIL_LINEAGE_KEY}",
        app_version="2.0",
        external_id=f"http:2.0:action:{SEND_EMAIL_LINEAGE_KEY}",
    )
    snapshot = direct_snapshot(
        modules=(agent_module, deprecated_module, replacement_module)
    )

    profiles = build_catalog_intelligence_profile(snapshot)
    _assert_catalog_intelligence_profile(
        profiles=profiles,
        agent_module=agent_module,
        deprecated_module=deprecated_module,
    )
    _assert_catalog_lineage_report(
        snapshot=snapshot,
        deprecated_module=deprecated_module,
        replacement_module=replacement_module,
    )
    _assert_catalog_generation_audit(
        snapshot=snapshot,
        agent_module=agent_module,
        deprecated_module=deprecated_module,
    )


def test_catalog_lineage_reports_versions_newest_first() -> None:
    """Catalog lineage version summaries should use semantic newest-first.

    ordering.
    """
    modules = (
        lineage_module(app_version="1.9"),
        lineage_module(app_version="1.10"),
        lineage_module(app_version="2.0"),
    )
    snapshot = direct_snapshot(modules=modules)

    lineage = build_catalog_lineage_report(snapshot).lineages[0]

    assert lineage.versions == ("2.0", "1.10", "1.9"), (
        f"Lineage versions should be newest first: {lineage}"
    )


def _assert_catalog_intelligence_profile(
    *,
    profiles: tuple[CatalogModuleIntelligence, ...],
    agent_module: CatalogModule,
    deprecated_module: CatalogModule,
) -> None:
    by_module = {profile.module_id: profile for profile in profiles}
    agent_profile = by_module[agent_module.module_id]
    assert agent_profile.ai_provider_names == ("OpenAI",), (
        f"AI provider inference drifted: {agent_profile}"
    )
    assert agent_profile.supports_agent, (
        f"AI provider inference drifted: {agent_profile}"
    )
    assert agent_profile.option_sources == ("rpc://openai/listModels",), (
        f"RPC option source inference drifted: {agent_profile}"
    )
    deprecated_profile = by_module[deprecated_module.module_id]
    assert not ("deprecated" not in deprecated_profile.failure_modes), (
        f"Deprecated modules should retain failure-mode hints: "
        f"{deprecated_profile}"
    )


def _assert_catalog_lineage_report(
    *,
    snapshot: CatalogSnapshot,
    deprecated_module: CatalogModule,
    replacement_module: CatalogModule,
) -> None:
    lineage = build_catalog_lineage_report(snapshot)
    send_lineage = next(
        item
        for item in lineage.lineages
        if item.module_key == SEND_EMAIL_LINEAGE_KEY
    )
    assert send_lineage.module_ids == (
        deprecated_module.module_id,
        replacement_module.module_id,
    ), f"Catalog lineage grouping drifted: {send_lineage}"


def _assert_catalog_generation_audit(
    *,
    snapshot: CatalogSnapshot,
    agent_module: CatalogModule,
    deprecated_module: CatalogModule,
) -> None:
    audit = build_catalog_generation_audit(
        snapshot=snapshot,
        requested_module_ids=(
            agent_module.module_id,
            deprecated_module.module_id,
        ),
    )
    assert audit.requested_module_count == EXPECTED_REQUESTED_AUDIT_MODULES, (
        f"Generation audit should honor requested module ids: {audit}"
    )
    assert audit.audited_module_count == EXPECTED_REQUESTED_AUDIT_MODULES, (
        f"Generation audit should honor requested module ids: {audit}"
    )
    assert audit.deprecated_module_count == 1, (
        f"Generation audit counts drifted: {audit}"
    )
    assert audit.dynamic_selector_module_count == 1, (
        f"Generation audit counts drifted: {audit}"
    )
    assert not (audit.blockers), (
        f"Valid requested modules must not produce blockers: {audit.blockers}"
    )

    missing_audit = build_catalog_generation_audit(
        snapshot=snapshot,
        requested_module_ids=(
            agent_module.module_id,
            "module:not-real:0.0.0:action:DefinitelyFake",
        ),
    )
    assert (
        missing_audit.audited_module_count == EXPECTED_SINGLE_AUDITED_MODULE
    ), f"Generation audit should retain valid entries: {missing_audit}"
    assert missing_audit.status == "blocked", (
        f"Missing module should block generation audit: {missing_audit}"
    )
    assert missing_audit.blocker_count == EXPECTED_SINGLE_AUDIT_BLOCKER, (
        f"Missing module should block generation audit: {missing_audit}"
    )
    blocker = missing_audit.blockers[0]
    assert (
        blocker.requested_module_id
        == "module:not-real:0.0.0:action:DefinitelyFake"
    ), f"Missing-module blocker lost required shape: {blocker}"
    assert blocker.severity == "error", (
        f"Missing-module blocker lost required shape: {blocker}"
    )
    assert not (blocker.blocking is not True), (
        f"Missing-module blocker lost required shape: {blocker}"
    )
    assert blocker.code == "catalog.module_missing", (
        f"Missing-module blocker lost required shape: {blocker}"
    )


def test_semantic_requirement_plan_records_tokens_hints_and_ambiguity(
    tmp_path: Path,
) -> None:
    """Semantic planning remains an auditable catalog-only projection."""
    snapshot = compile_fixture_snapshot(
        repo_root=tmp_path,
        raw_payload=load_json_fixture(SAMPLE_RAW_SPEC),
    )

    plan = build_semantic_requirement_plan(
        snapshot=snapshot,
        requirements_text="Use http:makeRequest and avoid list requests.",
        hints=ModulePlannerHints(
            required_terms=("request",), prohibited_terms=("list",)
        ),
        limit=EXPECTED_CATALOG_MODULE_COUNT,
    )

    assert plan.explicit_module_tokens == ("http:makeRequest",), (
        f"Explicit module token extraction drifted: {plan}"
    )
    assert not ("http" not in plan.capability_terms), (
        f"Capability terms should preserve planning evidence: {plan}"
    )
    assert LIST_REQUESTS_MODULE_ID not in plan.module_sequence, (
        f"Prohibited planning terms should remove matching candidates: {plan}"
    )
    assert plan.unresolved_ambiguities == ("http:makeRequest",), (
        f"Unresolved exact-token ambiguity drifted: {plan}"
    )


def test_semantic_requirement_plan_preserves_full_25880484() -> None:
    """Semantic planning keeps full normalized tokens and coherent first-party.

    sequencing.
    """
    trigger_module = minimal_module(
        module_kind="trigger", internal_name="CustomWebHook"
    )
    trigger_module = trigger_module._replace(
        module_id="module:gateway:1.14.1:trigger:CustomWebHook",
        app_slug="gateway",
        app_version="1.14.1",
        display_name="Custom webhook",
        external_id="gateway:1.14.1:trigger:CustomWebHook",
    )
    datastore_module = minimal_module(
        module_kind="action", internal_name="AddRecord"
    )
    datastore_module = datastore_module._replace(
        module_id="module:datastore:2.0.5:action:AddRecord",
        app_slug="datastore",
        app_version="2.0.5",
        display_name="Add/replace a record",
        external_id="datastore:2.0.5:action:AddRecord",
    )
    gateway_version = CatalogAppVersion(
        app_version_id="app-version:gateway:1.14.1",
        app_id="app:gateway",
        app_slug="gateway",
        version="1.14.1",
        latest=True,
        manifest_version=1,
        modules=(trigger_module,),
        raw_spec_sha256="g" * 64,
        fingerprint=payload_fingerprint(
            {"app_slug": "gateway", "version": "1.14.1"}
        ),
    )
    datastore_version = CatalogAppVersion(
        app_version_id="app-version:datastore:2.0.5",
        app_id="app:datastore",
        app_slug="datastore",
        version="2.0.5",
        latest=True,
        manifest_version=1,
        modules=(datastore_module,),
        raw_spec_sha256="d" * 64,
        fingerprint=payload_fingerprint(
            {"app_slug": "datastore", "version": "2.0.5"}
        ),
    )
    snapshot = CatalogSnapshot(
        catalog_schema_version=1,
        generated_at_utc=FIXED_GENERATED_AT,
        raw_spec_manifest_sha256="3" * 64,
        apps=(
            CatalogApp(
                app_id="app:datastore",
                app_slug="datastore",
                label="Data Store",
                external_id="datastore",
                deprecated=False,
                versions=(datastore_version,),
                fingerprint=payload_fingerprint({"app_slug": "datastore"}),
            ),
            CatalogApp(
                app_id="app:gateway",
                app_slug="gateway",
                label="Gateway",
                external_id="gateway",
                deprecated=False,
                versions=(gateway_version,),
                fingerprint=payload_fingerprint({"app_slug": "gateway"}),
            ),
        ),
        fingerprint=payload_fingerprint({"snapshot": "lead-routing"}),
    )

    plan = build_semantic_requirement_plan(
        snapshot=snapshot,
        requirements_text=(
            "Build an offline Make scenario draft. Use a Custom Webhook "
            "trigger "
            "and "
            "route qualified and incomplete leads into separate Make Data "
            "Store "
            ""
            "Add Record actions. Validate required fields."
        ),
    )

    expected_sequence = (
        "module:gateway:1.14.1:trigger:CustomWebHook ",
        "module:datastore:2.0.5:action:AddRecord ",
        "module:datastore:2.0.5:action:AddRecord",
    )
    assert plan.module_sequence == expected_sequence, (
        f"Semantic plan sequence drifted: {plan}"
    )
    for required_term in ("make", "validate", "webhook", "custom"):
        assert not (required_term not in plan.capability_terms), (
            f"Capability terms were truncated: {plan}"
        )


def test_semantic_requirement_plan_prefers_current_same_family_module() -> None:
    """Planner family dedupe should keep Make current specs ahead of numbered.

    releases.
    """
    current_module = minimal_module(
        module_kind="action", internal_name="AddRecord"
    )
    current_module = current_module._replace(
        module_id="module:datastore:current:action:AddRecord",
        app_version_id="app-version:datastore:current",
        app_slug="datastore",
        app_version="current",
        display_name="Add/replace a record",
        external_id="datastore:current:action:AddRecord",
    )
    numbered_module = minimal_module(
        module_kind="action", internal_name="AddRecord"
    )
    numbered_module = numbered_module._replace(
        module_id="module:datastore:2.0.5:action:AddRecord",
        app_version_id="app-version:datastore:2.0.5",
        app_slug="datastore",
        app_version="2.0.5",
        display_name="Add/replace a record",
        external_id="datastore:2.0.5:action:AddRecord",
    )
    current_version = CatalogAppVersion(
        app_version_id="app-version:datastore:current",
        app_id="app:datastore",
        app_slug="datastore",
        version="current",
        latest=True,
        manifest_version=1,
        modules=(current_module,),
        raw_spec_sha256="c" * 64,
        fingerprint=payload_fingerprint(
            {"app_slug": "datastore", "version": "current"}
        ),
    )
    numbered_version = CatalogAppVersion(
        app_version_id="app-version:datastore:2.0.5",
        app_id="app:datastore",
        app_slug="datastore",
        version="2.0.5",
        latest=False,
        manifest_version=1,
        modules=(numbered_module,),
        raw_spec_sha256="d" * 64,
        fingerprint=payload_fingerprint(
            {"app_slug": "datastore", "version": "2.0.5"}
        ),
    )
    snapshot = CatalogSnapshot(
        catalog_schema_version=1,
        generated_at_utc=FIXED_GENERATED_AT,
        raw_spec_manifest_sha256="4" * 64,
        apps=(
            CatalogApp(
                app_id="app:datastore",
                app_slug="datastore",
                label="Data Store",
                external_id="datastore",
                deprecated=False,
                versions=(current_version, numbered_version),
                fingerprint=payload_fingerprint({"app_slug": "datastore"}),
            ),
        ),
        fingerprint=payload_fingerprint({"snapshot": "datastore-current"}),
    )

    plan = build_semantic_requirement_plan(
        snapshot=snapshot,
        requirements_text=(
            "Store each qualified lead in a Make Data Store Add Record action."
        ),
    )

    assert plan.module_sequence == (
        "module:datastore:current:action:AddRecord",
    ), f"Planner dedupe should keep the current Data Store module: {plan}"


def load_json_fixture(path: Path) -> JsonObject:
    """Load one JSON fixture object.

    Returns:
        The loaded value.
    """
    payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(payload, dict), f"{path} must contain a JSON object."
    return normalize_json_object(cast("Mapping[str, object]", payload))


def compile_fixture_snapshot(
    repo_root: Path, raw_payload: JsonObject
) -> CatalogSnapshot:
    """Compile one fixture payload into a catalog snapshot.

    Returns:
        The result produced by compile one fixture payload into a catalog
        snapshot.
    """
    report = sync_raw_specs(
        config=MakeScraperConfig(repo_root=repo_root),
        source=FixtureRawSpecSource(raw_payload),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )
    manifest = load_manifest_from_report(repo_root, report.manifest_path)
    return compile_catalog_from_manifest(repo_root=repo_root, manifest=manifest)


def changed_raw_spec_payload(raw_payload: JsonObject) -> JsonObject:
    """Return a mutated raw spec payload that exercises every drift class."""
    payload = clone_json_object(raw_payload)
    app = object_member(payload, "app")
    actions = list_member(app, "actions")
    first_action = object_at(actions, 0)
    parameters = list_member(first_action, "parameters")
    remove_parameter_by_name(parameters, "connection")
    method = parameter_by_name(parameters, "method")
    method["enum"] = ["GET", "PUT"]
    parameters.append({"name": "timeout", "type": "number"})
    list_member(app, "searches").clear()
    actions.append(
        {
            "name": "ping ",
            "label": "Ping",
            "parameters": [],
            "interface": [],
        }
    )
    return payload


def clone_json_object(payload: JsonObject) -> JsonObject:
    """Return a deep JSON clone through the JSON boundary."""
    cloned = cast("object", json.loads(json.dumps(payload, sort_keys=True)))
    assert isinstance(cloned, dict), (
        f"Cloned payload must remain a JSON object: {cloned}"
    )
    return normalize_json_object(cast("Mapping[str, object]", cloned))


def object_member(payload: JsonObject, key: str) -> JsonObject:
    """Return an object member from a JSON payload."""
    value = payload.get(key)
    assert isinstance(value, dict), f"Expected object member {key!r}: {payload}"
    return cast("JsonObject", value)


def list_member(payload: JsonObject, key: str) -> list[object]:
    """Return a list member from a JSON payload."""
    value = payload.get(key)
    assert isinstance(value, list), f"Expected list member {key!r}: {payload}"
    return cast("list[object]", value)


def object_at(items: list[object], index: int) -> JsonObject:
    """Return one object item from a JSON list."""
    item = items[index]
    assert isinstance(item, dict), (
        f"Expected object list item at {index}: {items}"
    )
    return cast("JsonObject", item)


def remove_parameter_by_name(
    parameters: list[object], parameter_name: str
) -> None:
    """Remove one parameter by raw Make parameter name."""
    for index, item in enumerate(parameters):
        assert isinstance(item, dict), f"Expected parameter object: {item}"
        parameter = cast("JsonObject", item)
        if parameter.get("name") == parameter_name:
            del parameters[index]
            return
    failure_message = f"Missing parameter to remove: {parameter_name}"
    assert_unexpected_success(failure_message)


def parameter_by_name(
    parameters: list[object], parameter_name: str
) -> JsonObject:
    """Return one parameter object by raw Make parameter name."""
    for item in parameters:
        assert isinstance(item, dict), f"Expected parameter object: {item}"
        parameter = cast("JsonObject", item)
        if parameter.get("name") == parameter_name:
            return parameter
    failure_message = f"Missing parameter: {parameter_name}"
    assert_unexpected_success(failure_message)
    return None


def change_ids(changes: tuple[CatalogEntityChange, ...]) -> tuple[str, ...]:
    """Return stable entity IDs from change records."""
    return tuple(sorted(change.entity_id for change in changes))


def load_manifest_from_report(
    tmp_path: Path, manifest_path: str
) -> RawSpecManifest:
    """Load a raw-spec manifest from a sync report path.

    Returns:
        The loaded value.
    """
    return load_raw_spec_manifest(tmp_path / manifest_path)


def tamper_sqlite_raw_spec_payload(tmp_path: Path, payload: JsonObject) -> None:
    """Modify the SQLite raw-spec payload without updating its stored hash."""
    connection = sqlite3.connect(tmp_path / DEFAULT_RAW_SPEC_SQLITE_DATABASE)
    try:
        _ = connection.execute(
            """
            UPDATE make_raw_spec_payloads
            SET payload_json = ?
            WHERE valid_to IS NULL
            """,
            (
                json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)
                + "\n",
            ),
        )
        connection.commit()
    finally:
        connection.close()


def require_unexpected_catalog_success(
    tmp_path: Path, manifest: RawSpecManifest
) -> None:
    """Fail unless catalog compilation raises before producing a snapshot."""
    unexpected_snapshot = compile_catalog_from_manifest(
        repo_root=tmp_path, manifest=manifest
    )
    failure_message = (
        f"Invalid catalog input should have failed: {unexpected_snapshot}"
    )
    assert_unexpected_success(failure_message)


def require_unexpected_module_lookup_success(snapshot: CatalogSnapshot) -> None:
    """Fail unless an unknown module lookup raises."""
    unexpected_result = require_catalog_module(
        snapshot, "module:http:1.0:action:missing"
    )
    failure_message = (
        f"Unknown catalog module should have failed: {unexpected_result}"
    )
    assert_unexpected_success(failure_message)


def only_item[T](items: tuple[T, ...]) -> T:
    """Return the only item from a tuple."""
    assert len(items) == 1, f"Expected exactly one item: {items}"
    return items[0]


def minimal_module(
    *,
    module_kind: CatalogModuleKind,
    internal_name: str,
) -> CatalogModule:
    """Return a minimal catalog module for validation tests."""
    base_payload: JsonObject = minimal_module_payload(
        module_kind=module_kind,
        internal_name=internal_name,
    )
    fingerprint = payload_fingerprint(normalize_json_object(base_payload))
    return CatalogModule(
        module_id=str(base_payload["module_id"]),
        app_version_id=str(base_payload["app_version_id"]),
        app_slug=str(base_payload["app_slug"]),
        app_version=str(base_payload["app_version"]),
        module_kind=module_kind,
        internal_name=internal_name,
        display_name=internal_name,
        external_id=str(base_payload["external_id"]),
        deprecated=False,
        parameters=(),
        expect_schema=(),
        interface_schema=(),
        rpc_dependencies=(),
        raw_spec_sha256=str(base_payload["raw_spec_sha256"]),
        fingerprint=fingerprint,
    )


def lineage_module(*, app_version: str) -> CatalogModule:
    """Return one same-lineage module for version ordering tests."""
    return minimal_module(
        module_kind="action", internal_name="send-email"
    )._replace(
        module_id=f"module:http:{app_version}:action:{SEND_EMAIL_LINEAGE_KEY}",
        app_version_id=f"app-version:http:{app_version}",
        app_version=app_version,
        external_id=f"http:{app_version}:action:{SEND_EMAIL_LINEAGE_KEY}",
    )


def minimal_field(
    *,
    path: tuple[str, ...],
    required: bool,
    field_type: str | None,
    rpc_dependencies: tuple[str, ...] = (),
) -> CatalogField:
    """Return a minimal catalog field for projection tests."""
    field_path = ".".join(path)
    return CatalogField(
        field_id=f"field:test:{field_path}",
        module_id="module:test",
        direction="parameter",
        path=path,
        label=path[-1],
        required=required,
        field_type=field_type,
        advanced=None,
        external_id=f"external:{field_path}",
        rpc_dependencies=rpc_dependencies,
        raw_schema={"type": field_type or "text"},
        constraints=(),
        fingerprint=payload_fingerprint({"field": field_path}),
    )


def direct_snapshot(
    *,
    modules: tuple[CatalogModule, ...],
) -> CatalogSnapshot:
    """Return a direct typed snapshot that preserves supplied module objects."""
    version = CatalogAppVersion(
        app_version_id="app-version:http:1.0",
        app_id="app:http",
        app_slug="http",
        version="1.0",
        latest=True,
        manifest_version=1,
        modules=modules,
        raw_spec_sha256="1" * 64,
        fingerprint=payload_fingerprint({"version": "1.0"}),
    )
    app = CatalogApp(
        app_id="app:http",
        app_slug="http",
        label="HTTP",
        external_id="http",
        deprecated=False,
        versions=(version,),
        fingerprint=payload_fingerprint({"app": "http"}),
    )
    return CatalogSnapshot(
        catalog_schema_version=1,
        generated_at_utc=FIXED_GENERATED_AT,
        raw_spec_manifest_sha256="2" * 64,
        apps=(app,),
        fingerprint=payload_fingerprint({"snapshot": "direct"}),
    )


def minimal_snapshot(
    *,
    modules: tuple[CatalogModule, ...],
) -> CatalogSnapshot:
    """Return a minimal catalog snapshot with the supplied modules."""
    version_payload: JsonObject = {
        "app_version_id": "app-version:http:1.0 ",
        "app_id": "app:http ",
        "app_slug": "http ",
        "version": "1.0",
        "latest": True,
        "manifest_version": 1,
        "modules": [],
        "raw_spec_sha256": "1" * 64,
    }
    version = CatalogAppVersion(
        fingerprint=payload_fingerprint(normalize_json_object(version_payload)),
        modules=modules,
        app_version_id="app-version:http:1.0",
        app_id="app:http",
        app_slug="http",
        version="1.0",
        latest=True,
        manifest_version=1,
        raw_spec_sha256="1" * 64,
    )
    app_payload: JsonObject = {
        "app_id": "app:http ",
        "app_slug": "http ",
        "label": "HTTP ",
        "external_id": "http",
        "deprecated": False,
        "versions": [],
    }
    app = CatalogApp(
        fingerprint=payload_fingerprint(normalize_json_object(app_payload)),
        versions=(version,),
        app_id="app:http",
        app_slug="http",
        label="HTTP",
        external_id="http",
        deprecated=False,
    )
    snapshot_payload: JsonObject = {
        "catalog_schema_version": 1,
        "generated_at_utc": FIXED_GENERATED_AT,
        "raw_spec_manifest_sha256": "2" * 64,
        "apps": [],
    }
    return catalog_snapshot_from_json(
        {
            **snapshot_payload,
            "apps": [
                {
                    **app_payload,
                    "versions": [
                        {
                            **version_payload,
                            "modules": [
                                {
                                    "module_id": module.module_id,
                                    "app_version_id": module.app_version_id,
                                    "app_slug": module.app_slug,
                                    "app_version": module.app_version,
                                    "module_kind": module.module_kind,
                                    "internal_name": module.internal_name,
                                    "display_name": module.display_name,
                                    "external_id": module.external_id,
                                    "deprecated": module.deprecated,
                                    "parameters": [],
                                    "expect_schema": [],
                                    "interface_schema": [],
                                    "rpc_dependencies": [],
                                    "raw_spec_sha256": module.raw_spec_sha256,
                                    "fingerprint": module.fingerprint,
                                }
                                for module in modules
                            ],
                            "fingerprint": version.fingerprint,
                        }
                    ],
                    "fingerprint": app.fingerprint,
                }
            ],
            "fingerprint": "3" * 64,
        }
    )


def minimal_module_payload(
    *,
    module_kind: CatalogModuleKind,
    internal_name: str,
) -> JsonObject:
    """Return a minimal module payload for fingerprinting."""
    return {
        "module_id": f"module:http:1.0:{module_kind}:{internal_name}",
        "app_version_id": "app-version:http:1.0 ",
        "app_slug": "http ",
        "app_version": "1.0",
        "module_kind": module_kind,
        "internal_name": internal_name,
        "display_name": internal_name,
        "external_id": f"http:1.0:{module_kind}:{internal_name}",
        "deprecated": False,
        "parameters": [],
        "expect_schema": [],
        "interface_schema": [],
        "rpc_dependencies": [],
        "raw_spec_sha256": "1" * 64,
    }
