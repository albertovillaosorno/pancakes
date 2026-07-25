# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Behavior tests for the Make raw-spec scraper slice.

Boundary contract:
- Owns: tests for raw-spec ingestion, sync reports, live-source adapters, and
parser guards.
- Must not: test AST rendering, PDF/media slices, or repository tools.
- Allows: injected transports, repo-local data paths, and raw-spec fixtures.
- Split when: live adapter, manifest, and parser tests need separate modules.
- Merge when: another scraper raw-spec test duplicates this ingestion coverage.
"""

from __future__ import annotations

import json
import sqlite3
from email.message import Message
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Self, cast
from urllib.error import HTTPError

import languages.make.raw_specs.manifest as raw_spec_manifest
import pytest
from languages.make.raw_specs import (
    AUTHORIZED_API_RAW_SPEC_SOURCE_METADATA,
    SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
    MakeApiClient,
    MakeApiClientConfig,
    MakeApiConfigurationError,
    MakeApiRemoteError,
    MakeLiveRawSpecSource,
    MakeLocalNativeRawSpecSource,
    MakeNativeFallbackRawSpecSource,
    MakeNativeVersionedRawSpecSource,
    MakeRawSpecTarget,
    MakeScraperConfig,
    local_native_raw_spec_slugs,
    normalize_make_external_id,
    parse_make_raw_spec,
    raw_spec_refresh_status,
    refresh_raw_specs_from_live_config,
    repo_env_values,
    require_live_ready,
    sync_raw_specs,
)
from languages.make.raw_specs.__main__ import main as raw_specs_cli_main
from languages.make.raw_specs.live.source import MAKE_PLATFORM_RAW_SPEC_SLUGS
from languages.make.raw_specs.paths import (
    DEFAULT_RAW_SPEC_DIR,
    raw_spec_file_name,
    safe_path_token,
)
from languages.make.raw_specs.sqlite_store import (
    RAW_SPEC_SQLITE_DIR,
    RAW_SPEC_SQLITE_MANIFEST_PATH,
    RAW_SPEC_UPDATE_REVIEW_PENDING_STATUS,
    RAW_SPEC_UPDATE_REVIEW_SURFACES,
    load_sqlite_raw_spec_bundle,
)

from tests.support.assertions import assert_unexpected_success
from tests.support.json_payloads import json_object_from_text
from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping
    from urllib.request import Request

    from _pytest.capture import CaptureFixture
    from languages.make.raw_specs.models import JsonObject, RawSpecRecord

FIXED_GENERATED_AT = "2026-04-28T00:00:00+00:00"
EXPECTED_MANIFEST_VERSION = 2
EXPECTED_MODULE_COUNT = 2
EXPECTED_RETRY_ATTEMPTS = 2
EXPECTED_HTTP_429_BACKOFF_ATTEMPTS = 4
EXPECTED_LIVE_REFRESH_TARGET_COUNT = 2 + len(MAKE_PLATFORM_RAW_SPEC_SLUGS) - 1
ENV_EXAMPLE = Path(".env.example")
SCRAPER_README = Path("src/languages/make/raw_specs/README.md")
DEFAULT_MANIFEST_COVERAGE = (
    repo_root() / "src/languages/make/data/default_manifest_coverage.json"
)


class InMemoryRawSpecSource:
    """Deterministic MakeRawSpecSource used by tests."""

    def __init__(self, specs: Mapping[MakeRawSpecTarget, JsonObject]) -> None:
        """Store raw spec fixtures by target."""
        self._specs = dict(specs)

    def list_app_versions(self) -> tuple[MakeRawSpecTarget, ...]:
        """Return available targets."""
        return tuple(self._specs)

    def fetch_app_spec(self, target: MakeRawSpecTarget) -> JsonObject:
        """Return one raw spec fixture."""
        return self._specs[target]


class FakeMakeApiResponse:
    """Minimal response object for live adapter tests."""

    def __init__(self, payload: bytes, *, status: int = 200) -> None:
        """Store response bytes and status."""
        self._payload = payload
        self.status = status
        self.headers: dict[str, str] = {}

    def read(self, amount: int = -1) -> bytes:
        """Return response bytes."""
        del amount
        return self._payload

    def __enter__(self) -> Self:
        """Enter response context.

        Returns:
            The result produced by enter response context.
        """
        return self

    def __exit__(
        self, exc_type: object, exc: object, tb: object
    ) -> bool | None:
        """Exit response context.

        Returns:
            The result produced by exit response context.
        """
        del exc_type, exc, tb
        return None


def make_raw_spec_payload(
    *,
    slug: str = "http",
    version: str = "1.0",
    label: str = "HTTP",
) -> JsonObject:
    """Build one representative raw Make IMT app payload.

    Returns:
        The constructed value.
    """
    return {
        "app": {
            "name": slug,
            "version": version,
            "label": label,
            "latest": True,
            "manifest": {"version": 2},
            "actions": [
                {
                    "name": "makeRequest ",
                    "label": "Make a request",
                    "parameters": [{"name": "url"}, {"name": "method"}],
                    "interface": [{"name": "statusCode"}],
                }
            ],
            "searches": [
                {
                    "name": "listRequests ",
                    "label": "List requests",
                    "expect": [{"name": "query"}],
                    "interface": [{"name": "items"}, {"name": "cursor"}],
                }
            ],
        }
    }


def fake_make_api_token() -> str:
    """Return a non-secret test credential placeholder."""
    return "test-token"


def corrupt_sqlite_raw_spec_payload(repo_path: Path) -> None:
    """Corrupt the current SQLite raw-spec payload without updating its.

    digest.
    """
    database_path = repo_path / "src/data/pancakes.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        _ = connection.execute(
            """
            UPDATE make_raw_spec_payloads
            SET payload_json = ?
            WHERE valid_to IS NULL
            """,
            ("{}",),
        )
        connection.commit()
    finally:
        connection.close()


def test_make_raw_spec_parser_extracts_app_and_module_summary() -> None:
    """Parser extracts stable app identity and module summaries."""
    parsed = parse_make_raw_spec(make_raw_spec_payload())

    assert parsed.app_slug == "http", f"Unexpected app identity: {parsed}"
    assert parsed.app_version == "1.0", f"Unexpected app identity: {parsed}"
    assert parsed.app_label == "HTTP", f"Unexpected app metadata: {parsed}"
    assert parsed.latest, f"Unexpected app metadata: {parsed}"
    assert parsed.manifest_version == EXPECTED_MANIFEST_VERSION, (
        f"Unexpected manifest version: {parsed.manifest_version}"
    )
    module_names = tuple(module.internal_name for module in parsed.modules)
    assert module_names == ("makeRequest", "listRequests"), (
        f"Unexpected module ordering: {module_names}"
    )
    module_counts = tuple(
        (module.module_kind, module.parameter_count, module.output_count)
        for module in parsed.modules
    )
    assert module_counts == (("action", 2, 1), ("search", 1, 2)), (
        f"Unexpected module counts: {module_counts}"
    )


def test_raw_spec_sync_rejects_linked_raw_spec_file_before_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raw-spec sync deletes temp artifacts and writes durable SQLite rows."""
    raw_spec_dir = tmp_path / DEFAULT_RAW_SPEC_DIR
    raw_spec_dir.mkdir(parents=True)
    linked_path = raw_spec_dir / raw_spec_file_name("http", "1.0")
    _ = linked_path.write_text("outside placeholder\n", encoding="utf-8")

    def fake_link_probe(path: Path) -> bool:
        return path == linked_path

    monkeypatch.setattr(
        raw_spec_manifest, "_path_is_filesystem_link", fake_link_probe
    )
    source = InMemoryRawSpecSource(
        {
            MakeRawSpecTarget(
                app_slug="http", app_version="1.0"
            ): make_raw_spec_payload()
        }
    )
    config = MakeScraperConfig(repo_root=tmp_path)

    _ = sync_raw_specs(
        config=config,
        source=source,
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )
    manifest = load_sqlite_manifest(tmp_path)
    assert tuple(record.app_slug for record in manifest.records) == ("http",)
    assert_raw_spec_temp_clean(tmp_path)


