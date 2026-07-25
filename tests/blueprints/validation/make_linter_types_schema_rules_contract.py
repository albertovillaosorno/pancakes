# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contract tests for promoted Make linter type and schema rules.

Boundary contract:
- Owns: focused type/schema-rule fixtures promoted from the Make linter intake
  queue.
- Must not: import provider catalogs, leak raw specs, or infer business
semantics
  from public templates.
- Allows: synthetic AST fixtures, promoted knowledge facts, and exact finding
  assertions for local schema evidence.
- Split when: type coercion, Parse JSON, app catalog, or raw-spec provenance
rules
  need independent fixture families.
- Merge when: the main blueprint validation contract owns these exact fixtures.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from blueprints.ast import parse_make_ast_json_text
from blueprints.validation import validate_blueprint
from catalog import catalog_snapshot_from_json
from catalog.json_payloads import normalize_json_object
from catalog.knowledge import KnowledgeRuleFact, KnowledgeStoreQuery

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping

    from blueprints.validation import BlueprintValidationReport
    from catalog import CatalogSnapshot

REPO_ROOT = repo_root()
CATALOG_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "catalog"
    / "fixtures"
    / "make_catalog"
    / "sample_catalog.json"
)
CLIENT_PATH_TOKENS = ("\\", "/", "src/", "tests/", "Refactor", "C:")


