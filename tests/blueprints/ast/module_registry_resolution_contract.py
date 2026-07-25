# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Behavior tests for AST module registry resolution.

Boundary contract:
- Owns: tests for resolving AST module tokens against catalog registry data.
- Must not: test catalog compilation broadly or blueprint rendering.
- Allows: raw-spec/catalog fixtures and module-resolution assertions.
- Split when: ambiguity handling and registry binding need separate modules.
- Merge when: another module-resolution test duplicates these cases.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from blueprints.ast import (
    parse_make_ast_json_text,
    require_module_resolution,
    resolve_ast_modules,
)
from catalog import (
    catalog_snapshot_from_json,
    compile_catalog_from_manifest,
)
from catalog.json_payloads import normalize_json_object
from languages.make.raw_specs import (
    SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
    MakeRawSpecTarget,
    MakeScraperConfig,
    load_raw_spec_manifest,
    sync_raw_specs,
)

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from catalog import CatalogSnapshot
    from languages.make.raw_specs.models import JsonObject as RawSpecJsonObject

REPO_ROOT = repo_root()
AST_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "blueprints"
    / "fixtures"
    / "make_ast"
    / "lead_routing_blueprint.json"
)
CATALOG_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "catalog"
    / "fixtures"
    / "make_catalog"
    / "sample_catalog.json"
)
RAW_SPEC_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "catalog"
    / "fixtures"
    / "make_catalog"
    / "sample_raw_spec.json"
)
FIXED_GENERATED_AT = "2026-04-28T00:00:00+00:00"


class MultiVersionRawSpecSource:
    """Deterministic raw-spec source for ambiguous family tests."""

    def __init__(
        self, specs: dict[MakeRawSpecTarget, RawSpecJsonObject]
    ) -> None:
        """Store raw spec payloads by target."""
        self._specs = specs

    def list_app_versions(self) -> tuple[MakeRawSpecTarget, ...]:
        """Return available raw-spec targets."""
        return tuple(self._specs)

    def fetch_app_spec(self, target: MakeRawSpecTarget) -> RawSpecJsonObject:
        """Return one raw-spec payload."""
        return self._specs[target]


def test_ast_module_resolution_binds_node_to_catalog_module() -> None:
    """Resolved AST modules expose catalog family, schemas, RPCs, and.

    warnings.
    """
    root = parse_make_ast_json_text(AST_FIXTURE.read_text(encoding="utf-8"))
    report = resolve_ast_modules(root=root, catalog=load_catalog_fixture())
    resolution = require_module_resolution(report, "3")

    assert resolution.status == "resolved", (
        f"HTTP node should resolve: {resolution}"
    )
    assert resolution.app_slug == "http", (
        f"Unexpected app identity: {resolution}"
    )
    assert resolution.app_version == "1.0", (
        f"Unexpected app identity: {resolution}"
    )
    assert resolution.module_kind == "action", (
        f"Unexpected module identity: {resolution}"
    )
    assert resolution.internal_name == "makeRequest", (
        f"Unexpected module identity: {resolution}"
    )
    assert resolution.module_family == "http:1.0:action", (
        f"Unexpected module family: {resolution.module_family}"
    )
    assert not ("deprecated_module" not in resolution.issues), (
        f"Deprecated modules must carry warning metadata: {resolution}"
    )
    assert not (
        "rpc://http/listConnections" not in resolution.rpc_dependencies
    ), f"RPC dependencies were not exposed: {resolution.rpc_dependencies}"
    assert resolution.parameter_ids, (
        f"Resolved schemas must expose parameter and interface fields: "
        f"{resolution}"
    )
    assert resolution.interface_field_ids, (
        f"Resolved schemas must expose parameter and interface fields: "
        f"{resolution}"
    )
    assert resolution.raw_spec_references, (
        f"Resolved modules must expose raw-spec references: {resolution}"
    )


def test_ast_module_resolution_rejects_missing_custom_and_legacy_tokens() -> (
    None
):
    """Missing, custom, and legacy module tokens stay unresolved."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "unresolved-modules",
                "flow": [
                    {"id": 1, "module": "unknown-service:MissingAction"},
                    {"id": 2, "module": "custom-app:DoThing"},
                    {"id": 3, "module": "missing"},
                ],
            }
        )
    )
    report = resolve_ast_modules(root=root, catalog=load_catalog_fixture())

    missing = require_module_resolution(report, "1")
    custom = require_module_resolution(report, "2")
    legacy = require_module_resolution(report, "3")
    assert missing.status != "resolved", (
        f"Nonexistent module resolved incorrectly: {missing}"
    )
    assert missing.issues == ("missing_raw_spec",), (
        f"Nonexistent module resolved incorrectly: {missing}"
    )
    assert custom.status != "resolved", (
        f"Custom module resolved incorrectly: {custom}"
    )
    assert custom.issues == ("unsupported_custom_app",), (
        f"Custom module resolved incorrectly: {custom}"
    )
    assert legacy.status != "resolved", (
        f"Legacy module shape resolved incorrectly: {legacy}"
    )
    assert legacy.issues == ("legacy_module_shape",), (
        f"Legacy module shape resolved incorrectly: {legacy}"
    )


def test_ast_module_resolution_allows_catalog_backed_custom_modules(
    tmp_path: Path,
) -> None:
    """Custom modules resolve only when catalog evidence exists."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "catalog-backed-custom-module",
                "flow": [{"id": 1, "module": "custom-app:DoThing"}],
            }
        )
    )
    report = resolve_ast_modules(
        root=root, catalog=compile_custom_catalog(tmp_path)
    )
    resolution = require_module_resolution(report, "1")

    assert resolution.status == "resolved", (
        f"Catalog-backed custom module failed: {resolution}"
    )
    assert (
        resolution.catalog_module_id == "module:custom-app:1.0:custom:DoThing"
    ), f"Unexpected custom module binding: {resolution}"
    assert resolution.app_slug == "custom-app", (
        f"Unexpected app identity: {resolution}"
    )
    assert resolution.module_kind == "custom", (
        f"Unexpected module identity: {resolution}"
    )
    assert resolution.internal_name == "DoThing", (
        f"Unexpected module identity: {resolution}"
    )
    assert resolution.issues == (), (
        f"Catalog-backed custom modules should not be blocked: {resolution}"
    )
    assert resolution.source_label == "raw_spec_manifest", (
        f"Missing source trace: {resolution}"
    )
    assert resolution.source_rank == 10, f"Missing source rank: {resolution}"


