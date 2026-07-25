# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Behavior tests for pure Make knowledge catalog projections.

Boundary contract:
- Owns: tests for converting loaded knowledge facts into catalog read models.
- Must not: open SQLite databases, read raw specs, call MCP handlers,
  or contact Make.
- Allows: synthetic knowledge facts and deterministic catalog projection
  assertions.
- Split when: projection behavior needs IO-backed integration coverage.
- Merge when: another catalog test duplicates these pure projection contracts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from catalog.knowledge.models import (
    KnowledgeConstraintFact,
    KnowledgeFieldFact,
    KnowledgeModuleFact,
    KnowledgeStoreQuery,
)
from catalog.knowledge.projection import (
    knowledge_module_ids_for_token,
    knowledge_query_to_catalog_snapshot,
)

if TYPE_CHECKING:
    from catalog.models import (
        CatalogAppVersion,
        CatalogField,
        CatalogModule,
        CatalogSnapshot,
    )

HTTP_MODULE_ID = "module:http:1.0:action:makeRequest"
HTTP_SEARCH_MODULE_ID = "module:http:1.0:search:listRequests"
SLACK_LEGACY_MESSAGE_MODULE_ID = (
    "module:slack:2.14.3:action:ActionCreateMessage"
)
SLACK_CURRENT_MESSAGE_MODULE_ID = "module:slack:4.12.22:action:CreateMessage"
SLACK_LEGACY_MESSAGE_REFERENCE = "slack:ActionCreateMessage"
HTTP_URL_FIELD_ID = "field:module:http:1.0:action:makeRequest:parameter:url"
HTTP_HEADERS_FIELD_ID = (
    "field:module:http:1.0:action:makeRequest:expect:headers"
)
HTTP_URL_CONSTRAINT_ID = f"constraint:{HTTP_URL_FIELD_ID}:required"
HTTP_RPC_CONSTRAINT_ID = f"constraint:{HTTP_HEADERS_FIELD_ID}:validate_rpc"
QUERY_FINGERPRINT = "f" * 64
DISPLAY_NAME_REFERENCE = "http:Make Request"
INTERNAL_NAME_REFERENCE = "http:make-request"
UNKNOWN_REFERENCE = "unknown"


def test_knowledge_query_projects_snapshot_fields_and_constraints() -> None:
    """Knowledge facts become deterministic catalog snapshots."""
    snapshot = knowledge_query_to_catalog_snapshot(query=_synthetic_query())

    _assert_snapshot_identity(snapshot)
    version = _assert_single_http_version(snapshot)
    module = version.modules[0]
    _assert_projected_module(module)
    _assert_projected_url_field(module.parameters[0])


def _assert_snapshot_identity(snapshot: CatalogSnapshot) -> None:
    assert snapshot.catalog_schema_version == 1, (
        f"Unexpected catalog schema version: {snapshot.catalog_schema_version}"
    )
    assert snapshot.generated_at_utc == "knowledge-store", (
        f"Unexpected projection timestamp label: {snapshot.generated_at_utc}"
    )
    assert snapshot.raw_spec_manifest_sha256 == QUERY_FINGERPRINT, (
        f"Unexpected raw-spec projection fingerprint: {snapshot}"
    )
    assert len(snapshot.apps) == 1, (
        f"Projected apps were not grouped by slug: {snapshot.apps}"
    )
    assert snapshot.apps[0].app_slug == "http", (
        f"Projected apps were not grouped by slug: {snapshot.apps}"
    )


def _assert_single_http_version(snapshot: CatalogSnapshot) -> CatalogAppVersion:
    app = snapshot.apps[0]
    assert app.label == "Http", f"Projected app identity drifted: {app}"
    assert app.external_id == "http", f"Projected app identity drifted: {app}"
    assert not (app.deprecated), f"Projected app identity drifted: {app}"
    assert tuple(version.version for version in app.versions) == ("1.0",), (
        f"Projected versions were not grouped deterministically: {app.versions}"
    )
    version = app.versions[0]
    assert tuple(module.module_id for module in version.modules) == (
        HTTP_MODULE_ID,
        HTTP_SEARCH_MODULE_ID,
    ), f"Projected modules were not sorted by module id: {version.modules}"
    return version