def test_parse_json_requires_schema_evidence() -> None:
    """Parse JSON warns when no local schema or data-structure evidence is.

    visible.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "parse-json-missing-schema",
                    "flow": [
                        {
                            "id": 1,
                            "module": "json:ParseJSON",
                            "parameters": {"json": "{{1.body}}"},
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=types_schema_knowledge_query(),
    )

    findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "parse_json.schema_missing"
    )

    assert findings, f"Parse JSON schema warning did not run: {report.codes()}"
    assert not (any(finding.severity != "warning" for finding in findings)), (
        f"Parse JSON schema findings should warn: {findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_parse_json_accepts_schema_evidence() -> None:
    """Parse JSON stays quiet when local schema evidence exists."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "parse-json-with-schema",
                    "flow": [
                        {
                            "id": 1,
                            "module": "json:ParseJSON",
                            "parameters": {
                                "json": "{{1.body}}",
                                "schema": {
                                    "type": "object",
                                    "required": ["id"],
                                },
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=types_schema_knowledge_query(),
    )

    assert "parse_json.schema_missing" not in report.codes(), (
        f"Parse JSON schema evidence still produced warnings: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_parse_json_required_mapper_field_matches_live_module_validation() -> (
    None
):
    """Live module validation for missing mapper.json is mirrored by local.

    required fields.
    """
    missing = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "parse-json-missing-required-json",
                    "flow": [
                        {
                            "id": 1,
                            "module": "json:ParseJSON",
                            "parameters": {},
                            "mapper": {},
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=live_parse_json_catalog_fixture(),
    )
    valid = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "parse-json-with-required-json",
                    "flow": [
                        {
                            "id": 1,
                            "module": "json:ParseJSON",
                            "parameters": {},
                            "mapper": {"json": '{"status":"ok"}'},
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=live_parse_json_catalog_fixture(),
    )

    missing_required = tuple(
        finding
        for finding in missing.findings
        if finding.code == "mapping.required_parameter_missing"
    )

    assert missing_required, (
        f"Missing mapper.json should fail locally: {missing.codes()}"
    )
    assert "mapping.required_parameter_missing" not in valid.codes(), (
        f"Mapped mapper.json should satisfy the required field: "
        f"{valid.findings}"
    )
    assert_client_messages_are_path_safe(missing)
    assert_client_messages_are_path_safe(valid)


def types_schema_knowledge_query() -> KnowledgeStoreQuery:
    """Return promoted type/schema facts for focused linter fixtures."""
    return KnowledgeStoreQuery(
        fingerprint="knowledge:types-schema-data-apps",
        aliases=(),
        rule_facts=(
            KnowledgeRuleFact(
                rule_id="linter-0019-parse-json-schema-missing",
                domain="types_schema",
                rule_code="parse_json.schema_missing",
                severity="warning",
                description=(
                    "Parse JSON modules should declare schema or data-structure"
                    "evidence."
                ),
                adr_anchor="001079#repo.make-linter.rule-intake-manual-gate",
            ),
        ),
        optimizer_hints=(),
    )


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


def live_parse_json_catalog_fixture() -> CatalogSnapshot:
    """Return a minimal catalog with Make-observed Parse JSON required-field.

    evidence.
    """
    field_id = "field:module:json:1.0:transformer:ParseJSON:parameter:json"
    module_id = "module:json:1.0:transformer:ParseJSON"
    app_sha = "1" * 64
    version_sha = "2" * 64
    module_sha = "3" * 64
    field_sha = "4" * 64
    constraint_sha = "5" * 64
    raw_spec_sha = "6" * 64
    catalog_sha = "7" * 64
    manifest_sha = "8" * 64
    payload: Mapping[str, object] = {
        "apps": [
            {
                "app_id": "app:json",
                "app_slug": "json",
                "deprecated": False,
                "external_id": "json",
                "fingerprint": app_sha,
                "label": "JSON",
                "versions": [
                    {
                        "app_id": "app:json",
                        "app_slug": "json",
                        "app_version_id": "app-version:json:1.0",
                        "fingerprint": version_sha,
                        "latest": True,
                        "manifest_version": 1,
                        "modules": [
                            {
                                "app_slug": "json",
                                "app_version": "1.0",
                                "app_version_id": "app-version:json:1.0",
                                "deprecated": False,
                                "display_name": "Parse JSON",
                                "expect_schema": [],
                                "external_id": "json:1.0:transformer:ParseJSON",
                                "fingerprint": module_sha,
                                "interface_schema": [],
                                "internal_name": "ParseJSON",
                                "module_id": module_id,
                                "module_kind": "transformer",
                                "parameters": [
                                    {
                                        "advanced": None,
                                        "constraints": [
                                            {
                                                "constraint_id": (
                                                    f"{field_id}:required_000"
                                                ),
                                                "field_id": field_id,
                                                "fingerprint": constraint_sha,
                                                "key": "required_000",
                                                "value": {"required": True},
                                            }
                                        ],
                                        "direction": "parameter",
                                        "external_id": (
                                            f"{module_id}:parameter:json"
                                        ),
                                        "field_id": field_id,
                                        "field_type": "text",
                                        "fingerprint": field_sha,
                                        "label": "JSON string",
                                        "module_id": module_id,
                                        "path": ["json"],
                                        "raw_schema": {
                                            "label": "JSON string",
                                            "name": "json",
                                            "required": True,
                                            "type": "text",
                                        },
                                        "required": True,
                                        "rpc_dependencies": [],
                                    }
                                ],
                                "raw_spec_sha256": raw_spec_sha,
                                "rpc_dependencies": [],
                            }
                        ],
                        "raw_spec_sha256": raw_spec_sha,
                        "version": "1.0",
                    }
                ],
            }
        ],
        "catalog_schema_version": 1,
        "fingerprint": catalog_sha,
        "generated_at_utc": "2026-05-28T00:00:00+00:00",
        "raw_spec_manifest_sha256": manifest_sha,
    }
    return catalog_snapshot_from_json(normalize_json_object(payload))


def assert_client_messages_are_path_safe(
    report: BlueprintValidationReport,
) -> None:
    """Fail if any public validation message leaks repository path details."""
    for finding in report.findings:
        leaked_tokens = [
            token
            for token in CLIENT_PATH_TOKENS
            if token in finding.client_message
        ]
        assert not (leaked_tokens), (
            f"Client message leaked path tokens {leaked_tokens}: {finding}"
        )