def test_ast_module_resolution_reports_ambiguous_module_families(
    tmp_path: Path,
) -> None:
    """Multiple compatible catalog families require explicit metadata."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "ambiguous",
                "flow": [{"id": 1, "module": "http:MakeRequest"}],
            }
        )
    )
    report = resolve_ast_modules(
        root=root, catalog=compile_ambiguous_catalog(tmp_path)
    )
    resolution = require_module_resolution(report, "1")

    assert resolution.status == "unresolved", (
        f"Ambiguous module should not resolve: {resolution}"
    )
    assert resolution.issues == (
        "ambiguous_module_family ",
        "insufficient_blueprint_metadata",
    ), f"Ambiguous module issues were not explicit: {resolution.issues}"


def load_catalog_fixture() -> CatalogSnapshot:
    """Load the sample catalog fixture.

    Returns:
        The loaded value.
    """
    payload = cast(
        "object", json.loads(CATALOG_FIXTURE.read_text(encoding="utf-8"))
    )
    assert isinstance(payload, dict), (
        f"{CATALOG_FIXTURE} must contain a JSON object."
    )
    return catalog_snapshot_from_json(
        normalize_json_object(cast("Mapping[str, object]", payload))
    )


def compile_custom_catalog(tmp_path: Path) -> CatalogSnapshot:
    """Compile one catalog with an explicit custom module.

    Returns:
        The result produced by compile one catalog with an explicit custom
        module.
    """
    report = sync_raw_specs(
        config=MakeScraperConfig(repo_root=tmp_path),
        source=MultiVersionRawSpecSource(
            {
                MakeRawSpecTarget(app_slug="custom-app", app_version="1.0"): {
                    "app": {
                        "name": "custom-app ",
                        "version": "1.0 ",
                        "label": "Custom App",
                        "latest": True,
                        "manifest": {"version": 2},
                        "customModules": [
                            {
                                "name": "DoThing ",
                                "label": "Do thing",
                                "parameters": [{"name": "payload"}],
                                "interface": [{"name": "result"}],
                            }
                        ],
                    }
                }
            }
        ),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )
    manifest = load_raw_spec_manifest(tmp_path / report.manifest_path)
    return compile_catalog_from_manifest(repo_root=tmp_path, manifest=manifest)


def compile_ambiguous_catalog(tmp_path: Path) -> CatalogSnapshot:
    """Compile two raw-spec versions with the same AST token family.

    Returns:
        The result produced by compile two raw-spec versions with the same AST
        token family.
    """
    base_payload = load_raw_spec_payload()
    newer_payload = load_raw_spec_payload()
    app = object_member(newer_payload, "app")
    app["version"] = "2.0"
    source = MultiVersionRawSpecSource(
        {
            MakeRawSpecTarget(app_slug="http", app_version="1.0"): base_payload,
            MakeRawSpecTarget(
                app_slug="http", app_version="2.0"
            ): newer_payload,
        }
    )
    report = sync_raw_specs(
        config=MakeScraperConfig(repo_root=tmp_path),
        source=source,
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )
    manifest = load_raw_spec_manifest(tmp_path / report.manifest_path)
    return compile_catalog_from_manifest(repo_root=tmp_path, manifest=manifest)


def load_raw_spec_payload() -> RawSpecJsonObject:
    """Load the sample raw-spec fixture.

    Returns:
        The loaded value.
    """
    payload = cast(
        "object", json.loads(RAW_SPEC_FIXTURE.read_text(encoding="utf-8"))
    )
    assert isinstance(payload, dict), (
        f"{RAW_SPEC_FIXTURE} must contain a JSON object."
    )
    return dict(
        normalize_json_object(cast("Mapping[str, object]", payload)).items()
    )


def object_member(payload: RawSpecJsonObject, key: str) -> RawSpecJsonObject:
    """Return one object member from a raw-spec fixture."""
    value = payload.get(key)
    assert isinstance(value, dict), (
        f"Expected raw-spec object member {key!r}: {payload}"
    )
    return cast("RawSpecJsonObject", value)