def _assert_projected_module(module: CatalogModule) -> None:
    assert module.app_version_id == "app-version:http:1.0", (
        f"Projected module app-version id drifted: {module}"
    )
    assert module.module_kind == "action", (
        f"Projected module identity drifted: {module}"
    )
    assert module.display_name == "Make request", (
        f"Projected module identity drifted: {module}"
    )
    assert module.rpc_dependencies == ("rpc://http/headers",), (
        f"Projected RPC dependencies drifted: {module.rpc_dependencies}"
    )
    assert tuple(field.field_id for field in module.parameters) == (
        HTTP_URL_FIELD_ID,
    ), f"Projected parameter fields drifted: {module.parameters}"
    assert tuple(field.field_id for field in module.expect_schema) == (
        HTTP_HEADERS_FIELD_ID,
    ), f"Projected expect fields drifted: {module.expect_schema}"
    assert not (module.interface_schema), (
        f"Unexpected interface fields were projected: {module.interface_schema}"
    )


def _assert_projected_url_field(url_field: CatalogField) -> None:
    assert url_field.raw_schema == {
        "path": ["url"],
        "label": "URL",
        "required": True,
        "type": "url",
    }, f"Projected field raw schema drifted: {url_field.raw_schema}"
    assert url_field.constraints[0].value == {"required": True}, (
        f"Projected constraint JSON object drifted: {url_field.constraints}"
    )


def test_knowledge_query_projection_can_select_requested_modules() -> None:
    """Pure projection can narrow queries without changing owners."""
    snapshot = knowledge_query_to_catalog_snapshot(
        query=_synthetic_query(),
        module_ids=(HTTP_SEARCH_MODULE_ID,),
    )

    projected_module_ids = tuple(
        module.module_id
        for app in snapshot.apps
        for version in app.versions
        for module in version.modules
    )
    assert projected_module_ids == (HTTP_SEARCH_MODULE_ID,), (
        f"Projected module filter drifted: {projected_module_ids}"
    )


def test_knowledge_query_projection_marks_only_newest_version_latest() -> None:
    """Projected versions should be newest-first with one latest."""
    snapshot = knowledge_query_to_catalog_snapshot(
        query=_multi_version_http_query()
    )
    app = snapshot.apps[0]

    assert tuple(version.version for version in app.versions) == (
        "2.0",
        "1.10",
        "1.9",
    ), f"Projected app versions should be semantic newest-first: {app.versions}"
    assert tuple(version.latest for version in app.versions) == (
        True,
        False,
        False,
    ), f"Only the newest projected version should be latest: {app.versions}"


def test_knowledge_module_ids_for_token_uses_separator_names() -> None:
    """AST-style module tokens map without MCP-specific logic."""
    query = _synthetic_query()

    assert knowledge_module_ids_for_token(
        query=query, module_token=HTTP_MODULE_ID
    ) == (HTTP_MODULE_ID,), "Exact module ids must pass through unchanged."
    assert knowledge_module_ids_for_token(
        query=query, module_token=DISPLAY_NAME_REFERENCE
    ) == (HTTP_MODULE_ID,), (
        "Display-name module tokens must resolve separator-insensitively."
    )
    assert knowledge_module_ids_for_token(
        query=query, module_token=INTERNAL_NAME_REFERENCE
    ) == (HTTP_MODULE_ID,), (
        "Internal-name module tokens must resolve separator-insensitively."
    )
    assert (
        knowledge_module_ids_for_token(
            query=query, module_token=UNKNOWN_REFERENCE
        )
        == ()
    ), "Non Make-style module tokens must not fabricate catalog matches."


def test_knowledge_module_ids_include_legacy_successors() -> None:
    """Project snapshots include successors for legacy module tokens."""
    query = _legacy_slack_query()

    assert knowledge_module_ids_for_token(
        query=query,
        module_token=SLACK_LEGACY_MESSAGE_REFERENCE,
    ) == (
        SLACK_LEGACY_MESSAGE_MODULE_ID,
        SLACK_CURRENT_MESSAGE_MODULE_ID,
    ), "Legacy Make action prefixes must not pin snapshots to stale IDs."


