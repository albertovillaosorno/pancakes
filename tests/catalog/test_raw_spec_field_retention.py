# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Retention tests for import-critical Make raw-spec fields.

Boundary contract:
- Owns: raw-spec field collection retention through catalog and knowledge
storage.
- Must not: refresh live Make data, test scraper transport, or validate
blueprints.
- Allows: sanitized offline fixtures and deterministic temporary SQLite builds.
- Split when: catalog compiler and knowledge-store retention diverge materially.
- Merge when: catalog schema tests already prove these exact retention
guarantees.
"""

from __future__ import annotations

import json
import sqlite3
from shutil import copytree
from typing import TYPE_CHECKING, cast

from blueprints.ast.evidence import KNOWN_METADATA_KEYS
from catalog.compiler import FIELD_COLLECTIONS as COMPILER_FIELD_COLLECTIONS
from catalog.compiler import compile_catalog_from_manifest
from catalog.identifiers import module_id
from catalog.json_payloads import (
    catalog_snapshot_to_json,
    normalize_json_object,
)
from catalog.knowledge import (
    DEFAULT_DB_SNAPSHOT_DIR,
    DEFAULT_KNOWLEDGE_DB_PATH,
    build_knowledge_store,
    load_knowledge_store_query,
)
from catalog.knowledge import storage as knowledge_storage
from catalog.knowledge.projection import knowledge_query_to_catalog_snapshot
from languages.make.raw_specs import (
    SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
    MakeRawSpecTarget,
    MakeScraperConfig,
    RawSpecSyncReport,
    load_raw_spec_manifest,
    sync_raw_specs,
)

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from catalog.models import CatalogModule, CatalogSnapshot, JsonObject

REPO_ROOT = repo_root()
FIXTURE_PATH = (
    REPO_ROOT
    / "tests"
    / "catalog"
    / "fixtures"
    / "raw_specs"
    / "minimal_restore_expect_interface.json"
)
FIXED_GENERATED_AT = "2026-05-05T00:00:00+00:00"
RETENTION_MODULE_ID = module_id(
    app_slug="retention-fixture",
    app_version="1.0",
    module_kind="action",
    internal_name="createRetainedRecord",
)
EXPECTED_PARAMETER_PATHS = (
    ("account",),
    ("account", "accountId"),
    ("payload",),
    ("payload", "leadEmail"),
)
EXPECTED_EXPECT_PATHS = (("bundle",), ("bundle", "leadId"))
EXPECTED_INTERFACE_PATHS = (("result",), ("result", "recordId"))


class FixtureRawSpecSource:
    """Deterministic raw-spec source backed by the sanitized retention.

    fixture.
    """

    def __init__(self, payload: JsonObject) -> None:
        """Store one fixture payload."""
        self._payload = payload

    @staticmethod
    def list_app_versions() -> tuple[MakeRawSpecTarget, ...]:
        """Return the one app version represented by the fixture."""
        return (
            MakeRawSpecTarget(app_slug="retention-fixture", app_version="1.0"),
        )

    def fetch_app_spec(self, target: MakeRawSpecTarget) -> JsonObject:
        """Return the fixture payload for the expected target."""
        expected = MakeRawSpecTarget(
            app_slug="retention-fixture", app_version="1.0"
        )
        assert target == expected, (
            f"Unexpected raw-spec target for retention fixture: {target}"
        )
        return self._payload


def test_catalog_compiler_retains_parameters_expect_interface_and_restore(
    tmp_path: Path,
) -> None:
    """Catalog compilation keeps import-critical raw-spec collections and.

    restore evidence.
    """
    snapshot = compile_retention_fixture(tmp_path)
    module = snapshot.apps[0].versions[0].modules[0]

    assert_retention_module_collections(module)
    assert_retention_catalog_payload(snapshot)


def assert_retention_module_collections(module: CatalogModule) -> None:
    """Assert that the compiled retention module preserved field collections."""
    assert module.module_id == RETENTION_MODULE_ID, (
        f"Retention fixture compiled the wrong module: {module.module_id}"
    )
    assert (
        tuple(field.path for field in module.parameters)
        == EXPECTED_PARAMETER_PATHS
    ), f"Catalog parameters were not retained: {module.parameters}"
    assert (
        tuple(field.path for field in module.expect_schema)
        == EXPECTED_EXPECT_PATHS
    ), f"Catalog expect schema was not retained: {module.expect_schema}"
    assert (
        tuple(field.path for field in module.interface_schema)
        == EXPECTED_INTERFACE_PATHS
    ), f"Catalog interface schema was not retained: {module.interface_schema}"

    account = module.parameters[0]
    assert not (account.advanced is not True), (
        f"Catalog field lost advanced setting metadata: {account}"
    )
    assert account.raw_schema.get("restore") == {
        "mode": "connection",
        "source": "accountId",
    }, f"Catalog field raw schema lost restore evidence: {account.raw_schema}"


def assert_retention_catalog_payload(snapshot: CatalogSnapshot) -> None:
    """Assert that catalog JSON exposes advanced and restore metadata."""
    catalog_payload = catalog_snapshot_to_json(snapshot)
    app_payload = object_at(list_member(catalog_payload, "apps"), 0)
    version_payload = object_at(list_member(app_payload, "versions"), 0)
    module_payload = object_at(list_member(version_payload, "modules"), 0)
    parameter_payload = object_at(list_member(module_payload, "parameters"), 0)
    assert not (parameter_payload.get("advanced") is not True), (
        f"Catalog JSON payload lost advanced setting metadata: "
        f"{parameter_payload}"
    )
    raw_account = object_member(parameter_payload, "raw_schema")
    assert not (raw_account.get("advanced") is not True), (
        f"Catalog JSON raw schema lost advanced setting metadata: {raw_account}"
    )
    assert not ("restore" not in raw_account), (
        f"Catalog JSON payload lost restore evidence: {raw_account}"
    )
    assert not ("restore" not in KNOWN_METADATA_KEYS), (
        "AST evidence summaries must continue to recognize restore metadata."
    )


def test_catalog_storage_round_trip_retains_make_field_collections(
    tmp_path: Path,
) -> None:
    """Knowledge storage keeps the same Make field collections after a SQLite.

    build.
    """
    prepare_snapshot_dir(tmp_path)
    _ = sync_retention_fixture(tmp_path)

    report = build_knowledge_store(repo_root=tmp_path)
    query = load_knowledge_store_query(
        repo_root=tmp_path, include_structural_facts=True
    )
    fields_by_direction = {
        direction: tuple(
            field.path
            for field in query.fields
            if field.module_id == RETENTION_MODULE_ID
            and field.direction == direction
        )
        for _collection_key, direction in COMPILER_FIELD_COLLECTIONS
    }

    assert report.module_count == 1, (
        f"Knowledge storage did not ingest the retention fixture module: "
        f"{report}"
    )
    assert fields_by_direction["parameter"] == EXPECTED_PARAMETER_PATHS, (
        f"Knowledge storage lost parameters: {fields_by_direction}"
    )
    assert fields_by_direction["expect"] == EXPECTED_EXPECT_PATHS, (
        f"Knowledge storage lost expect fields: {fields_by_direction}"
    )
    assert fields_by_direction["interface"] == EXPECTED_INTERFACE_PATHS, (
        f"Knowledge storage lost interface fields: {fields_by_direction}"
    )

    raw_schema = stored_field_raw_schema(
        tmp_path, direction="parameter", path="account"
    )
    query_field = next(
        field
        for field in query.fields
        if field.module_id == RETENTION_MODULE_ID
        and field.direction == "parameter"
        and field.path == ("account",)
    )
    advanced_constraints = tuple(
        constraint
        for constraint in query.constraints_for_field(query_field.field_id)
        if constraint.constraint_key == "advanced"
    )
    assert tuple(
        constraint.value_json for constraint in advanced_constraints
    ) == ('{"advanced":true}',), (
        f"Knowledge storage lost advanced setting constraints: "
        f"{advanced_constraints}"
    )
    projected = knowledge_query_to_catalog_snapshot(
        query=query, module_ids=(RETENTION_MODULE_ID,)
    )
    projected_account = projected.apps[0].versions[0].modules[0].parameters[0]
    assert not (projected_account.advanced is not True), (
        f"Knowledge projection lost advanced setting metadata: "
        f"{projected_account}"
    )
    if projected_account.raw_schema.get("advanced") is not True:
        message = (
            "Knowledge projection raw schema lost advanced setting metadata: "
            f"{projected_account.raw_schema}"
        )
        assert not (projected_account.raw_schema.get("advanced") is not True), (
            message
        )
    assert raw_schema.get("restore") == {
        "mode": "connection",
        "source": "accountId",
    }, f"Knowledge storage raw schema lost restore evidence: {raw_schema}"


def test_field_collection_constant_is_shared_or_drift_checked() -> None:
    """Compiler and knowledge storage must share the Make field collection.

    source.
    """
    if knowledge_storage.FIELD_COLLECTIONS is not COMPILER_FIELD_COLLECTIONS:
        message = (
            "Catalog compiler and knowledge storage must share"
            "FIELD_COLLECTIONS to prevent"
        )
        assert not (
            knowledge_storage.FIELD_COLLECTIONS
            is not COMPILER_FIELD_COLLECTIONS
        ), f"{message} parameters/expect/interface drift."


def compile_retention_fixture(repo_root_path: Path) -> CatalogSnapshot:
    """Compile the sanitized retention fixture through the public compiler API.

    Returns:
        The compiled catalog snapshot.
    """
    report = sync_retention_fixture(repo_root_path)
    manifest = load_raw_spec_manifest(repo_root_path / report.manifest_path)
    return compile_catalog_from_manifest(
        repo_root=repo_root_path, manifest=manifest
    )


def sync_retention_fixture(repo_root_path: Path) -> RawSpecSyncReport:
    """Return the computed result for the caller."""
    return sync_raw_specs(
        config=MakeScraperConfig(repo_root=repo_root_path),
        source=FixtureRawSpecSource(load_fixture_payload()),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )


def load_fixture_payload() -> JsonObject:
    """Load the sanitized raw-spec retention fixture.

    Returns:
        The fixture payload.
    """
    payload = cast(
        "object", json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    )
    assert isinstance(payload, dict), (
        f"Retention fixture must contain a JSON object: {FIXTURE_PATH}"
    )
    return normalize_json_object(cast("Mapping[str, object]", payload))


def prepare_snapshot_dir(tmp_path: Path) -> None:
    """Copy tracked SQL snapshots into a temporary repository root."""
    _ = copytree(
        REPO_ROOT / DEFAULT_DB_SNAPSHOT_DIR, tmp_path / DEFAULT_DB_SNAPSHOT_DIR
    )


def stored_field_raw_schema(
    tmp_path: Path, *, direction: str, path: str
) -> JsonObject:
    """Load the raw field schema JSON stored in SQLite for one field.

    Returns:
        The stored raw schema payload.
    """
    connection = sqlite3.connect(tmp_path / DEFAULT_KNOWLEDGE_DB_PATH)
    try:
        row = cast(
            "tuple[object, ...] | None",
            connection.execute(
                """
                SELECT raw_schema_json
                FROM fields
                WHERE module_id = ?
                  AND direction = ?
                  AND path = ?
                  AND valid_to IS NULL
                """,
                (RETENTION_MODULE_ID, direction, path),
            ).fetchone(),
        )
    finally:
        connection.close()
    assert row is not None, (
        f"Stored field raw schema was missing for {direction}:{path}"
    )
    payload = cast("object", json.loads(str(row[0])))
    assert isinstance(payload, dict), (
        f"Stored field raw schema must be a JSON object: {payload}"
    )
    return normalize_json_object(cast("Mapping[str, object]", payload))


def object_member(payload: JsonObject, key: str) -> JsonObject:
    """Return one JSON object member.

    Returns:
        The selected object member.
    """
    value = payload.get(key)
    assert isinstance(value, dict), f"Expected object member {key!r}: {payload}"
    return normalize_json_object(cast("Mapping[str, object]", value))


def list_member(payload: JsonObject, key: str) -> list[object]:
    """Return one JSON list member.

    Returns:
        The selected list member.
    """
    value = payload.get(key)
    assert isinstance(value, list), f"Expected list member {key!r}: {payload}"
    return cast("list[object]", value)


def object_at(items: list[object], index: int) -> JsonObject:
    """Return one JSON object from a list.

    Returns:
        The selected object item.
    """
    item = items[index]
    assert isinstance(item, dict), f"Expected object item at {index}: {items}"
    return normalize_json_object(cast("Mapping[str, object]", item))