def test_raw_spec_sync_rejects_linked_manifest_file_before_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raw-spec sync ignores legacy manifest paths and uses SQLite only."""
    manifest_path = tmp_path / "linked-manifest.json"
    _ = manifest_path.write_text("outside placeholder\n", encoding="utf-8")

    def fake_link_probe(path: Path) -> bool:
        return path == manifest_path

    monkeypatch.setattr(
        raw_spec_manifest, "_path_is_filesystem_link", fake_link_probe
    )
    source = InMemoryRawSpecSource(
        {
            MakeRawSpecTarget(
                app_slug="http", app_version="1.0"
            ): make_raw_spec_payload()
        }
    )
    config = MakeScraperConfig(
        repo_root=tmp_path,
        raw_spec_dir=Path("raw-specs"),
        manifest_path=Path("linked-manifest.json"),
    )

    report = sync_raw_specs(
        config=config,
        source=source,
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )
    assert report.manifest_path == RAW_SPEC_SQLITE_MANIFEST_PATH
    assert manifest_path.read_text(encoding="utf-8") == "outside placeholder\n"


def test_make_raw_spec_parser_counts_5d2a487e() -> None:
    """Parser counts explicit custom and opaque module collections."""
    parsed = parse_make_raw_spec(
        {
            "app": {
                "name": "custom-client-api ",
                "version": "1.0 ",
                "label": "Custom Client API",
                "latest": True,
                "manifest": {"version": 2},
                "customModules": [
                    {
                        "name": "DoThing ",
                        "label": "Do thing",
                        "parameters": [{"name": "accountId"}],
                        "interface": [{"name": "result"}],
                    }
                ],
                "modules": [
                    {
                        "name": "OpaqueLegacy ",
                        "label": "Opaque legacy",
                        "parameters": [{"name": "payload"}],
                    }
                ],
            }
        }
    )

    module_summaries = tuple(
        (
            module.module_kind,
            module.internal_name,
            module.parameter_count,
            module.output_count,
        )
        for module in parsed.modules
    )
    assert module_summaries == (
        ("custom", "DoThing", 1, 1),
        ("unknown", "OpaqueLegacy", 1, 0),
    ), (
        f"Custom and unknown module collections were not counted: "
        f"{module_summaries}"
    )


def test_make_raw_spec_parser_counts_make_native_default_collections() -> None:
    """Parser counts Make-native default collections beyond standard IMT module.

    arrays.
    """
    parsed = parse_make_raw_spec(
        {
            "app": {
                "name": "builtin-defaults ",
                "version": "1.0 ",
                "label": "Built-in defaults",
                "latest": True,
                "manifest": {"version": 2},
                "feeders": [
                    {
                        "name": "FeedAttachments ",
                        "label": "Feed attachments",
                        "parameters": [{"name": "attachments"}],
                    }
                ],
                "convergers": [
                    {
                        "name": "BasicConverger ",
                        "label": "Flow control",
                        "interface": [{"name": "bundle"}],
                    }
                ],
                "directives": [
                    {
                        "name": "Rollback ",
                        "label": "Rollback",
                        "parameters": [{"name": "reason"}],
                    }
                ],
                "starters": [
                    {"name": "StartSubscenario", "label": "Start subscenario"}
                ],
                "returners": [{"name": "ReturnData", "label": "Return data"}],
                "agents": [{"name": "RunAgent", "label": "Run AI agent"}],
            }
        }
    )

    module_summaries = tuple(
        (
            module.module_kind,
            module.internal_name,
            module.parameter_count,
            module.output_count,
        )
        for module in parsed.modules
    )
    assert module_summaries == (
        ("action", "ReturnData", 0, 0),
        ("action", "Rollback", 1, 0),
        ("agent", "RunAgent", 0, 0),
        ("router", "BasicConverger", 0, 1),
        ("transformer", "FeedAttachments", 1, 0),
        ("trigger", "StartSubscenario", 0, 0),
    ), f"Make-native default collections were not counted: {module_summaries}"


def test_make_default_manifest_coverage_ledger_is_complete() -> None:
    """Operator Make built-in/default export coverage stays raw-spec backed."""
    payload = cast(
        "JsonObject",
        json.loads(DEFAULT_MANIFEST_COVERAGE.read_text(encoding="utf-8")),
    )
    coverage = cast("JsonObject", payload["coverage"])
    records = cast("list[JsonObject]", payload["records"])
    browser_evidence = cast("JsonObject", payload["browser_evidence"])
    redaction = cast("JsonObject", payload["redaction"])

    assert coverage["source_node_count"] == 198, (
        f"Coverage source count drifted: {coverage}"
    )
    assert coverage["unique_module_count"] == 197, (
        f"Coverage module count drifted: {coverage}"
    )
    assert coverage["raw_spec_backed_count"] == 197, (
        f"Coverage dropped raw specs: {coverage}"
    )
    assert coverage["missing_local_catalog_manifest_count"] == 0, (
        f"Built-in/default modules lost local manifest coverage: {coverage}"
    )
    assert coverage["missing_modules"] == [], (
        f"Unexpected missing modules: {coverage}"
    )
    assert len(records) == 197, f"Coverage records drifted: {len(records)}"
    assert all(record["status"] == "raw_spec_backed" for record in records), (
        f"Every coverage row must stay raw-spec backed: {records}"
    )
    assert browser_evidence["status"] == "manual_login_ready_read_only", (
        f"Browser evidence status drifted: {browser_evidence}"
    )
    assert redaction["provider_credentials"] == "not_recorded", (
        f"Coverage ledger must not record credentials: {redaction}"
    )


def test_sync_raw_specs_writes_sqlite_and_cleans_temp_json(
    tmp_path: Path,
) -> None:
    """Sync writes raw specs directly into SQLite and removes temp JSON."""
    target = MakeRawSpecTarget(app_slug="http", app_version="1.0")
    config = MakeScraperConfig(repo_root=tmp_path)
    report = sync_raw_specs(
        config=config,
        source=InMemoryRawSpecSource({target: make_raw_spec_payload()}),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )

    assert report.targets_seen == 1, f"Unexpected sync counts: {report}"
    assert report.files_written == 1, f"Unexpected sync counts: {report}"
    assert report.raw_spec_dir == RAW_SPEC_SQLITE_DIR, (
        f"Unexpected raw spec dir: {report.raw_spec_dir}"
    )
    assert report.manifest_path == RAW_SPEC_SQLITE_MANIFEST_PATH, (
        f"Unexpected manifest path: {report.manifest_path}"
    )

    manifest = load_sqlite_manifest(tmp_path)
    assert manifest.generated_at_utc == FIXED_GENERATED_AT, (
        f"Unexpected manifest timestamp: {manifest}"
    )
    assert manifest.manifest_sha256 == report.manifest_sha256, (
        "Report and manifest fingerprints diverged."
    )
    assert len(manifest.records) == 1, (
        f"Expected one manifest record: {manifest.records}"
    )

    verify_manifest_record(manifest.records[0])

    loaded_payload = load_sqlite_payload(tmp_path, manifest.records[0])
    assert not ("app" not in loaded_payload), (
        f"SQLite raw spec payload did not contain the app object: "
        f"{loaded_payload}"
    )
    assert_raw_spec_temp_clean(tmp_path)


def test_raw_spec_sync_reviews_new_and_changed_specs_without_duplicate_rows(
    tmp_path: Path,
) -> None:
    """SQLite raw-spec refresh opens reviews for changes and collapses exact.

    repeats.
    """
    target = MakeRawSpecTarget(app_slug="http", app_version="1.0")
    config = MakeScraperConfig(repo_root=tmp_path)
    first_generated_at = FIXED_GENERATED_AT
    duplicate_generated_at = "2026-04-29T00:00:00+00:00"
    changed_generated_at = "2026-04-30T00:00:00+00:00"
    _ = sync_raw_specs(
        config=config,
        source=InMemoryRawSpecSource({target: make_raw_spec_payload()}),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=first_generated_at,
    )
    _ = sync_raw_specs(
        config=config,
        source=InMemoryRawSpecSource({target: make_raw_spec_payload()}),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=duplicate_generated_at,
    )
    duplicate_manifest = load_sqlite_manifest(tmp_path)
    _ = sync_raw_specs(
        config=config,
        source=InMemoryRawSpecSource(
            {
                target: make_raw_spec_payload(label="HTTP Updated"),
            }
        ),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=changed_generated_at,
    )

    connection = sqlite3.connect(tmp_path / "src/data/pancakes.sqlite")
    try:
        payload_rows = cast(
            "list[tuple[str, str, str | None]]",
            connection.execute(
                """
                SELECT sha256, valid_from, valid_to
                FROM make_raw_spec_payloads
                WHERE app_slug = 'http' AND app_version = '1.0'
                ORDER BY valid_from
                """
            ).fetchall(),
        )
        manifest_rows = cast(
            "list[tuple[str, str, str | None]]",
            connection.execute(
                """
                SELECT app_label, valid_from, valid_to
                FROM make_raw_spec_manifest_records
                WHERE app_slug = 'http' AND app_version = '1.0'
                ORDER BY valid_from
                """
            ).fetchall(),
        )
        review_rows = cast(
            "list[tuple[str, str, str, str, str, str, str | None]]",
            connection.execute(
                """
                SELECT
                  update_kind,
                  review_status,
                  review_surfaces_json,
                  source_sha256,
                  previous_sha256,
                  previous_valid_from,
                  valid_to
                FROM make_raw_spec_update_reviews
                WHERE app_slug = 'http' AND app_version = '1.0'
                ORDER BY valid_from
                """
            ).fetchall(),
        )
    finally:
        connection.close()

    assert len(payload_rows) == 2, (
        f"Exact duplicate raw specs must not create extra payload rows: "
        f"{payload_rows}"
    )
    assert duplicate_manifest.generated_at_utc == duplicate_generated_at, (
        f"Exact duplicate refreshes must advance current manifest freshness: "
        f"{duplicate_manifest}"
    )
    assert payload_rows[0][1:] == (first_generated_at, changed_generated_at), (
        f"Changed raw specs must close the older current row: {payload_rows}"
    )
    assert payload_rows[1][1:] == (changed_generated_at, None), (
        f"Changed raw specs must become the current row: {payload_rows}"
    )
    assert manifest_rows == [
        ("HTTP", first_generated_at, duplicate_generated_at),
        ("HTTP", duplicate_generated_at, changed_generated_at),
        ("HTTP Updated", changed_generated_at, None),
    ], (
        f"Manifest history did not retain the changed raw-spec versions: "
        f"{manifest_rows}"
    )
    assert [row[0] for row in review_rows] == [
        "new_raw_spec ",
        "changed_raw_spec",
    ], f"Refresh should review only new or changed raw specs: {review_rows}"
    assert review_rows[0][1] == RAW_SPEC_UPDATE_REVIEW_PENDING_STATUS
    assert review_rows[1][1] == RAW_SPEC_UPDATE_REVIEW_PENDING_STATUS
    assert (
        review_surfaces_from_json(review_rows[0][2])
        == RAW_SPEC_UPDATE_REVIEW_SURFACES
    )
    assert (
        review_surfaces_from_json(review_rows[1][2])
        == RAW_SPEC_UPDATE_REVIEW_SURFACES
    )
    assert review_rows[0][6] == changed_generated_at, (
        f"The newer review should close the older current review: {review_rows}"
    )
    assert review_rows[1][4] == payload_rows[0][0], (
        f"Changed review must point at the prior payload digest: {review_rows}"
    )
    assert review_rows[1][5] == first_generated_at, (
        f"Changed review must point at the prior valid_from timestamp: "
        f"{review_rows}"
    )
    assert review_rows[1][6] is None, (
        f"Latest changed review should remain pending: {review_rows}"
    )


def test_raw_spec_sync_rejects_changed_specs_with_reused_timestamps(
    tmp_path: Path,
) -> None:
    """Changed raw specs need a fresh timestamp so prior SQLite rows are.

    retained.
    """
    target = MakeRawSpecTarget(app_slug="http", app_version="1.0")
    config = MakeScraperConfig(repo_root=tmp_path)
    _ = sync_raw_specs(
        config=config,
        source=InMemoryRawSpecSource({target: make_raw_spec_payload()}),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )

    with pytest.raises(RuntimeError, match="generated_at_utc"):
        _ = sync_raw_specs(
            config=config,
            source=InMemoryRawSpecSource(
                {
                    target: make_raw_spec_payload(label="HTTP Updated"),
                }
            ),
            source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
            generated_at_utc=FIXED_GENERATED_AT,
        )

    connection = sqlite3.connect(tmp_path / "src/data/pancakes.sqlite")
    try:
        payload_rows = cast(
            "list[tuple[str, str | None]]",
            connection.execute(
                """
                SELECT valid_from, valid_to
                FROM make_raw_spec_payloads
                WHERE app_slug = 'http' AND app_version = '1.0'
                """
            ).fetchall(),
        )
    finally:
        connection.close()

    assert payload_rows == [(FIXED_GENERATED_AT, None)], (
        f"Failed same-timestamp changes must preserve the prior current row: "
        f"{payload_rows}"
    )


def test_raw_spec_manifest_latest_metadata_uses_current_index(
    tmp_path: Path,
) -> None:
    """The raw-spec manifest metadata lookup uses its current-row timestamp.

    index.
    """
    target = MakeRawSpecTarget(app_slug="http", app_version="1.0")
    config = MakeScraperConfig(repo_root=tmp_path)
    _ = sync_raw_specs(
        config=config,
        source=InMemoryRawSpecSource({target: make_raw_spec_payload()}),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )

    database_path = tmp_path / "src/data/pancakes.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        index_rows = cast(
            "list[tuple[str]]",
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall(),
        )
        query_plan_rows = cast(
            "list[tuple[int, int, int, str]]",
            connection.execute(
                """
                EXPLAIN QUERY PLAN
                SELECT generated_at_utc
                FROM make_raw_spec_manifest_records
                WHERE valid_to IS NULL
                ORDER BY generated_at_utc DESC
                LIMIT 1
                """
            ).fetchall(),
        )
        index_names = {str(row[0]) for row in index_rows}
        query_plan = " ".join(str(row[3]) for row in query_plan_rows)
    finally:
        connection.close()

    assert (
        "idx_make_raw_spec_manifest_records_latest_metadata" in index_names
    ), f"Raw-spec manifest latest metadata index is missing: {index_names}"
    assert "idx_make_raw_spec_manifest_records_latest_metadata" in query_plan, (
        f"Raw-spec manifest latest metadata lookup is not indexed: {query_plan}"
    )


def test_sync_raw_specs_skips_empty_authorized_api_records(
    tmp_path: Path,
) -> None:
    """Authenticated metadata-only app records do not enter the local.

    manifest.
    """
    useful_target = MakeRawSpecTarget(app_slug="http", app_version="1.0")
    empty_target = MakeRawSpecTarget(
        app_slug="metadata-only", app_version="1.0"
    )
    config = MakeScraperConfig(repo_root=tmp_path)

    report = sync_raw_specs(
        config=config,
        source=InMemoryRawSpecSource(
            {
                useful_target: make_raw_spec_payload(),
                empty_target: {
                    "app": {
                        "name": "metadata-only ",
                        "version": "1.0 ",
                        "label": "Metadata Only",
                        "latest": True,
                        "manifest": {"version": 2},
                    }
                },
            }
        ),
        source_metadata=AUTHORIZED_API_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )

    manifest = load_sqlite_manifest(tmp_path)
    assert report.targets_seen == 2, f"Unexpected sync counts: {report}"
    assert report.files_written == 1, f"Unexpected sync counts: {report}"
    assert tuple(record.app_slug for record in manifest.records) == ("http",), (
        f"Empty authenticated records must be excluded from the manifest: "
        f"{manifest.records}"
    )
    assert_raw_spec_temp_clean(tmp_path)


def test_sync_raw_specs_keeps_custom_only_authorized_records(
    tmp_path: Path,
) -> None:
    """Authenticated custom-only app records are not misclassified as empty.

    metadata.
    """
    target = MakeRawSpecTarget(app_slug="custom-client-api", app_version="1.0")
    config = MakeScraperConfig(repo_root=tmp_path)

    report = sync_raw_specs(
        config=config,
        source=InMemoryRawSpecSource(
            {
                target: {
                    "app": {
                        "name": "custom-client-api ",
                        "version": "1.0 ",
                        "label": "Custom Client API",
                        "latest": True,
                        "manifest": {"version": 2},
                        "customModules": [
                            {
                                "name": "DoThing ",
                                "label": "Do thing",
                                "parameters": [{"name": "payload"}],
                            }
                        ],
                    }
                }
            }
        ),
        source_metadata=AUTHORIZED_API_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )

    manifest = load_sqlite_manifest(tmp_path)
    assert report.targets_seen == 1, f"Unexpected sync counts: {report}"
    assert report.files_written == 1, f"Unexpected sync counts: {report}"
    assert len(manifest.records) == 1, (
        f"Expected one manifest record: {manifest.records}"
    )
    assert manifest.records[0].module_count == 1, (
        f"Unexpected manifest: {manifest.records[0]}"
    )
    assert manifest.records[0].module_kinds == ("custom",), (
        f"Unexpected manifest: {manifest.records[0]}"
    )
    assert_raw_spec_temp_clean(tmp_path)


def test_sync_raw_specs_reports_target_when_payload_shape_fails(
    tmp_path: Path,
) -> None:
    """Sync failures include the exact app target that stopped the refresh."""
    target = MakeRawSpecTarget(app_slug="broken-app", app_version="current")
    config = MakeScraperConfig(repo_root=tmp_path)

    with pytest.raises(
        RuntimeError, match="app_slug='broken-app' app_version='current'"
    ):
        _ = sync_raw_specs(
            config=config,
            source=InMemoryRawSpecSource({target: {"error": "missing app"}}),
            source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
            generated_at_utc=FIXED_GENERATED_AT,
        )


def test_parse_raw_spec_rejects_non_boolean_latest() -> None:
    """Raw-spec parsing must not coerce truthy text into latest=true."""
    payload = make_raw_spec_payload()
    app = cast("JsonObject", payload["app"])
    app["latest"] = "false"

    with pytest.raises(TypeError, match="latest"):
        _ = parse_make_raw_spec(payload)


def test_parse_raw_spec_rejects_non_text_app_identity() -> None:
    """Raw-spec parsing must not stringify malformed app identity fields."""
    payload = make_raw_spec_payload()
    app = cast("JsonObject", payload["app"])
    app["name"] = 123

    with pytest.raises(ValueError, match="name"):
        _ = parse_make_raw_spec(payload)


def test_parse_raw_spec_does_not_stringify_module_names() -> None:
    """Malformed module names are not normalized into fake module identities."""
    payload = make_raw_spec_payload()
    app = cast("JsonObject", payload["app"])
    actions = cast("list[JsonObject]", app["actions"])
    actions[0]["name"] = 123

    parsed = parse_make_raw_spec(payload)

    module_names = tuple(module.internal_name for module in parsed.modules)
    assert "123" not in module_names, (
        f"Malformed module names must not be stringified: {module_names}"
    )
    assert module_names == ("listRequests",), (
        f"Malformed module names must not be stringified: {module_names}"
    )


def test_sqlite_manifest_loader_rejects_non_integer_latest(
    tmp_path: Path,
) -> None:
    """SQLite manifest loading must not coerce truthy text into latest=true."""
    target = MakeRawSpecTarget(app_slug="http", app_version="1.0")
    config = MakeScraperConfig(repo_root=tmp_path)
    _ = sync_raw_specs(
        config=config,
        source=InMemoryRawSpecSource({target: make_raw_spec_payload()}),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )
    database_path = tmp_path / "src/data/pancakes.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        _ = connection.execute(
            "UPDATE make_raw_spec_manifest_records SET latest = 'false'"
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ValueError, match="invalid literal"):
        _ = load_sqlite_raw_spec_bundle(database_path=database_path)


def load_sqlite_manifest(repo_root: Path) -> object:
    """Return the current SQLite raw-spec manifest for assertions."""
    bundle = load_sqlite_raw_spec_bundle(
        database_path=repo_root / "src/data/pancakes.sqlite",
    )
    assert bundle is not None, "Expected raw-spec bundle in Pancakes SQLite."
    return bundle.manifest


def load_sqlite_payload(repo_root: Path, record: RawSpecRecord) -> JsonObject:
    """Return one raw-spec payload from the SQLite SSOT."""
    bundle = load_sqlite_raw_spec_bundle(
        database_path=repo_root / "src/data/pancakes.sqlite",
    )
    assert bundle is not None, "Expected raw-spec bundle in Pancakes SQLite."
    return bundle.payloads_by_ref[record.relative_path]


def review_surfaces_from_json(payload_text: str) -> tuple[str, ...]:
    """Return review surfaces from a SQLite JSON list."""
    payload = cast("object", json.loads(payload_text))
    assert isinstance(payload, list), (
        f"Review surfaces must be a list: {payload!r}"
    )
    return tuple(str(item) for item in cast("list[object]", payload))


def assert_raw_spec_temp_clean(repo_root: Path) -> None:
    """Assert raw-spec JSON temp files were deleted after SQLite ingest."""
    assert not (repo_root / DEFAULT_RAW_SPEC_DIR).exists(), (
        "Raw-spec temp files must be deleted after SQLite ingest."
    )


def verify_manifest_record(record: RawSpecRecord) -> None:
    """Verify one manifest record for the HTTP fixture."""
    assert record.relative_path == f"{RAW_SPEC_SQLITE_DIR}/http__1.0", (
        f"Unexpected record path: {record.relative_path}"
    )
    assert record.source_metadata == SYNTHETIC_RAW_SPEC_SOURCE_METADATA, (
        f"Raw-spec record lost required source metadata: "
        f"{record.source_metadata}"
    )
    assert record.module_count == EXPECTED_MODULE_COUNT, (
        f"Unexpected module manifest: {record}"
    )
    assert record.module_kinds == ("action", "search"), (
        f"Unexpected module manifest: {record}"
    )


def require_escaping_raw_spec_dir_failure(config: MakeScraperConfig) -> None:
    """Fail unless an escaping raw-spec directory is rejected."""
    unexpected_path = config.resolved_raw_spec_dir()
    failure_message = f"Escaping path should have failed: {unexpected_path}"
    assert_unexpected_success(failure_message)


def test_scraper_config_rejects_paths_outside_repository(
    tmp_path: Path,
) -> None:
    """Config path resolution blocks writes outside the checkout."""
    config = MakeScraperConfig(
        repo_root=tmp_path, raw_spec_dir=Path("../outside")
    )
    with pytest.raises(ValueError, match="escapes"):
        require_escaping_raw_spec_dir_failure(config)


def test_scraper_config_rejects_manifest_paths_outside_repository(
    tmp_path: Path,
) -> None:
    """Config manifest path resolution blocks writes outside the checkout."""
    config = MakeScraperConfig(
        repo_root=tmp_path, manifest_path=Path("../manifest.json")
    )
    with pytest.raises(ValueError, match="escapes"):
        _ = config.resolved_manifest_path()


def require_invalid_pacing_failure(tmp_path: Path) -> None:
    """Fail unless invalid pacing configuration is rejected."""
    unexpected_config = MakeScraperConfig.from_env(
        tmp_path,
        {"MAKE_IMT_APPS_PER_MINUTE": "0"},
    )
    failure_message = f"Invalid pacing should have failed: {unexpected_config}"
    assert_unexpected_success(failure_message)


def test_scraper_live_mode_requires_explicit_safe_credentials(
    tmp_path: Path,
) -> None:
    """Live scraping is disabled by default and requires explicit.

    credentials.
    """
    default_config = MakeScraperConfig.from_env(tmp_path, {})
    assert not (default_config.live_enabled), (
        f"Default config must not enable live scraping: {default_config}"
    )
    assert not (default_config.api_token is not None), (
        f"Default config must not enable live scraping: {default_config}"
    )
    with pytest.raises(RuntimeError, match="disabled"):
        require_live_ready(default_config)

    with pytest.raises(ValueError, match="positive"):
        require_invalid_pacing_failure(tmp_path)

    live_config = MakeScraperConfig.from_env(
        tmp_path,
        {
            "MAKE_LIVE_SCRAPER_ENABLED": "true ",
            "MAKE_API_TOKEN": "token ",
            "MAKE_ZONE": "eu1.make.com",
            "MAKE_ORGANIZATION_ID": "123",
        },
    )
    require_live_ready(live_config)


def test_scraper_service_env_file_loads_repo_local_credentials(
    tmp_path: Path,
) -> None:
    """Service processes can load ignored repo-local scraper env defaults."""
    env_path = tmp_path / ".env"
    _ = env_path.write_text(
        f"""MAKE_LIVE_SCRAPER_ENABLED=true