def _synthetic_query() -> KnowledgeStoreQuery:
    return KnowledgeStoreQuery(
        aliases=(),
        rule_facts=(),
        optimizer_hints=(),
        transaction_profiles=(),
        claim_conflicts=(),
        designer_messages=(),
        modules=(
            KnowledgeModuleFact(
                module_id=HTTP_SEARCH_MODULE_ID,
                app_slug="http",
                app_version="1.0",
                module_kind="search",
                internal_name="listRequests",
                display_name="List requests",
                deprecated=False,
                fingerprint="2" * 64,
                adr_anchor="001064#repo.make-knowledge.runtime-source-label",
            ),
            KnowledgeModuleFact(
                module_id=HTTP_MODULE_ID,
                app_slug="http",
                app_version="1.0",
                module_kind="action",
                internal_name="make-request",
                display_name="Make request",
                deprecated=False,
                fingerprint="1" * 64,
                adr_anchor="001064#repo.make-knowledge.runtime-source-label",
            ),
        ),
        fields=(
            KnowledgeFieldFact(
                field_id=HTTP_HEADERS_FIELD_ID,
                module_id=HTTP_MODULE_ID,
                direction="expect",
                path=("headers",),
                label="Headers",
                required=False,
                field_type="collection",
                fingerprint="4" * 64,
                adr_anchor="001064#repo.make-knowledge.runtime-source-label",
            ),
            KnowledgeFieldFact(
                field_id=HTTP_URL_FIELD_ID,
                module_id=HTTP_MODULE_ID,
                direction="parameter",
                path=("url",),
                label="URL",
                required=True,
                field_type="url",
                fingerprint="3" * 64,
                adr_anchor="001064#repo.make-knowledge.runtime-source-label",
            ),
        ),
        constraints=(
            KnowledgeConstraintFact(
                constraint_id=HTTP_RPC_CONSTRAINT_ID,
                field_id=HTTP_HEADERS_FIELD_ID,
                constraint_key="validate_rpc",
                value_json='{"rpc":"rpc://http/headers"}',
                fingerprint="6" * 64,
                adr_anchor="001064#repo.make-knowledge.runtime-source-label",
            ),
            KnowledgeConstraintFact(
                constraint_id=HTTP_URL_CONSTRAINT_ID,
                field_id=HTTP_URL_FIELD_ID,
                constraint_key="required",
                value_json='{"required":true}',
                fingerprint="5" * 64,
                adr_anchor="001064#repo.make-knowledge.runtime-source-label",
            ),
        ),
        native_expectations=(),
        fingerprint=QUERY_FINGERPRINT,
    )


def _legacy_slack_query() -> KnowledgeStoreQuery:
    return KnowledgeStoreQuery(
        aliases=(),
        rule_facts=(),
        optimizer_hints=(),
        transaction_profiles=(),
        claim_conflicts=(),
        designer_messages=(),
        modules=(
            KnowledgeModuleFact(
                module_id=SLACK_LEGACY_MESSAGE_MODULE_ID,
                app_slug="slack",
                app_version="2.14.3",
                module_kind="action",
                internal_name="ActionCreateMessage",
                display_name="Create a message",
                deprecated=False,
                fingerprint="a" * 64,
                adr_anchor="001064#repo.make-knowledge.runtime-source-label",
            ),
            KnowledgeModuleFact(
                module_id=SLACK_CURRENT_MESSAGE_MODULE_ID,
                app_slug="slack",
                app_version="4.12.22",
                module_kind="action",
                internal_name="CreateMessage",
                display_name="Send a Message",
                deprecated=False,
                fingerprint="b" * 64,
                adr_anchor="001064#repo.make-knowledge.runtime-source-label",
            ),
        ),
        fields=(),
        constraints=(),
        fingerprint=QUERY_FINGERPRINT,
    )


def _multi_version_http_query() -> KnowledgeStoreQuery:
    return KnowledgeStoreQuery(
        aliases=(),
        rule_facts=(),
        optimizer_hints=(),
        transaction_profiles=(),
        claim_conflicts=(),
        designer_messages=(),
        modules=(
            _http_module_fact(app_version="1.9", fingerprint="9" * 64),
            _http_module_fact(app_version="1.10", fingerprint="a" * 64),
            _http_module_fact(app_version="2.0", fingerprint="b" * 64),
        ),
        fields=(),
        constraints=(),
        native_expectations=(),
        fingerprint=QUERY_FINGERPRINT,
    )


def _http_module_fact(
    *, app_version: str, fingerprint: str
) -> KnowledgeModuleFact:
    return KnowledgeModuleFact(
        module_id=f"module:http:{app_version}:action:makeRequest",
        app_slug="http",
        app_version=app_version,
        module_kind="action",
        internal_name="make-request",
        display_name="Make request",
        deprecated=False,
        fingerprint=fingerprint,
        adr_anchor="001064#repo.make-knowledge.runtime-source-label",
    )