MAKE_API_TOKEN={fake_make_api_token()}
MAKE_ZONE=eu1.make.com
MAKE_ORGANIZATION_ID=123
MAKE_IMT_APPS_PER_MINUTE=15
""",
        encoding="utf-8",
    )

    values = repo_env_values(
        repo_root=tmp_path, env={"MAKE_ZONE": "us1.make.com"}
    )
    assert values["MAKE_API_TOKEN"] == fake_make_api_token(), (
        f"Unexpected repo env merge result: {values}"
    )
    assert values["MAKE_ZONE"] == "us1.make.com", (
        f"Unexpected repo env merge result: {values}"
    )

    config = MakeScraperConfig.from_repo_env(
        tmp_path, env={"MAKE_ZONE": "us1.make.com"}
    )
    assert config.live_enabled, (
        f"Repo env config did not load service credentials: {config}"
    )
    assert config.zone == "us1.make.com", (
        f"Repo env config did not load service credentials: {config}"
    )


def test_scraper_env_file_parse_errors_redact_raw_lines(tmp_path: Path) -> None:
    """Malformed env-file lines must not echo secret-looking content."""
    unsafe_line = "sk-" + ("E" * 24)
    _ = (tmp_path / ".env").write_text(unsafe_line, encoding="utf-8")

    with pytest.raises(ValueError, match="raw env line is redacted") as error:
        _ = repo_env_values(repo_root=tmp_path, env={})

    message = str(error.value)
    assert unsafe_line not in message, (
        f"Malformed env line leaked into exception: {message}"
    )
    assert "raw env line is redacted" in message, (
        f"Malformed env line exception should explain redaction: {message}"
    )


def test_scraper_invalid_pacing_errors_redact_raw_values(
    tmp_path: Path,
) -> None:
    """Invalid pacing values must not echo secret-looking env values."""
    unsafe_value = "sk-" + ("P" * 24)

    with pytest.raises(ValueError, match="raw env value is redacted") as error:
        _ = MakeScraperConfig.from_env(
            tmp_path,
            {"MAKE_IMT_APPS_PER_MINUTE": unsafe_value},
        )

    message = str(error.value)
    assert unsafe_value not in message, (
        f"Invalid pacing value leaked into exception: {message}"
    )
    assert "raw env value is redacted" in message, (
        f"Invalid pacing exception should explain redaction: {message}"
    )


def test_scraper_preserves_large_make_external_identifiers(
    tmp_path: Path,
) -> None:
    """Large Make identifiers stay as lossless decimal text."""
    largest_external_id = "1844674407370955161618446744073709551616"
    live_config = MakeScraperConfig.from_env(
        tmp_path,
        {
            "MAKE_LIVE_SCRAPER_ENABLED": "true ",
            "MAKE_API_TOKEN": "token ",
            "MAKE_ZONE": "eu1.make.com",
            "MAKE_ORGANIZATION_ID": largest_external_id,
        },
    )

    assert live_config.organization_id == largest_external_id, (
        f"Organization ID was not preserved: {live_config.organization_id}"
    )
    assert normalize_make_external_id(123, field_name="sample") == "123", (
        "Integer Make IDs should normalize to decimal text."
    )


def test_scraper_rejects_invalid_make_external_identifiers(
    tmp_path: Path,
) -> None:
    """Make external IDs fail closed before any live adapter can use them."""
    with pytest.raises(ValueError, match="decimal digits"):
        _ = MakeScraperConfig.from_env(
            tmp_path, {"MAKE_ORGANIZATION_ID": "abc"}
        )
    invalid_boolean: object = True
    with pytest.raises(TypeError, match="boolean"):
        _ = normalize_make_external_id(invalid_boolean, field_name="sample")


def test_env_example_documents_scraper_without_secret_values() -> None:
    """Env example documents provider credentials without owning service.

    runtime.

    config.
    """
    env_text = ENV_EXAMPLE.read_text(encoding="utf-8")
    required_lines = {
        "MAKE_API_TOKEN=",
        "MAKE_ZONE=",
        "MAKE_ORGANIZATION_ID=",
    }
    missing_lines = sorted(required_lines.difference(env_text.splitlines()))
    assert not (missing_lines), (
        f".env.example is missing Make credential lines: {missing_lines}"
    )
    service_runtime_lines = {
        "MAKE_RAW_SPEC_DIR",
        "MAKE_RAW_SPEC_MANIFEST",
        "MAKE_IMT_APPS_PER_MINUTE",
        "MAKE_LIVE_SCRAPER_ENABLED",
    }
    misplaced_lines = sorted(
        line.split("=", maxsplit=1)[0]
        for line in env_text.splitlines()
        if line.split("=", maxsplit=1)[0] in service_runtime_lines
    )
    assert not misplaced_lines, (
        "Pancakes .env.example must not own Windows-service scraper runtime "
        "config: "
        f"{misplaced_lines}"
    )
    assert "AXIOM" not in env_text, (
        ".env.example must not use legacy Axiom branding."
    )


def test_make_scraper_readme_documents_manual_dry_run_boundary() -> None:
    """Scraper readme documents the manual source-injected dry run."""
    readme_text = SCRAPER_README.read_text(encoding="utf-8")
    required_fragments = (
        "MakeRawSpecSource ",
        "sync_raw_specs ",
        "src/data/pancakes.sqlite ",
        "API scraping stays disabled by default ",
        "python -B -m languages.make.raw_specs",
    )
    missing_fragments = [
        fragment
        for fragment in required_fragments
        if fragment not in readme_text
    ]
    assert not (missing_fragments), (
        f"Scraper readme is missing: {missing_fragments}"
    )


def test_raw_spec_path_tokens_are_windows_safe() -> None:
    """Raw spec filenames use sanitized path tokens."""
    assert safe_path_token("../") == "spec", (
        "Unsafe path tokens must fall back to a safe value."
    )
    assert raw_spec_file_name("HTTP/Web", "1:0") == "HTTPWeb__10.json", (
        "Raw spec file names must remove path separators and punctuation."
    )


def test_sqlite_loader_rejects_tampered_payload(tmp_path: Path) -> None:
    """SQLite loading rejects payload changes that do not update the digest."""
    target = MakeRawSpecTarget(app_slug="http", app_version="1.0")
    _ = sync_raw_specs(
        config=MakeScraperConfig(repo_root=tmp_path),
        source=InMemoryRawSpecSource({target: make_raw_spec_payload()}),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )
    database_path = tmp_path / "src/data/pancakes.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        _ = connection.execute(
            "UPDATE make_raw_spec_payloads SET payload_json = ?",
            ('{"app":{"name":"tampered","version":"1.0"}}',),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ValueError, match="hash mismatch"):
        _ = load_sqlite_raw_spec_bundle(database_path=database_path)


def test_make_live_raw_spec_source_uses_documented_imt_endpoints() -> None:
    """The live source adapter maps Make IMT index and detail calls into raw.

    specs.
    """
    observed_urls: list[str] = []

    def fake_open(
        request: Request, timeout_seconds: float
    ) -> FakeMakeApiResponse:
        del timeout_seconds
        observed_urls.append(request.full_url)
        if request.full_url.endswith(
            "/imt/apps?organizationId=123&search=notion"
        ):
            return FakeMakeApiResponse(
                b'{"apps":[{"name":"notion","version":"1.0"},{"name":"slack","version":"2.0"}]}'
            )
        if request.full_url.endswith("/imt/apps/notion/1.0"):
            return FakeMakeApiResponse(
                b'{"app":{"name":"notion","version":"1.0"}}'
            )
        failure_message = f"Unexpected Make API request: {request.full_url}"
        assert_unexpected_success(failure_message)
        return None

    client = MakeApiClient(
        MakeApiClientConfig(
            api_token=fake_make_api_token(), zone="eu1.make.com"
        ),
        opener=fake_open,
    )
    source = MakeLiveRawSpecSource(
        client=client,
        organization_id="123",
        search="notion",
        limit=1,
    )

    targets = source.list_app_versions()
    assert targets == (
        MakeRawSpecTarget(app_slug="notion", app_version="1.0"),
    ), f"Unexpected live source targets: {targets}"
    payload = source.fetch_app_spec(targets[0])
    assert payload == {"app": {"name": "notion", "version": "1.0"}}, (
        f"Unexpected fetched raw spec: {payload}"
    )
    assert observed_urls == [
        (
            "https://eu1.make.com/api/v2/imt/"
            "apps?organizationId=123&search=notion "
        ),
        "https://eu1.make.com/api/v2/imt/apps/notion/1.0",
    ], f"Unexpected live source URLs: {observed_urls}"


def test_make_live_raw_spec_source_expands_nested_version_summaries() -> None:
    """The live source accepts index summaries that carry versions as nested.

    items.
    """

    def fake_open(
        request: Request, timeout_seconds: float
    ) -> FakeMakeApiResponse:
        del timeout_seconds
        if request.full_url.endswith("/imt/apps?organizationId=123"):
            return FakeMakeApiResponse(
                b'{"apps":[{"slug":"custom-mail","versions":[{"version":"1.0"},{"name":"2.0"}]}]}'
            )
        failure_message = f"Unexpected Make API request: {request.full_url}"
        assert_unexpected_success(failure_message)
        return None

    client = MakeApiClient(
        MakeApiClientConfig(
            api_token=fake_make_api_token(), zone="eu1.make.com"
        ),
        opener=fake_open,
    )
    source = MakeLiveRawSpecSource(
        client=client,
        organization_id="123",
        include_platform_targets=False,
    )

    targets = source.list_app_versions()
    assert targets == (
        MakeRawSpecTarget(app_slug="custom-mail", app_version="1.0"),
        MakeRawSpecTarget(app_slug="custom-mail", app_version="2.0"),
    ), f"Unexpected nested-version targets: {targets}"


def test_make_live_raw_spec_source_a4652107() -> None:
    """The live source uses the current IMT detail endpoint when the index has.

    no versions.
    """
    observed_urls: list[str] = []

    def fake_open(
        request: Request, timeout_seconds: float
    ) -> FakeMakeApiResponse:
        del timeout_seconds
        observed_urls.append(request.full_url)
        if request.full_url.endswith("/imt/apps?organizationId=123"):
            return FakeMakeApiResponse(
                b'{"apps":[{"name":"HTTP","label":"HTTP"}]}'
            )
        if request.full_url.endswith("/imt/apps/http"):
            return FakeMakeApiResponse(b'{"app":{"name":"http","version":"1"}}')
        failure_message = f"Unexpected Make API request: {request.full_url}"
        assert_unexpected_success(failure_message)
        return None

    client = MakeApiClient(
        MakeApiClientConfig(
            api_token=fake_make_api_token(), zone="eu1.make.com"
        ),
        opener=fake_open,
    )
    source = MakeLiveRawSpecSource(
        client=client,
        organization_id="123",
        include_platform_targets=False,
    )

    targets = source.list_app_versions()
    assert targets == (
        MakeRawSpecTarget(app_slug="http", app_version="current"),
    ), f"Unexpected current-version targets: {targets}"
    payload = source.fetch_app_spec(targets[0])
    assert payload == {"app": {"name": "http", "version": "1"}}, (
        f"Unexpected current raw spec payload: {payload}"
    )
    assert observed_urls == [
        "https://eu1.make.com/api/v2/imt/apps?organizationId=123 ",
        "https://eu1.make.com/api/v2/imt/apps/http",
    ], f"Unexpected current raw spec URLs: {observed_urls}"


def test_make_api_client_rejects_imt_path_token_injection() -> None:
    """Authenticated IMT detail calls must not allow path or query segment.

    injection.
    """
    observed_urls: list[str] = []

    def fake_open(
        request: Request, timeout_seconds: float
    ) -> FakeMakeApiResponse:
        del timeout_seconds
        observed_urls.append(request.full_url)
        failure_message = (
            f"Unsafe Make API request was opened: {request.full_url}"
        )
        assert_unexpected_success(failure_message)
        return None

    client = MakeApiClient(
        MakeApiClientConfig(
            api_token=fake_make_api_token(), zone="eu1.make.com"
        ),
        opener=fake_open,
    )

    with pytest.raises(MakeApiConfigurationError, match="app_slug"):
        _ = client.get_imt_app(
            app_slug="../users?includeSecrets=true", app_version="current"
        )
    with pytest.raises(MakeApiConfigurationError, match="app_version"):
        _ = client.get_imt_app_explicit_version(
            app_slug="http",
            app_version="1.0?includeSecrets=true",
        )
    assert observed_urls == []


def test_make_live_raw_spec_source_rejects_numeric_app_slugs() -> None:
    """Live discovery must not synthesize app slugs from numeric summary.

    fields.
    """

    def fake_open(
        request: Request, timeout_seconds: float
    ) -> FakeMakeApiResponse:
        del timeout_seconds
        if request.full_url.endswith("/imt/apps?organizationId=123"):
            return FakeMakeApiResponse(
                b'{"apps":[{"name":123,"version":"1.0"}]}'
            )
        failure_message = f"Unexpected Make API request: {request.full_url}"
        assert_unexpected_success(failure_message)
        return None

    client = MakeApiClient(
        MakeApiClientConfig(
            api_token=fake_make_api_token(), zone="eu1.make.com"
        ),
        opener=fake_open,
    )
    source = MakeLiveRawSpecSource(
        client=client,
        organization_id="123",
        include_platform_targets=False,
    )

    with pytest.raises(ValueError, match="missing slug fields"):
        _ = source.list_app_versions()


def test_make_live_raw_spec_source_skips_addon_app_summaries() -> None:
    """Addon index rows are not raw IMT app specs and must not become.

    targets.
    """

    def fake_open(
        request: Request, timeout_seconds: float
    ) -> FakeMakeApiResponse:
        del timeout_seconds
        if request.full_url.endswith("/imt/apps?organizationId=123"):
            return FakeMakeApiResponse(
                json.dumps(
                    {
                        "apps": [
                            {
                                "addonApp": True,
                                "name": "communityApp-2-solar-community ",
                                "type": "community",
                            },
                            {"name": "http", "version": "1.0"},
                        ],
                    }
                ).encode("utf-8")
            )
        failure_message = f"Unexpected Make API request: {request.full_url}"
        assert_unexpected_success(failure_message)
        return None

    client = MakeApiClient(
        MakeApiClientConfig(
            api_token=fake_make_api_token(), zone="eu1.make.com"
        ),
        opener=fake_open,
    )
    source = MakeLiveRawSpecSource(
        client=client,
        organization_id="123",
        include_platform_targets=False,
    )

    targets = source.list_app_versions()
    assert targets == (
        MakeRawSpecTarget(app_slug="http", app_version="1.0"),
    ), f"Unexpected addon-filtered targets: {targets}"


def test_make_live_raw_spec_source_includes_make_platform_targets() -> None:
    """Full live refresh discovery includes Make-owned platform modules."""

    def fake_open(
        request: Request, timeout_seconds: float
    ) -> FakeMakeApiResponse:
        del timeout_seconds
        if request.full_url.endswith("/imt/apps?organizationId=123"):
            return FakeMakeApiResponse(
                b'{"apps":[{"name":"slack","version":"2.0"},{"name":"http","version":"3.45.0"}]}'
            )
        failure_message = f"Unexpected Make API request: {request.full_url}"
        assert_unexpected_success(failure_message)
        return None

    client = MakeApiClient(
        MakeApiClientConfig(
            api_token=fake_make_api_token(), zone="eu1.make.com"
        ),
        opener=fake_open,
    )
    source = MakeLiveRawSpecSource(client=client, organization_id="123")

    targets = source.list_app_versions()
    target_by_slug = {target.app_slug: target for target in targets}
    assert target_by_slug["http"].app_version == "3.45.0", (
        f"Discovered platform target should not be duplicated: {targets}"
    )
    missing_platform_slugs = [
        slug
        for slug in MAKE_PLATFORM_RAW_SPEC_SLUGS
        if slug not in target_by_slug
    ]
    assert not (missing_platform_slugs), (
        f"Platform raw-spec targets were not seeded: {missing_platform_slugs}"
    )
    assert target_by_slug["builtin"].app_version == "current", (
        f"Omitted platform targets should fetch current specs: {targets}"
    )


def test_native_fallback_source_repairs_empty_platform_specs() -> None:
    """Native fallback source replaces empty Make-owned platform specs."""
    targets = tuple(
        MakeRawSpecTarget(app_slug=slug, app_version="current")
        for slug in MAKE_PLATFORM_RAW_SPEC_SLUGS
    )
    primary = InMemoryRawSpecSource(
        {
            target: {
                "app": {
                    "name": target.app_slug,
                    "version": "current",
                    "label": target.app_slug,
                    "manifest": {"version": 2},
                }
            }
            for target in targets
        }
    )
    source = MakeNativeFallbackRawSpecSource(
        primary_source=primary,
        native_fallback_source=MakeLocalNativeRawSpecSource(),
    )

    parsed_by_slug = {
        target.app_slug: parse_make_raw_spec(source.fetch_app_spec(target))
        for target in targets
    }
    missing_modules = [
        slug for slug, parsed in parsed_by_slug.items() if not parsed.modules
    ]
    assert not missing_modules, (
        f"Native fallback left platform specs metadata-only: {missing_modules}"
    )
    builtin_kinds = {
        module.module_kind for module in parsed_by_slug["builtin"].modules
    }
    assert {"action", "aggregator", "router", "transformer"} <= builtin_kinds, (
        f"Flow-control fallback did not preserve Make default topology kinds: "
        f"{builtin_kinds}"
    )


def test_local_native_source_covers_make_default_platform_modules() -> None:
    """Local native source covers Make default platform modules, not only basic.

    topology.
    """
    source = MakeLocalNativeRawSpecSource()

    assert local_native_raw_spec_slugs() == MAKE_PLATFORM_RAW_SPEC_SLUGS
    assert tuple(target.app_slug for target in source.list_app_versions()) == (
        MAKE_PLATFORM_RAW_SPEC_SLUGS
    )
    parsed_by_slug = {
        target.app_slug: parse_make_raw_spec(source.fetch_app_spec(target))
        for target in source.list_app_versions()
    }
    required_modules = {
        "ai-agent": {"RunAnAIAgent", "UpsertAIAgentContextString"},
        "ai-local-agent": {"RunLocalAIAgent"},
        "ai-provider": {"createCompletion", "runAgent"},
        "ai-tools": {"Ask", "Extract", "Summarize", "CountAndChunkText"},
        "app-runtime": {"ExecuteAction", "ExecuteSearch", "ExecuteHookTrigger"},
        "builtin": {
            "BasicRouter ",
            "BasicIfElse ",
            "BasicAggregator ",
            "Iterator",
        },
        "csv": {"ParseCSV", "CreateAggregator"},
        "datastore": {"AddRecord", "SearchRecord", "Stats"},
        "http": {"MakeRequest", "DownloadFile", "ResolveUrl"},
        "json": {"ParseJSON", "CreateJSON", "AggregateToJSON"},
        "regexp": {"Parser", "Replace", "HTMLToText", "GetElementsFromText"},
        "util": {
            "ComposeTransformer ",
            "TextAggregator ",
            "BasicTrigger ",
            "SetVariable2",
        },
        "xml": {"ParseXML", "TransformToXML", "XPathQuery"},
    }
    for slug, module_names in required_modules.items():
        observed = {
            module.internal_name for module in parsed_by_slug[slug].modules
        }
        assert module_names <= observed, (
            f"Local native default modules for {slug} are incomplete: "
            f"{observed}"
        )

    required_kinds = {
        "ai-local-agent": {"agent"},
        "app-runtime": {"action", "search", "trigger"},
        "builtin": {"action", "aggregator", "router", "transformer"},
        "csv": {"aggregator", "transformer"},
        "regexp": {"transformer"},
        "util": {"action", "aggregator", "transformer", "trigger"},
        "xml": {"search", "transformer"},
    }
    for slug, module_kinds in required_kinds.items():
        observed = {
            module.module_kind for module in parsed_by_slug[slug].modules
        }
        assert module_kinds <= observed, (
            f"Local native default module kinds for {slug} are incomplete: "
            f"{observed}"
        )


def test_native_versioned_source_uses_local_a92022c0() -> None:
    """Versioned fallback source uses local platform payloads after empty.

    explicit specs.
    """
    observed_urls: list[str] = []

    def fake_open(
        request: Request, timeout_seconds: float
    ) -> FakeMakeApiResponse:
        del timeout_seconds
        observed_urls.append(request.full_url)
        if request.full_url.endswith("/imt/apps/ai-tools/current"):
            return FakeMakeApiResponse(
                b'{"app":{"name":"ai-tools","version":"current","manifest":{"version":2}}}'
            )
        failure_message = f"Unexpected Make API request: {request.full_url}"
        assert_unexpected_success(failure_message)
        return None

    client = MakeApiClient(
        MakeApiClientConfig(
            api_token=fake_make_api_token(), zone="eu1.make.com"
        ),
        opener=fake_open,
    )
    source = MakeNativeVersionedRawSpecSource(client=client)

    payload = source.fetch_app_spec(
        MakeRawSpecTarget(app_slug="ai-tools", app_version="current")
    )

    parsed = parse_make_raw_spec(payload)
    assert {"Ask", "Extract", "Summarize"} <= {
        module.internal_name for module in parsed.modules
    }, f"Versioned fallback did not use the local AI Toolkit payload: {parsed}"
    assert observed_urls == [
        "https://eu1.make.com/api/v2/imt/apps/ai-tools/current",
    ], f"Unexpected versioned fallback requests: {observed_urls}"


def test_live_refresh_uses_local_native_source_for_platform_search(
    tmp_path: Path,
) -> None:
    """Search-scoped platform refreshes use the local default manifest without.

    live HTTP.
    """
    observed_urls: list[str] = []

    def fake_open(
        request: Request, timeout_seconds: float
    ) -> FakeMakeApiResponse:
        del timeout_seconds
        observed_urls.append(request.full_url)
        failure_message = f"Unexpected Make API request: {request.full_url}"
        assert_unexpected_success(failure_message)
        return None

    config = MakeScraperConfig.from_env(
        tmp_path,
        {
            "MAKE_LIVE_SCRAPER_ENABLED": "true",
            "MAKE_API_TOKEN": fake_make_api_token(),
            "MAKE_ZONE": "eu1.make.com",
            "MAKE_ORGANIZATION_ID": "123",
        },
    )
    client = MakeApiClient(
        MakeApiClientConfig(
            api_token=fake_make_api_token(), zone="eu1.make.com"
        ),
        opener=fake_open,
    )

    _ = refresh_raw_specs_from_live_config(
        config=config,
        client=client,
        search="ai-tools",
        generated_at_utc=FIXED_GENERATED_AT,
    )

    manifest = load_sqlite_manifest(tmp_path)
    assert tuple(record.app_slug for record in manifest.records) == (
        "ai-tools",
    ), (
        f"Search-scoped local refresh wrote unexpected records: "
        f"{manifest.records}"
    )
    assert manifest.records[0].module_count >= 9, (
        f"Local platform refresh did not populate AI Toolkit modules: "
        f"{manifest}"
    )
    assert manifest.records[0].module_kinds == ("action",), (
        f"AI Toolkit local refresh should expose action modules: {manifest}"
    )
    assert observed_urls == [], (
        f"Local platform search should not call Make: {observed_urls}"
    )


def test_local_native_search_refresh_preserves_existing_manifest_records(
    tmp_path: Path,
) -> None:
    """Local native search refreshes replace same-app stale records only."""
    initial_target = MakeRawSpecTarget(app_slug="http", app_version="1.0")
    stale_native_target = MakeRawSpecTarget(
        app_slug="ai-provider", app_version="0.3.0"
    )
    _ = sync_raw_specs(
        config=MakeScraperConfig(repo_root=tmp_path),
        source=InMemoryRawSpecSource(
            {
                initial_target: make_raw_spec_payload(),
                stale_native_target: {
                    "app": {
                        "name": "ai-provider ",
                        "version": "0.3.0 ",
                        "label": "Make's AI Provider",
                        "latest": True,
                        "manifest": {"version": 1},
                    }
                },
            }
        ),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )

    def fake_open(
        request: Request, timeout_seconds: float
    ) -> FakeMakeApiResponse:
        del timeout_seconds
        failure_message = f"Unexpected Make API request: {request.full_url}"
        assert_unexpected_success(failure_message)
        return None

    config = MakeScraperConfig.from_env(
        tmp_path,
        {
            "MAKE_LIVE_SCRAPER_ENABLED": "true",
            "MAKE_API_TOKEN": fake_make_api_token(),
            "MAKE_ZONE": "eu1.make.com",
            "MAKE_ORGANIZATION_ID": "123",
        },
    )
    client = MakeApiClient(
        MakeApiClientConfig(
            api_token=fake_make_api_token(), zone="eu1.make.com"
        ),
        opener=fake_open,
    )

    _ = refresh_raw_specs_from_live_config(
        config=config,
        client=client,
        search="ai-provider",
        generated_at_utc="2026-04-30T00:00:00+00:00",
    )

    manifest = load_sqlite_manifest(tmp_path)
    assert tuple(record.app_slug for record in manifest.records) == (
        "ai-provider ",
        "http",
    ), f"Search refresh replaced unrelated manifest records: {manifest.records}"
    ai_provider = manifest.records[0]
    assert ai_provider.app_version == "current", (
        f"Search refresh preserved stale same-app native records: "
        f"{manifest.records}"
    )
    assert ai_provider.module_kinds == ("action", "agent"), (
        f"Native local fallback did not repair scoped refresh: {ai_provider}"
    )


def test_live_refresh_command_fetches_all_targets_by_default(
    tmp_path: Path,
) -> None:
    """The live refresh command downloads every discovered raw-spec target by.

    default.
    """
    observed_urls: list[str] = []

    def fake_open(
        request: Request, timeout_seconds: float
    ) -> FakeMakeApiResponse:
        del timeout_seconds
        observed_urls.append(request.full_url)
        if request.full_url.endswith("/imt/apps?organizationId=123"):
            payload = {
                "apps": [
                    {"name": "http", "version": "1.0"},
                    {"name": "slack", "version": "2.0"},
                ],
            }
            return FakeMakeApiResponse(json.dumps(payload).encode("utf-8"))
        if request.full_url.endswith("/imt/apps/http/1.0"):
            return FakeMakeApiResponse(
                json.dumps(
                    make_raw_spec_payload(slug="http", version="1.0")
                ).encode("utf-8")
            )
        if request.full_url.endswith("/imt/apps/slack/2.0"):
            return FakeMakeApiResponse(
                json.dumps(
                    make_raw_spec_payload(slug="slack", version="2.0")
                ).encode("utf-8")
            )
        for platform_slug in MAKE_PLATFORM_RAW_SPEC_SLUGS:
            if platform_slug != "http" and request.full_url.endswith(
                f"/imt/apps/{platform_slug}"
            ):
                return FakeMakeApiResponse(
                    json.dumps(
                        make_raw_spec_payload(
                            slug=platform_slug,
                            version="current",
                            label=platform_slug,
                        )
                    ).encode("utf-8")
                )
        failure_message = f"Unexpected Make API request: {request.full_url}"
        assert_unexpected_success(failure_message)
        return None

    config = MakeScraperConfig.from_env(
        tmp_path,
        {
            "MAKE_LIVE_SCRAPER_ENABLED": "true",
            "MAKE_API_TOKEN": fake_make_api_token(),
            "MAKE_ZONE": "eu1.make.com",
            "MAKE_ORGANIZATION_ID": "123",
        },
    )
    client = MakeApiClient(
        MakeApiClientConfig(
            api_token=fake_make_api_token(), zone="eu1.make.com"
        ),
        opener=fake_open,
    )

    report = refresh_raw_specs_from_live_config(
        config=config,
        client=client,
        generated_at_utc=FIXED_GENERATED_AT,
    )

    assert report.targets_seen == EXPECTED_LIVE_REFRESH_TARGET_COUNT, (
        f"Live refresh did not fetch all targets: {report}"
    )
    assert report.files_written == EXPECTED_LIVE_REFRESH_TARGET_COUNT, (
        f"Live refresh did not fetch all targets: {report}"
    )
    manifest = load_sqlite_manifest(tmp_path)
    expected_manifest_slugs = tuple(
        sorted(("slack", *MAKE_PLATFORM_RAW_SPEC_SLUGS))
    )
    assert (
        tuple(record.app_slug for record in manifest.records)
        == expected_manifest_slugs
    ), f"Unexpected manifest records: {manifest.records}"
    expected_fetch_targets = tuple(
        sorted(
            (
                *(
                    MakeRawSpecTarget(app_slug=slug, app_version="current")
                    for slug in MAKE_PLATFORM_RAW_SPEC_SLUGS
                    if slug != "http"
                ),
                MakeRawSpecTarget(app_slug="http", app_version="1.0"),
                MakeRawSpecTarget(app_slug="slack", app_version="2.0"),
            ),
            key=lambda target: (target.app_slug, target.app_version),
        )
    )
    expected_fetch_urls = [
        "https://eu1.make.com/api/v2/imt/apps?organizationId=123",
        *[
            (
                f"https://eu1.make.com/api/v2/imt/apps/{target.app_slug}"
                if target.app_version == "current"
                else f"https://eu1.make.com/api/v2/imt/apps/{target.app_slug}/{target.app_version}"
            )
            for target in expected_fetch_targets
        ],
    ]
    assert observed_urls == expected_fetch_urls, (
        f"Unexpected live refresh URLs: {observed_urls}"
    )


def test_live_refresh_downloads_raw_spec_and_opens_downstream_review(
    tmp_path: Path,
) -> None:
    """Service-facing live refresh downloads raw specs and queues downstream.

    review.
    """
    observed_urls: list[str] = []

    def fake_open(
        request: Request, timeout_seconds: float
    ) -> FakeMakeApiResponse:
        del timeout_seconds
        observed_urls.append(request.full_url)
        if request.full_url.endswith(
            "/imt/apps?organizationId=123&search=slack"
        ):
            return FakeMakeApiResponse(
                b'{"apps":[{"name":"slack","version":"2.0"}]}'
            )
        if request.full_url.endswith("/imt/apps/slack/2.0"):
            return FakeMakeApiResponse(
                json.dumps(
                    make_raw_spec_payload(
                        slug="slack",
                        version="2.0",
                        label="Slack",
                    )
                ).encode("utf-8")
            )
        failure_message = f"Unexpected Make API request: {request.full_url}"
        assert_unexpected_success(failure_message)
        return None

    config = MakeScraperConfig.from_env(
        tmp_path,
        {
            "MAKE_LIVE_SCRAPER_ENABLED": "true",
            "MAKE_API_TOKEN": fake_make_api_token(),
            "MAKE_ZONE": "eu1.make.com",
            "MAKE_ORGANIZATION_ID": "123",
        },
    )
    client = MakeApiClient(
        MakeApiClientConfig(
            api_token=fake_make_api_token(), zone="eu1.make.com"
        ),
        opener=fake_open,
    )

    report = refresh_raw_specs_from_live_config(
        config=config,
        client=client,
        search="slack",
        limit=1,
        generated_at_utc=FIXED_GENERATED_AT,
    )

    connection = sqlite3.connect(tmp_path / "src/data/pancakes.sqlite")
    try:
        payload_count = cast(
            "tuple[int]",
            connection.execute(
                """
                SELECT COUNT(*)
                FROM make_raw_spec_payloads
                WHERE app_slug = 'slack'
                  AND app_version = '2.0'
                  AND valid_to IS NULL
                """
            ).fetchone(),
        )[0]
        review_row = cast(
            "tuple[str, str, str, str, str | None]",
            connection.execute(
                """
                SELECT
                  update_kind,
                  review_status,
                  review_surfaces_json,
                  source_ref,
                  valid_to
                FROM make_raw_spec_update_reviews
                WHERE app_slug = 'slack'
                  AND app_version = '2.0'
                ORDER BY valid_from DESC
                LIMIT 1
                """
            ).fetchone(),
        )
    finally:
        connection.close()

    assert observed_urls == [
        "https://eu1.make.com/api/v2/imt/apps?organizationId=123&search=slack ",
        "https://eu1.make.com/api/v2/imt/apps/slack/2.0",
    ], f"Live refresh did not download Slack raw specs: {observed_urls}"
    assert report.files_written == 1, (
        f"Live refresh did not persist Slack: {report}"
    )
    assert payload_count == 1, (
        "Live refresh did not write the current Slack payload."
    )
    assert review_row[0] == "new_raw_spec", (
        f"New live raw specs must open downstream review: {review_row}"
    )
    assert review_row[1] == RAW_SPEC_UPDATE_REVIEW_PENDING_STATUS
    assert (
        review_surfaces_from_json(review_row[2])
        == RAW_SPEC_UPDATE_REVIEW_SURFACES
    )
    assert review_row[3] == f"{RAW_SPEC_SQLITE_DIR}/slack__2.0"
    assert review_row[4] is None, (
        f"New review must remain pending: {review_row}"
    )


def test_raw_spec_cli_reports_status_from_repo_env(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    """The service-facing raw-spec CLI reports manifest status without live.

    calls.
    """
    exit_code = raw_specs_cli_main(["--repo-root", str(tmp_path), "status"])

    output = capsys.readouterr().out
    payload = json_object_from_text(output, "raw-spec status output")
    assert exit_code == 0, (
        f"Unexpected raw-spec CLI status: {exit_code}, {payload}"
    )
    assert payload["status"] == "missing_manifest", (
        f"Unexpected raw-spec CLI status: {exit_code}, {payload}"
    )
    assert payload["freshness_status"] == "missing_manifest", (
        f"Missing manifest status must expose freshness explicitly: {payload}"
    )
    assert payload["complete_refresh_available"] is False, (
        f"Status must not imply live refresh is configured: {payload}"
    )
    blockers = cast("list[str]", payload["complete_refresh_blockers"])
    assert any("operator-gated" in blocker for blocker in blockers), (
        f"Status must explain the operator-gated live refresh blocker: "
        f"{payload}"
    )


def test_raw_spec_cli_redacts_invalid_limit_arguments(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    """CLI argument errors must not echo secret-looking limit values."""
    unsafe_value = "sk-" + ("L" * 24)

    with pytest.raises(SystemExit):
        _ = raw_specs_cli_main(
            ["--repo-root", str(tmp_path), "refresh", "--limit", unsafe_value]
        )

    captured = capsys.readouterr()
    assert unsafe_value not in captured.err, (
        f"Invalid raw-spec CLI limit leaked into stderr: {captured.err}"
    )
    assert "raw argument value is redacted" in captured.err, (
        f"Invalid raw-spec CLI limit should explain redaction: {captured.err}"
    )


def test_raw_spec_cli_reports_invalid_manifest_status(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    """The service-facing status command reports local manifest corruption."""
    target = MakeRawSpecTarget(app_slug="http", app_version="1.0")
    report = sync_raw_specs(
        config=MakeScraperConfig(repo_root=tmp_path),
        source=InMemoryRawSpecSource({target: make_raw_spec_payload()}),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )
    del report
    corrupt_sqlite_raw_spec_payload(tmp_path)

    exit_code = raw_specs_cli_main(["--repo-root", str(tmp_path), "status"])

    output = capsys.readouterr().out
    status = json_object_from_text(
        output, "raw-spec invalid-manifest status output"
    )
    assert exit_code == 0, (
        f"Unexpected invalid-manifest status: {exit_code}, {status}"
    )
    assert status["status"] == "invalid_manifest", (
        f"Unexpected invalid-manifest status: {exit_code}, {status}"
    )
    assert not (status["manifest_available"] is not True), (
        f"Invalid manifests must still be reported available: {status}"
    )
    assert status["record_count"] == 0, (
        f"Invalid manifests must not report loaded records: {status}"
    )


def test_raw_spec_status_degrades_for_tampered_raw_spec_file(
    tmp_path: Path,
) -> None:
    """Raw-spec status verifies SQLite payload integrity, not cache projection.

    state.
    """
    target = MakeRawSpecTarget(app_slug="http", app_version="1.0")
    report = sync_raw_specs(
        config=MakeScraperConfig(repo_root=tmp_path),
        source=InMemoryRawSpecSource({target: make_raw_spec_payload()}),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )
    del report
    corrupt_sqlite_raw_spec_payload(tmp_path)

    status = raw_spec_refresh_status(MakeScraperConfig(repo_root=tmp_path))

    assert status.status == "invalid_manifest", (
        f"Tampered SQLite raw-spec payload should fail closed: {status}"
    )
    assert not (status.missing_records), (
        f"Tampered SQLite payload should not be reported as a missing cache "
        f"file: {status}"
    )
    assert status.invalid_records == ("make_raw_spec_manifest_records",), (
        f"Tampered SQLite payload should be reported invalid: {status}"
    )
    assert status.freshness_status == "invalid_manifest", (
        f"Tampered raw specs must expose invalid freshness: {status}"
    )
    assert status.complete_refresh_blockers, (
        f"Degraded status must explain remaining refresh blockers: {status}"
    )


def test_raw_spec_status_reports_refresh_policy_and_source_summary(
    tmp_path: Path,
) -> None:
    """Status reports source freshness and refresh safety without live calls."""
    targets = {
        MakeRawSpecTarget(
            app_slug="http", app_version="1.0"
        ): make_raw_spec_payload(),
        MakeRawSpecTarget(
            app_slug="slack", app_version="2.0"
        ): make_raw_spec_payload(
            slug="slack",
            version="2.0",
            label="Slack",
        ),
    }
    _ = sync_raw_specs(
        config=MakeScraperConfig(repo_root=tmp_path),
        source=InMemoryRawSpecSource(targets),
        source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        generated_at_utc=FIXED_GENERATED_AT,
    )

    status = raw_spec_refresh_status(MakeScraperConfig(repo_root=tmp_path))

    assert status.status == "ready", (
        f"Synced raw specs should be ready: {status}"
    )
    assert status.generated_at_utc == FIXED_GENERATED_AT, (
        f"Status must expose manifest generation time: {status}"
    )
    assert status.freshness_status == "manifest_verified", (
        f"Ready status must expose verified freshness: {status}"
    )
    assert status.latest_record_count == len(targets), (
        f"Status must count latest retained records: {status}"
    )
    assert status.total_module_count == EXPECTED_MODULE_COUNT * len(targets), (
        f"Status must summarize module coverage: {status}"
    )
    assert status.source_type_counts == (("derived_fixture", len(targets)),), (
        f"Status must summarize source metadata: {status}"
    )
    assert status.sanitization_status_counts == (
        ("synthetic_fixture", len(targets)),
    ), f"Status must summarize sanitization posture: {status}"
    assert "pancakes_sqlite_raw_specs" in status.evidence_generalization_path, (
        f"Status must describe generalized evidence flow: {status}"
    )
    assert (
        "provider credential values in source control"
        in status.forbidden_refresh_inputs
    ), f"Status must document forbidden refresh inputs: {status}"


def test_make_api_client_retries_rate_limits_without_live_network() -> None:
    """The Make API client retries HTTP 429 through an injected transport."""
    attempt_urls: list[str] = []
    sleeps: list[float] = []

    def fake_open(
        request: Request, timeout_seconds: float
    ) -> FakeMakeApiResponse:
        del timeout_seconds
        attempt_urls.append(request.full_url)
        if len(attempt_urls) == 1:
            headers = Message()
            headers["Retry-After"] = "2"
            raise HTTPError(
                request.full_url,
                429,
                "Too Many Requests",
                hdrs=headers,
                fp=BytesIO(b'{"error":"rate_limited"}'),
            )
        return FakeMakeApiResponse(b'{"ok":true}')

    client = MakeApiClient(
        MakeApiClientConfig(api_token=fake_make_api_token(), zone="eu1"),
        opener=fake_open,
        sleeper=sleeps.append,
    )

    payload = client.get_json("/users/me")
    assert payload == {"ok": True}, (
        f"Unexpected retry behavior: {payload}, {attempt_urls}, {sleeps}"
    )
    assert len(attempt_urls) == EXPECTED_RETRY_ATTEMPTS, (
        f"Unexpected retry behavior: {payload}, {attempt_urls}, {sleeps}"
    )
    assert sleeps == [2.0], (
        f"Unexpected retry behavior: {payload}, {attempt_urls}, {sleeps}"
    )


def test_make_api_client_uses_explicit_3dfd9969() -> None:
    """HTTP 429 fallback retries use the configured exponential backoff.

    sequence.
    """
    attempts = 0
    sleeps: list[float] = []

    def fake_open(
        request: Request, timeout_seconds: float
    ) -> FakeMakeApiResponse:
        nonlocal attempts
        del timeout_seconds
        attempts += 1
        if attempts < EXPECTED_HTTP_429_BACKOFF_ATTEMPTS:
            raise HTTPError(
                request.full_url,
                429,
                "Too Many Requests",
                hdrs=Message(),
                fp=BytesIO(b'{"error":"rate_limited"}'),
            )
        return FakeMakeApiResponse(b'{"ok":true}')

    client = MakeApiClient(
        MakeApiClientConfig(api_token=fake_make_api_token(), zone="eu1"),
        opener=fake_open,
        sleeper=sleeps.append,
    )

    payload = client.get_json("/users/me")

    assert payload == {"ok": True}, (
        f"Unexpected fallback retry sequence: {payload}, {sleeps}"
    )
    assert sleeps == [30.0, 60.0, 150.0], (
        f"Unexpected fallback retry sequence: {payload}, {sleeps}"
    )


def test_make_api_client_closes_retry_response_before_sleep_failure() -> None:
    """Retryable HTTP error bodies are closed even when backoff sleeping.

    fails.
    """
    error_body = BytesIO(b'{"error":"rate_limited"}')

    def fake_open(
        request: Request, timeout_seconds: float
    ) -> FakeMakeApiResponse:
        del timeout_seconds
        headers = Message()
        headers["Retry-After"] = "2"
        raise HTTPError(
            request.full_url,
            429,
            "Too Many Requests",
            hdrs=headers,
            fp=error_body,
        )

    def failing_sleep(seconds: float) -> None:
        del seconds
        message = "sleep failed"
        raise RuntimeError(message)

    client = MakeApiClient(
        MakeApiClientConfig(api_token=fake_make_api_token(), zone="eu1"),
        opener=fake_open,
        sleeper=failing_sleep,
    )

    with pytest.raises(RuntimeError, match="sleep failed"):
        _ = client.get_json("/users/me")
    assert error_body.closed, (
        "Retryable HTTPError body was not closed before sleeper failure."
    )


def test_make_api_client_closes_non_retryable_error_response() -> None:
    """Non-retryable HTTP error bodies are closed after local error mapping."""
    error_body = BytesIO(b'{"error":"unavailable"}')

    def fake_open(
        request: Request, timeout_seconds: float
    ) -> FakeMakeApiResponse:
        del timeout_seconds
        raise HTTPError(
            request.full_url,
            500,
            "Server Error",
            hdrs=Message(),
            fp=error_body,
        )

    client = MakeApiClient(
        MakeApiClientConfig(api_token=fake_make_api_token(), zone="eu1"),
        opener=fake_open,
    )

    with pytest.raises(MakeApiRemoteError, match="status 500"):
        _ = client.get_json("/users/me")
    assert error_body.closed, (
        "Non-retryable HTTPError body was not closed after error mapping."
    )


def test_make_api_client_requires_token_before_live_transport() -> None:
    """Live client calls fail before transport when token configuration is.

    absent.
    """
    client = MakeApiClient(MakeApiClientConfig(api_token=None, zone="eu1"))

    with pytest.raises(MakeApiConfigurationError, match="token"):
        _ = client.get_json("/users/me")


def test_parser_rejects_payloads_without_app_object() -> None:
    """Parser fails closed when the raw spec has no app object."""
    with pytest.raises(TypeError, match="app"):
        require_missing_app_object_failure()


def test_parser_rejects_non_list_module_collections() -> None:
    """Parser fails closed when a Make module collection is malformed."""
    payload = make_raw_spec_payload()
    app = cast("JsonObject", payload["app"])
    app["actions"] = {"name": "makeRequest"}

    with pytest.raises(TypeError, match="actions"):
        _ = parse_make_raw_spec(payload)


def test_parser_rejects_non_object_module_collection_items() -> None:
    """Parser fails closed when a Make module collection item is malformed."""
    payload = make_raw_spec_payload()
    app = cast("JsonObject", payload["app"])
    app["actions"] = ["makeRequest"]

    with pytest.raises(TypeError, match=r"actions\[0\]"):
        _ = parse_make_raw_spec(payload)


def require_missing_app_object_failure() -> None:
    """Fail unless a payload without an app object is rejected."""
    unexpected_spec = parse_make_raw_spec({})
    failure_message = f"Invalid payload should have failed: {unexpected_spec}"
    assert_unexpected_success(failure_message)
