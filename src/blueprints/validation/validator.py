# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001042#repo.make-catalog.schema-policy
# - 001044#repo.make-ast.contract-policy
# - 001045#repo.make-ast.module-resolution-policy
# - 001046#repo.blueprint-validation.validator-policy
# - 001048#repo.blueprint-validation.expression-intelligence-policy
# - 001049#repo.blueprint-repair.diagnostics-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Validate Make AST blueprints against the canonical catalog.

Boundary contract:
- Owns: top-level blueprint validation orchestration across validation slices.
- Must not: own route wrapper rules, finding construction, or output contracts.
- Allows: coordinates parsed AST, catalog evidence, and validation findings.
- Split when: one validation concern can run as an independent deterministic
slice.
- Merge when: a helper only restates orchestration without owning a rule
boundary.
"""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING, Final, TypeGuard, cast
from urllib.parse import urlsplit

from languages.make.parameter_aliases import (
    make_connection_parameter_aliases_for_field,
)

from blueprints.ast.module_roles import (
    module_looks_like_trigger,
    module_looks_like_webhook_response,
    module_token_semantic_key,
)
from blueprints.ast.resolution import (
    DEPRECATED_MODULE,
    RAW_SPEC_BINDING_VERSION_DRIFT,
    RESOLVED_STATUS,
    MakeAstModuleResolution,
    resolve_ast_modules,
)
from blueprints.ast.traversal import iter_ast_nodes
from blueprints.validation.ai_agent_contracts import validate_ai_agent_contracts
from blueprints.validation.content_injection import (
    validate_content_injection_security,
)
from blueprints.validation.crypto_security import validate_crypto_security
from blueprints.validation.cycle_validation import validate_scenario_cycles
from blueprints.validation.data_exposure import validate_data_exposure_security
from blueprints.validation.expression_intelligence import (
    MappingRisk,
    analyze_mapping_risks,
)
from blueprints.validation.findings import build_validation_finding
from blueprints.validation.graphql_security import validate_graphql_security
from blueprints.validation.http_security import validate_http_url_security
from blueprints.validation.importability import validate_importability
from blueprints.validation.models import (
    BlueprintFindingSeverity,
    BlueprintValidationFinding,
    BlueprintValidationReport,
)
from blueprints.validation.network_hosts import host_ip_candidates
from blueprints.validation.note_security import validate_note_content_security
from blueprints.validation.notes import validate_root_notes
from blueprints.validation.output_contracts import validate_output_references
from blueprints.validation.redirect_security import validate_redirect_security
from blueprints.validation.route_validation import validate_routes
from blueprints.validation.sql_security import validate_sql_security
from blueprints.validation.webhook_response_paths import (
    webhook_has_response_on_all_paths,
    webhook_has_response_on_any_path,
)

if TYPE_CHECKING:
    from catalog.knowledge import (
        KnowledgeDesignerMessageEvidence,
        KnowledgeRuleFact,
        KnowledgeStoreQuery,
        KnowledgeTransactionProfile,
    )
    from catalog.models import CatalogField, CatalogModule, CatalogSnapshot

    from blueprints.ast.models import (
        AstPathPart,
        JsonObject,
        MakeAstNode,
        MakeAstRoot,
        MakeAstScheduleConfig,
    )

MUTATING_MODULE_KINDS: Final[frozenset[str]] = frozenset(
    ("action", "search", "trigger")
)
RAW_SPEC_BINDING_HASH_MISSING_CODE: Final = "raw_spec.binding_hash_missing"
RAW_SPEC_BINDING_VERSION_DRIFT_CODE: Final = "raw_spec.binding_version_drift"
RAW_SPEC_HASH_CLAIM_LEVELS: Final[frozenset[str]] = frozenset(
    (
        "catalog_backed_import_ready ",
        "strict_client_handoff",
    )
)
RAW_SPEC_HASH_ARTIFACT_PHASES: Final[frozenset[str]] = frozenset(
    (
        "importable_candidate ",
        "live_make_scenario",
    )
)
AUTH_ERROR_KEYWORDS: Final[tuple[str, ...]] = (
    "reauth ",
    "re-auth ",
    "authenticate ",
    "authentication",
)
SCHEDULE_SUB_MINUTE_INTERVAL_CODE: Final = "schedule.sub_minute_interval"
DIRECT_ERROR_KEYS: Final[tuple[str, ...]] = ("onerror", "on_error")
CHILD_FLOW_CONTAINER_KEYS: Final[frozenset[str]] = frozenset(
    ("routes", "branches", "tools")
)
OPERATION_VOLUME_KINDS: Final[frozenset[str]] = frozenset(
    ("iterator", "aggregator")
)
OPERATION_VOLUME_TOKEN_FRAGMENTS: Final[tuple[str, ...]] = (
    "search ",
    "list ",
    "watch",
)
DATA_STORE_RECOVERY_TOKENS: Final[tuple[str, ...]] = (
    "archive ",
    "audit ",
    "backup ",
    "recover ",
    "recovery ",
    "restore ",
    "rollback ",
    "snapshot ",
    "undo",
)
DATA_STORE_KEY_TOKENS: Final[tuple[str, ...]] = (
    "id ",
    "key ",
    "primary key ",
    "record id",
)
DATA_STORE_EPHEMERAL_STATE_TOKENS: Final[tuple[str, ...]] = (
    "cache ",
    "dedupe ",
    "dedupe key ",
    "idempotency ",
    "lease ",
    "lock ",
    "nonce ",
    "semaphore ",
    "session ",
    "temporary",
)
DATA_STORE_TTL_TOKENS: Final[tuple[str, ...]] = (
    "cleanup ",
    "delete after ",
    "expire after ",
    "expires ",
    "expires at ",
    "expires_at ",
    "expiration ",
    "expiry ",
    "retention ",
    "time to live ",
    "ttl",
)
DATA_STORE_SECRET_STORAGE_TOKENS: Final[tuple[str, ...]] = (
    "api key ",
    "apikey ",
    "auth ",
    "authorization ",
    "bearer ",
    "client secret ",
    "clientsecret ",
    "credential ",
    "password ",
    "refresh token ",
    "refresh_token ",
    "secret ",
    "token",
)
HTTP_FILE_UPLOAD_TOKENS: Final[tuple[str, ...]] = (
    "attachment ",
    "document ",
    "file ",
    "image ",
    "pdf ",
    "photo ",
    "upload",
)
HTTP_MULTIPART_TOKENS: Final[tuple[str, ...]] = (
    "formdata ",
    "multipart ",
    "multipartformdata",
)
HTTP_PARSE_RESPONSE_KEYS: Final[tuple[str, ...]] = (
    "parsedata ",
    "parsejson ",
    "parseresponse ",
    "parse_response",
)
HTTP_JSON_RESPONSE_PARSE_TOKENS: Final[tuple[str, ...]] = (
    "json parse ",
    "json records ",
    "json response ",
    "jsonparse ",
    "jsonrecords ",
    "jsonresponse ",
    "parse json ",
    "response json ",
    "responsejson",
)
HTTP_JSON_RESPONSE_EXPECTATION_TOKENS: Final[tuple[str, ...]] = (
    "json records ",
    "json response ",
    "jsonresponse ",
    "response json ",
    "responsejson",
)
HTTP_JSON_ACCEPT_HEADER_TOKENS: Final[tuple[str, ...]] = ("application/json",)
HTTP_REQUEST_BODY_KEYS: Final[tuple[str, ...]] = (
    "body ",
    "bodydata ",
    "payload ",
    "rawbody ",
    "requestbody ",
    "requestpayload",
)
HTTP_BODY_SIZE_BUDGET_TOKENS: Final[tuple[str, ...]] = (
    "body limit ",
    "body size budget ",
    "bodylimit ",
    "max body ",
    "max bytes ",
    "max payload ",
    "max request bytes ",
    "maxbody ",
    "maxbytes ",
    "maxpayload ",
    "payload limit ",
    "request body budget ",
    "requestbodybudget ",
    "size budget ",
    "size limit",
)
HTTP_SIZE_SENSITIVE_BODY_MAPPING_TOKENS: Final[tuple[str, ...]] = (
    "array ",
    "arrays ",
    "attachment ",
    "body ",
    "bundle ",
    "file ",
    "files ",
    "items ",
    "payload ",
    "rawbody ",
    "rawpayload ",
    "webhook",
)
HTTP_GET_BODY_ALLOWLIST_TOKENS: Final[tuple[str, ...]] = (
    "allow get body ",
    "body allowed on get ",
    "get body allowlist ",
    "getbodyallowlist ",
    "known nonstandard api ",
    "nonstandardapi",
)
HTTP_IDEMPOTENCY_EVIDENCE_TOKENS: Final[tuple[str, ...]] = (
    "dedupe key ",
    "dedupekey ",
    "deterministic transaction id ",
    "idempotency ",
    "idempotency key ",
    "idempotency-key ",
    "idempotencykey ",
    "idempotent ",
    "operation id ",
    "operationid ",
    "request id ",
    "requestid ",
    "transaction id ",
    "transactionid",
)
HTTP_PATCH_SEMANTICS_TOKENS: Final[tuple[str, ...]] = (
    "application/json-patch+json ",
    "application/merge-patch+json ",
    "json merge patch ",
    "json patch ",
    "jsonpatch ",
    "mergepatch ",
    "partial update ",
    "patch semantics ",
    "provider partial update ",
    "provider-specific partial update",
)
HTTP_PUT_REPLACEMENT_GUARD_TOKENS: Final[tuple[str, ...]] = (
    "convert to patch ",
    "converted to patch ",
    "full replacement ",
    "fullreplacement ",
    "partial update ",
    "put full replacement ",
    "put replacement ",
    "put semantics ",
    "putsemantics ",
    "replace resource ",
    "replacement acknowledged ",
    "replacement guard ",
    "replaces resource ",
    "use patch instead",
)
HTTP_DELETE_BODY_GUARD_TOKENS: Final[tuple[str, ...]] = (
    "delete body guard ",
    "delete body supported ",
    "delete body semantics ",
    "deletebody ",
    "deletebodyguard ",
    "provider supports delete body ",
    "provider-supported delete body",
)
HTTP_RESPONSE_BODY_EXPECTATION_KEYS: Final[tuple[str, ...]] = (
    "expectbody ",
    "expectedbody ",
    "outputbody ",
    "parsebody ",
    "parseresponse ",
    "responsebody ",
    "responsebodyschema ",
    "responseschema ",
    "returnbody",
)
HTTP_OPTIONS_ALLOWED_USE_TOKENS: Final[tuple[str, ...]] = (
    "capability discovery ",
    "capability probe ",
    "cors ",
    "cors check ",
    "options probe ",
    "options usage ",
    "optionsprobe ",
    "preflight",
)
HTTP_RESPONSE_SCHEMA_GUARD_TOKENS: Final[tuple[str, ...]] = (
    "data structure ",
    "datastructure ",
    "expected schema ",
    "fallback route ",
    "fallbackroute ",
    "response contract ",
    "response schema ",
    "responsebody schema ",
    "responsebodyschema ",
    "responseschema ",
    "schema guard ",
    "schema validation ",
    "schemaguard ",
    "typed response ",
    "validate schema",
)
HTTP_RESPONSE_SIZE_BUDGET_TOKENS: Final[tuple[str, ...]] = (
    "max response ",
    "max response bytes ",
    "max response size ",
    "response budget ",
    "response limit ",
    "response size budget ",
    "responsebudget ",
    "responselimit ",
    "responsesizebudget ",
    "size budget",
)
HTTP_ACCEPT_HEADER_FORBIDDEN_TOKENS: Final[tuple[str, ...]] = (
    "accept header forbidden ",
    "forbidden accept header ",
    "forbiddenacceptheader ",
    "forbids accept ",
    "forbids accept header ",
    "forbidsaccept ",
    "forbidsacceptheader ",
    "omit accept header ",
    "provider forbids accept ",
    "provider forbids accept header",
)
HTTP_RESPONSE_CONTENT_TYPE_GUARD_TOKENS: Final[tuple[str, ...]] = (
    "content type check ",
    "content type guard ",
    "content type validation ",
    "contenttypecheck ",
    "contenttypeguard ",
    "contenttypevalidation ",
    "json coercion ",
    "jsoncoercion ",
    "require json response ",
    "requirejsonresponse ",
    "response body coercion ",
    "response content type ",
    "response content type guard ",
    "responsecontenttype ",
    "responsecontenttypeguard ",
    "sanitize response body ",
    "sanitizeresponsebody ",
    "validate content type ",
    "validatecontenttype",
)
HTTP_PERMANENT_ERROR_STATUS_CODES: Final[frozenset[int]] = frozenset(
    (400, 401, 403)
)
HTTP_PERMANENT_ERROR_TOKENS: Final[tuple[str, ...]] = (
    "400 ",
    "401 ",
    "403 ",
    "bad request ",
    "badrequest ",
    "forbidden ",
    "malformed payload ",
    "malformedpayload ",
    "missing required field ",
    "missing required fields ",
    "missingrequiredfield ",
    "schema error ",
    "schemaerror ",
    "unauthorized ",
    "validation error ",
    "validationerror",
)
HTTP_AUTH_ERROR_STATUS_CODES: Final[frozenset[int]] = frozenset((401,))
HTTP_AUTH_ERROR_STATUS_TOKENS: Final[tuple[str, ...]] = (
    "401 ",
    "auth error ",
    "autherror ",
    "authentication error ",
    "credential error ",
    "invalid credential ",
    "unauthorized",
)
HTTP_AUTH_ERROR_HANDLING_TOKENS: Final[tuple[str, ...]] = (
    "401 auth branch ",
    "auth branch ",
    "auth error branch ",
    "auth refresh ",
    "authbranch ",
    "autherrorbranch ",
    "credential refresh ",
    "credentialrefresh ",
    "reauthenticate ",
    "token refresh ",
    "tokenrefresh ",
    "unauthorized branch",
)
HTTP_GENERIC_ERROR_CATCHALL_TOKENS: Final[tuple[str, ...]] = (
    "catch all ",
    "catch-all ",
    "catchall ",
    "default error ",
    "default error handler ",
    "default error route ",
    "generic error ",
    "generic error handler ",
    "generic error route ",
    "otherwise error ",
    "shared error handler ",
    "unclassified error",
)
HTTP_NOT_FOUND_STATUS_CODES: Final[frozenset[int]] = frozenset((404,))
HTTP_NOT_FOUND_STATUS_TOKENS: Final[tuple[str, ...]] = (
    "404 ",
    "not found ",
    "notfound",
)
HTTP_NOT_FOUND_CLASSIFICATION_TOKENS: Final[tuple[str, ...]] = (
    "404 classification ",
    "deleted upstream ",
    "deleted upstream object ",
    "expected missing resource ",
    "missing resource ",
    "missingresource ",
    "not found classification ",
    "notfoundclassification ",
    "stale reference ",
    "unexpected missing resource",
)
HTTP_CONFLICT_STATUS_CODES: Final[frozenset[int]] = frozenset((409,))
HTTP_CONFLICT_STATUS_TOKENS: Final[tuple[str, ...]] = ("409", "conflict")
HTTP_CONFLICT_HANDLING_TOKENS: Final[tuple[str, ...]] = (
    "409 conflict branch ",
    "conflict branch ",
    "conflict handling ",
    "conflict resolution ",
    "conflict route ",
    "conflictbranch ",
    "conflicthandling ",
    "conflictresolution ",
    "conflictroute",
)
HTTP_CONFLICT_RESUME_TOKENS: Final[tuple[str, ...]] = (
    "dedupe ",
    "dedupe key ",
    "dedupekey ",
    "duplicate key ",
    "existing resource ",
    "existingresource ",
    "get existing ",
    "idempotent resume ",
    "retrieve existing ",
    "retrieve existing resource ",
    "retrieveexisting ",
    "resume existing ",
    "resumeexisting ",
    "reuse existing",
)
HTTP_RATE_LIMIT_STATUS_CODES: Final[frozenset[int]] = frozenset((429,))
HTTP_RATE_LIMIT_STATUS_TOKENS: Final[tuple[str, ...]] = (
    "429 ",
    "rate limit ",
    "ratelimit",
)
HTTP_RATE_LIMIT_HANDLING_TOKENS: Final[tuple[str, ...]] = (
    "429 rate limit branch ",
    "rate limit backoff ",
    "rate limit branch ",
    "rate limit handling ",
    "rate limit route ",
    "ratelimitbranch ",
    "ratelimithandling ",
    "ratelimitroute ",
    "retry after ",
    "retryafter ",
    "throttle handling",
)
HTTP_SERVER_ERROR_STATUS_CODES: Final[frozenset[int]] = frozenset(
    range(500, 600)
)
HTTP_SERVER_ERROR_STATUS_TOKENS: Final[tuple[str, ...]] = (
    "5xx ",
    "500 ",
    "502 ",
    "503 ",
    "504 ",
    "server error ",
    "servererror",
)
HTTP_SERVER_ERROR_BACKOFF_TOKENS: Final[tuple[str, ...]] = (
    "bounded backoff ",
    "boundedbackoff ",
    "dead letter ",
    "deadletter ",
    "dlq ",
    "exponential backoff ",
    "exponentialbackoff ",
    "jitter ",
    "queue ",
    "queueing ",
    "server error backoff",
)
HTTP_STRUCTURED_RESPONSE_TOKENS: Final[tuple[str, ...]] = (
    "api ",
    "array ",
    "collection ",
    "data ",
    "json ",
    "records",
)
HTTP_CONTENT_TYPE_TOKENS: Final[tuple[str, ...]] = (
    "application/json ",
    "content type ",
    "json content",
)
HTTP_JSON_BODY_TOKENS: Final[tuple[str, ...]] = ("json",)
HTTP_RAW_BODY_TYPE_KEYS: Final[tuple[str, ...]] = (
    "bodytype ",
    "requestbodytype",
)
HTTP_RAW_BODY_TYPE_TOKENS: Final[tuple[str, ...]] = (
    "raw ",
    "raw body ",
    "rawbody",
)
HTTP_JSON_BODY_VALIDATION_TOKENS: Final[tuple[str, ...]] = (
    "json body validation ",
    "json validation ",
    "jsonbodyvalidation ",
    "parse json ",
    "parsejson ",
    "parsed json ",
    "parsedjson ",
    "valid json ",
    "validated json ",
    "validated json body ",
    "validate json ",
    "validate json body ",
    "validjson",
)
HTTP_UPSTREAM_STATUS_MAPPING_TOKENS: Final[tuple[str, ...]] = (
    "client status mapping ",
    "map upstream status ",
    "preserve upstream status ",
    "proxy status ",
    "status map ",
    "status mapping ",
    "status passthrough ",
    "statusmap ",
    "statusmapping ",
    "upstream status ",
    "upstream status mapping ",
    "upstreamstatus ",
    "upstreamstatusmapping",
)
HTTP_USER_AGENT_CONTEXT_HEADER_NAMES: Final[tuple[str, ...]] = (
    "user-agent ",
    "x-correlation-id ",
    "x-execution-id ",
    "x-request-id ",
    "x-scenario-id ",
    "x-trace-id",
)
HTTP_USER_AGENT_CONTEXT_TOKENS: Final[tuple[str, ...]] = (
    "execution context ",
    "scenario context ",
    "user agent ",
    "user-agent ",
    "useragent",
)
HTTP_HANDLE_ERRORS_KEY_TOKENS: Final[tuple[str, ...]] = ("handleerrors",)
SCENARIO_GOVERNANCE_PROFILE_TOKENS: Final[tuple[str, ...]] = (
    "business critical ",
    "business-critical ",
    "critical ",
    "deployment ",
    "environment ",
    "governance ",
    "production ",
    "prod ",
    "release ",
    "tier 1 ",
    "tier1",
)
SCENARIO_INCIDENT_PROFILE_TOKENS: Final[tuple[str, ...]] = (
    "business critical ",
    "business-critical ",
    "critical ",
    "incident ",
    "pager ",
    "tier 1 ",
    "tier1",
)
SCENARIO_OWNER_TOKENS: Final[tuple[str, ...]] = (
    "escalation ",
    "on call ",
    "on-call ",
    "oncall ",
    "owner ",
    "service owner ",
    "team",
)
SCENARIO_CHANGE_REASON_TOKENS: Final[tuple[str, ...]] = (
    "change reason ",
    "change ticket ",
    "change_reason ",
    "deployment reason ",
    "migration note ",
    "release note ",
    "release reason",
)
SCENARIO_ROLLBACK_TOKENS: Final[tuple[str, ...]] = (
    "previous blueprint hash ",
    "previous_blueprint_hash ",
    "restore plan ",
    "rollback ",
    "rollback plan",
)
SCENARIO_INCIDENT_NOTE_TOKENS: Final[tuple[str, ...]] = (
    "incident ",
    "on call ",
    "on-call ",
    "oncall ",
    "pager ",
    "runbook ",
    "severity",
)
SCENARIO_PRODUCTION_DEBUG_TOKENS: Final[tuple[str, ...]] = (
    "debug ",
    "debug log ",
    "test channel ",
    "throwaway datastore ",
    "verbose log ",
    "verbose logging",
)
HTTP_PROVIDER_FORBIDS_USER_AGENT_TOKENS: Final[tuple[str, ...]] = (
    "forbid user agent ",
    "forbids user-agent ",
    "provider forbids user agent ",
    "provider forbids user-agent",
)
HTTP_RESTORE_LABEL_AUTH_TOKENS: Final[tuple[str, ...]] = (
    "api key ",
    "apikey ",
    "auth ",
    "authentication ",
    "authorization ",
    "bearer ",
    "oauth ",
    "token",
)
HTTP_RUNTIME_AUTH_TOKENS: Final[tuple[str, ...]] = (
    "api key ",
    "apikey ",
    "auth ",
    "authentication ",
    "authorization ",
    "bearer ",
    "connection ",
    "oauth ",
    "token",
)
HTTP_LOCAL_HOSTS: Final[frozenset[str]] = frozenset(
    ("localhost", "127.0.0.1", "::1")
)
WEBHOOK_RESPONSE_STATUS_KEYS: Final[tuple[str, ...]] = (
    "code ",
    "responsecode ",
    "responsestatus ",
    "status ",
    "statuscode",
)
HTTP_SUCCESS_STATUS_KEYS: Final[tuple[str, ...]] = (
    "acceptedstatus ",
    "acceptedstatuses ",
    "expectedstatus ",
    "expectedstatuses ",
    "okstatus ",
    "okstatuses ",
    "statuscode ",
    "statuscodes ",
    "successstatus ",
    "successstatuses",
)
HTTP_SUCCESS_STATUS_MIN: Final = 200
HTTP_SUCCESS_STATUS_MAX: Final = 299
HTTP_EMPTY_BODY_STATUS_CODES: Final[frozenset[int]] = frozenset((204,))
HTTP_EMPTY_BODY_STATUS_TOKENS: Final[tuple[str, ...]] = (
    "204 ",
    "empty body ",
    "emptybody ",
    "empty response ",
    "emptyresponse ",
    "no content ",
    "nocontent",
)
HTTP_EMPTY_BODY_PARSE_GUARD_TOKENS: Final[tuple[str, ...]] = (
    "allow empty response ",
    "empty body guard ",
    "empty body parse guard ",
    "emptybodyguard ",
    "emptybodyparseguard ",
    "guard empty response ",
    "no content guard ",
    "no content parse guard ",
    "nocontentguard ",
    "nocontentparseguard ",
    "skip empty ",
    "skip json parse ",
    "skipempty ",
    "skipjsonparse",
)
HTTP_REDIRECT_ENABLED_TOKENS: Final[tuple[str, ...]] = (
    "allow redirects ",
    "allowredirects ",
    "follow redirects ",
    "followredirects ",
    "redirects enabled ",
    "redirectsenabled",
)
HTTP_REDIRECT_LIMIT_TOKENS: Final[tuple[str, ...]] = (
    "hop limit ",
    "hoplimit ",
    "max hops ",
    "maxhops ",
    "max redirects ",
    "maxredirects ",
    "redirect limit ",
    "redirectlimit",
)
HTTP_REDIRECT_HOST_POLICY_TOKENS: Final[tuple[str, ...]] = (
    "allowed hosts ",
    "allowed redirect hosts ",
    "host allowlist ",
    "redirect allowlist ",
    "redirect hosts ",
    "redirecthosts",
)
HTTP_REDIRECT_CREDENTIAL_POLICY_TOKENS: Final[tuple[str, ...]] = (
    "credential forwarding ",
    "credential policy ",
    "forward credentials ",
    "redirect credentials ",
    "redirectcredentials ",
    "strip authorization",
)
HTTP_WRITE_METHODS: Final[frozenset[str]] = frozenset(("PATCH", "POST", "PUT"))
HTTP_MUTATING_METHODS: Final[frozenset[str]] = HTTP_WRITE_METHODS | frozenset(
    ("DELETE",)
)
ITERATOR_ARRAY_INPUT_TOKENS: Final[tuple[str, ...]] = (
    "array ",
    "arrays ",
    "items ",
    "list ",
    "sourcearray",
)
ITERATOR_ITEM_LIMIT_TOKENS: Final[tuple[str, ...]] = (
    "batch size ",
    "bundle limit ",
    "chunk size ",
    "item count budget ",
    "item limit ",
    "limit ",
    "max bundles ",
    "max items ",
    "max records ",
    "maxitems ",
    "maxrecords ",
    "page size ",
    "record limit ",
    "slice",
)
AGGREGATOR_SOURCE_TOKENS: Final[tuple[str, ...]] = (
    "array ",
    "from ",
    "module ",
    "origin ",
    "source ",
    "source array ",
    "source module",
)
AGGREGATOR_BUNDLE_LIMIT_TOKENS: Final[tuple[str, ...]] = (
    "batch size ",
    "bundle count budget ",
    "bundle limit ",
    "bundlelimit ",
    "chunk size ",
    "input limit ",
    "limit ",
    "max bundles ",
    "max records ",
    "maxbundles ",
    "maxrecords ",
    "record limit ",
    "window",
)
AGGREGATOR_STRATEGY_TOKENS: Final[tuple[str, ...]] = (
    "aggregate ",
    "aggregation ",
    "columns ",
    "fields ",
    "format ",
    "function ",
    "group ",
    "groupby ",
    "row separator ",
    "separator ",
    "target structure",
)
TEXT_PARSER_INPUT_TOKENS: Final[tuple[str, ...]] = (
    "body ",
    "content ",
    "input ",
    "source ",
    "string ",
    "text",
)
TEXT_PARSER_PATTERN_TOKENS: Final[tuple[str, ...]] = (
    "pattern ",
    "regex ",
    "regexp ",
    "regular",
)
PARSE_JSON_SCHEMA_TOKENS: Final[tuple[str, ...]] = (
    "data structure ",
    "datastructure ",
    "expected schema ",
    "json schema ",
    "sample ",
    "schema ",
    "structure",
)
TOOL_CONTRACT_INPUT_TOKENS: Final[tuple[str, ...]] = (
    "input ",
    "inputs ",
    "input schema",
)
TOOL_CONTRACT_OUTPUT_TOKENS: Final[tuple[str, ...]] = (
    "output ",
    "outputs ",
    "output schema ",
    "return",
)
WEBHOOK_IP_ALLOWLIST_KEYS: Final[tuple[str, ...]] = (
    "allowlist ",
    "allowedips ",
    "allowedipaddresses ",
    "ipallowlist ",
    "ipfilter ",
    "ipwhitelist ",
    "whitelist",
)
WEBHOOK_SIGNATURE_TOKENS: Final[tuple[str, ...]] = (
    "digest ",
    "hash ",
    "hmac ",
    "sha256 ",
    "signature ",
    "signed ",
    "webhooksecret ",
    "xsignature",
)
WEBHOOK_ENCRYPTION_TOKENS: Final[tuple[str, ...]] = (
    "aes ",
    "cipher ",
    "encrypted ",
    "encryption ",
    "encrypt ",
    "pgp",
)
WEBHOOK_PROTECTED_TOKENS: Final[tuple[str, ...]] = (
    "auth ",
    "authorization ",
    "bank ",
    "bearer ",
    "card ",
    "credential ",
    "iban ",
    "payment ",
    "private ",
    "protected ",
    "secret ",
    "token",
)
WEBHOOK_SENSITIVE_TOKENS: Final[tuple[str, ...]] = (
    "accountnumber ",
    "bank ",
    "card ",
    "creditcard ",
    "iban ",
    "passport ",
    "payment ",
    "personaldata ",
    "pii ",
    "routingnumber ",
    "ssn",
)
WEBHOOK_PAYLOAD_CONTRACT_TOKENS: Final[tuple[str, ...]] = (
    "data structure ",
    "fields ",
    "interface ",
    "required ",
    "sample ",
    "schema ",
    "strict",
)
WEBHOOK_PAYLOAD_REQUEST_TOKENS: Final[tuple[str, ...]] = (
    "body ",
    "headers ",
    "json ",
    "payload ",
    "post ",
    "query ",
    "request",
)
WEBHOOK_TIMESTAMP_TOKENS: Final[tuple[str, ...]] = (
    "created at ",
    "createdat ",
    "sent at ",
    "sentat ",
    "timestamp ",
    "x timestamp ",
    "xtimestamp",
)
WEBHOOK_DRIFT_WINDOW_TOKENS: Final[tuple[str, ...]] = (
    "drift ",
    "expires ",
    "max age ",
    "maxage ",
    "replay window ",
    "time window ",
    "tolerance ",
    "window",
)
WEBHOOK_PAYLOAD_SIZE_BUDGET_TOKENS: Final[tuple[str, ...]] = (
    "bodylimit ",
    "content length ",
    "max body ",
    "max bytes ",
    "max payload ",
    "maxpayload ",
    "payload budget ",
    "payload limit ",
    "payload size ",
    "payloadsize ",
    "size limit",
)
WEBHOOK_RESPONSE_BODY_SIZE_LIMIT_BYTES: Final = 5 * 1024 * 1024
WEBHOOK_RESPONSE_BODY_CONTENT_KEYS: Final[tuple[str, ...]] = (
    "body ",
    "content ",
    "responsebody",
)
WEBHOOK_RESPONSE_BODY_SIZE_KEYS: Final[tuple[str, ...]] = (
    "body bytes ",
    "body length ",
    "body size ",
    "body size bytes ",
    "bodybytes ",
    "bodysizebytes ",
    "content length ",
    "contentlength ",
    "response body bytes ",
    "response body length ",
    "response body size ",
    "response body size bytes ",
    "responsebodybytes ",
    "responsebodysize ",
    "responsebodysizebytes",
)
WEBHOOK_RESPONSE_CONTENT_TYPE_TOKENS: Final[tuple[str, ...]] = (
    "application/json ",
    "application/xml ",
    "text/html ",
    "text/plain ",
    "text/xml",
)
WEBHOOK_HTTP_METHOD_VALUES: Final[frozenset[str]] = frozenset(
    ("DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT")
)
WEBHOOK_METHOD_GUARD_KEYS: Final[tuple[str, ...]] = (
    "acceptedmethod ",
    "acceptedmethods ",
    "allowedmethod ",
    "allowedmethods ",
    "httpmethod ",
    "method ",
    "requestmethod ",
    "supportedmethod ",
    "supportedmethods",
)
WEBHOOK_CONCURRENCY_BUDGET_TOKENS: Final[tuple[str, ...]] = (
    "concurrency ",
    "concurrency budget ",
    "concurrency limit ",
    "max concurrency ",
    "parallelism ",
    "rate limit ",
    "ratelimit ",
    "sequential processing ",
    "worker limit ",
    "workerlimit",
)
WEBHOOK_BACKPRESSURE_TOKENS: Final[tuple[str, ...]] = (
    "backpressure ",
    "burst ",
    "concurrency ",
    "concurrency budget ",
    "concurrency limit ",
    "dead letter ",
    "debounce ",
    "dedupe ",
    "deduplicate ",
    "dlq ",
    "queue ",
    "queue consumer ",
    "rate limit ",
    "ratelimit ",
    "sequential processing ",
    "token bucket ",
    "worker limit ",
    "workerlimit",
)
MAILHOOK_SENDER_ALLOWLIST_TOKENS: Final[tuple[str, ...]] = (
    "allowed domain ",
    "allowed domains ",
    "allowed sender ",
    "allowed senders ",
    "from allowlist ",
    "sender allowlist ",
    "sender domain allowlist ",
    "sender domains ",
    "trusted domain ",
    "trusted sender",
)
TRANSACTION_SAFETY_POSTURE_TOKENS: Final[tuple[str, ...]] = (
    "audit ",
    "backup ",
    "compensate ",
    "compensation ",
    "dedupe ",
    "deduplicate ",
    "idempotency ",
    "idempotent ",
    "recover ",
    "recovery ",
    "restore ",
    "rollback ",
    "undo",
)
ROLLBACK_SAFE_CAPABILITIES: Final[frozenset[str]] = frozenset(
    ("acid", "native")
)
MAKE_DESIGNER_WARNING_CLIENT_PREFIX: Final = "MAKE-DESIGNER-WARN"
WEBHOOK_BACKPRESSURE_MISSING_CODE: Final = "webhook.backpressure_missing"
WEBHOOK_INGRESS_BUDGET_MISSING_CODE: Final = "webhook.ingress_budget_missing"
WEBHOOK_METHOD_GUARD_MISSING_CODE: Final = "webhook.method_guard_missing"
WEBHOOK_RESPONSE_BODY_SIZE_LIMIT_CODE: Final = (
    "webhook.response_body_size_limit_exceeded"
)
WEBHOOK_RESPONSE_CONTENT_TYPE_MISSING_CODE: Final = (
    "webhook.response_content_type_missing"
)
HTTP_SUCCESS_STATUS_CONTRACT_MISSING_CODE: Final = (
    "http.success_status_contract_missing"
)
HTTP_REDIRECT_POLICY_MISSING_CODE: Final = "http.redirect_policy_missing"
HTTP_AUTHORIZATION_REDIRECT_LEAK_CODE: Final = (
    "http.authorization_redirect_leak"
)
HTTP_EMPTY_BODY_PARSE_GUARD_MISSING_CODE: Final = (
    "http.empty_body_parse_guard_missing"
)
HTTP_RESPONSE_CONTENT_TYPE_GUARD_MISSING_CODE: Final = (
    "http.response_content_type_guard_missing"
)
HTTP_PERMANENT_ERROR_RETRY_POLICY_CODE: Final = (
    "http.permanent_error_retry_policy"
)
HTTP_NOT_FOUND_CLASSIFICATION_MISSING_CODE: Final = (
    "http.not_found_classification_missing"
)
HTTP_CONFLICT_BRANCH_MISSING_CODE: Final = "http.conflict_branch_missing"
HTTP_RATE_LIMIT_BRANCH_MISSING_CODE: Final = "http.rate_limit_branch_missing"
HTTP_SERVER_ERROR_BACKOFF_MISSING_CODE: Final = (
    "http.server_error_backoff_missing"
)
HTTP_ACCEPT_HEADER_MISSING_CODE: Final = "http.accept_header_missing"
HTTP_GET_BODY_NOT_ALLOWED_CODE: Final = "http.get_body_not_allowed"
HTTP_CONFLICT_RESUME_MISSING_CODE: Final = "http.conflict_resume_missing"
HTTP_RETRYABLE_MUTATION_IDEMPOTENCY_MISSING_CODE: Final = (
    "http.retryable_mutation_idempotency_missing"
)
HTTP_PATCH_SEMANTICS_MISSING_CODE: Final = "http.patch_semantics_missing"
HTTP_PUT_REPLACEMENT_GUARD_MISSING_CODE: Final = (
    "http.put_replacement_guard_missing"
)
HTTP_DELETE_BODY_GUARD_MISSING_CODE: Final = "http.delete_body_guard_missing"
HTTP_HEAD_RESPONSE_BODY_EXPECTED_CODE: Final = (
    "http.head_response_body_expected"
)
HTTP_OPTIONS_USAGE_GUARD_MISSING_CODE: Final = (
    "http.options_usage_guard_missing"
)
HTTP_RESPONSE_SCHEMA_GUARD_MISSING_CODE: Final = (
    "http.response_schema_guard_missing"
)
HTTP_REQUEST_BODY_SIZE_BUDGET_MISSING_CODE: Final = (
    "http.request_body_size_budget_missing"
)
HTTP_RESPONSE_SIZE_BUDGET_MISSING_CODE: Final = (
    "http.response_size_budget_missing"
)
HTTP_BLIND_ERROR_CATCHALL_CODE: Final = "http.blind_error_catchall"
HTTP_ERROR_STATUS_EVALUATION_DISABLED_CODE: Final = (
    "http.error_status_evaluation_disabled"
)
HTTP_RAW_JSON_BODY_VALIDATION_MISSING_CODE: Final = (
    "http.raw_json_body_validation_missing"
)
HTTP_JSON_BODY_SYNTAX_INVALID_CODE: Final = "http.json_body_syntax_invalid"
HTTP_UPSTREAM_STATUS_MAPPING_MISSING_CODE: Final = (
    "http.upstream_status_mapping_missing"
)
HTTP_USER_AGENT_CONTEXT_MISSING_CODE: Final = "http.user_agent_context_missing"
HTTP_RESTORE_LABEL_DEPENDENCY_CODE: Final = "http.restore_label_dependency"
MAILHOOK_SENDER_ALLOWLIST_MISSING_CODE: Final = (
    "webhook.mailhook_sender_allowlist_missing"
)
WEBHOOK_SIGNATURE_TIMESTAMP_MISSING_CODE: Final = (
    "webhook.signature_timestamp_missing"
)


def validate_blueprint(
    *,
    root: MakeAstRoot,
    catalog: CatalogSnapshot,
    knowledge: KnowledgeStoreQuery | None = None,
) -> BlueprintValidationReport:
    """Validate a parsed Make blueprint AST against the canonical catalog.

    Returns:
    The validation result for a parsed Make blueprint AST against the canonical
    catalog.
    """
    nodes = iter_ast_nodes(root)
    shape_findings = _validate_ast_shape_safety(root=root, nodes=nodes)
    resolution_report = resolve_ast_modules(root=root, catalog=catalog)
    resolution_pairs = _module_resolution_pairs(
        nodes=nodes,
        resolutions=resolution_report.resolutions,
    )
    resolutions_by_node_identity = {
        id(node): resolution for node, resolution in resolution_pairs
    }
    modules_by_id = _catalog_modules_by_id(catalog)
    findings: list[BlueprintValidationFinding] = []
    findings.extend(shape_findings)
    findings.extend(
        _validate_module_resolutions(
            resolution_pairs=resolution_pairs,
            modules_by_id=modules_by_id,
            knowledge=knowledge,
        )
    )
    findings.extend(
        _validate_raw_spec_binding_hashes(
            root=root,
            resolution_pairs=resolution_pairs,
        )
    )
    findings.extend(validate_routes(nodes))
    findings.extend(_validate_schedule(root.scenario.schedule))
    findings.extend(validate_ai_agent_contracts(nodes))
    findings.extend(_validate_webhook_responses(root=root, nodes=nodes))
    findings.extend(_validate_webhook_response_content_types(nodes))
    findings.extend(_validate_webhook_response_body_size_limits(nodes))
    findings.extend(_validate_webhook_ingress_budgets(nodes))
    findings.extend(_validate_webhook_method_guards(nodes))
    findings.extend(_validate_webhook_backpressure(nodes))
    findings.extend(_validate_http_semantic_rules(nodes))
    findings.extend(_validate_mailhook_sender_allowlists(nodes))
    findings.extend(_validate_webhook_signature_timestamps(nodes))
    findings.extend(
        validate_http_url_security(
            nodes, scenario_metadata=root.scenario.metadata
        )
    )
    findings.extend(validate_data_exposure_security(nodes))
    findings.extend(validate_note_content_security(root=root, nodes=nodes))
    findings.extend(validate_crypto_security(nodes))
    findings.extend(validate_sql_security(nodes))
    findings.extend(
        validate_graphql_security(
            nodes, scenario_metadata=root.scenario.metadata
        )
    )
    findings.extend(validate_redirect_security(nodes))
    findings.extend(validate_content_injection_security(nodes))
    findings.extend(
        _validate_knowledge_promoted_rules(
            root=root, nodes=nodes, knowledge=knowledge
        )
    )
    findings.extend(_validate_semantic_module_usage(nodes))
    findings.extend(_validate_operation_volume_review(nodes))
    findings.extend(_validate_designer_runtime_messages(nodes))
    findings.extend(
        _validate_trigger_semantics(
            nodes=nodes,
            resolutions_by_node_identity=resolutions_by_node_identity,
        )
    )
    findings.extend(validate_scenario_cycles(root))
    findings.extend(validate_output_references(root))
    findings.extend(_validate_mapping_risks(root))
    findings.extend(validate_importability(nodes, root=root))
    return BlueprintValidationReport(
        catalog_fingerprint=resolution_report.catalog_fingerprint,
        findings=tuple(findings),
    )


def _module_resolution_pairs(
    *,
    nodes: tuple[MakeAstNode, ...],
    resolutions: tuple[MakeAstModuleResolution, ...],
) -> tuple[tuple[MakeAstNode, MakeAstModuleResolution], ...]:
    """Pair module-like nodes with resolver output without collapsing duplicate.

    IDs.

    Returns:
        Node and resolution pairs in module-node order.
    """
    module_nodes = tuple(node for node in nodes if node.module_token)
    return tuple(zip(module_nodes, resolutions, strict=True))


def _validate_module_resolutions(
    *,
    resolution_pairs: tuple[tuple[MakeAstNode, MakeAstModuleResolution], ...],
    modules_by_id: dict[str, CatalogModule],
    knowledge: KnowledgeStoreQuery | None,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate catalog resolution and required module mappings.

    Returns:
    The validation result for catalog resolution and required module mappings.
    """
    findings: list[BlueprintValidationFinding] = []
    for node, resolution in resolution_pairs:
        if resolution.status != RESOLVED_STATUS:
            findings.append(
                _unresolved_module_finding(resolution=resolution, node=node)
            )
            continue
        module = _resolved_module(
            resolution=resolution, modules_by_id=modules_by_id
        )
        if module is None:
            findings.append(
                _missing_catalog_record_finding(
                    resolution=resolution, node=node
                )
            )
            continue
        findings.extend(
            _validate_raw_spec_binding_version(
                node=node, module=module, resolution=resolution
            )
        )
        findings.extend(_validate_required_parameters(node=node, module=module))
        findings.extend(_validate_deprecated_module(node=node, module=module))
        findings.extend(
            _validate_error_handlers(
                node=node, module=module, knowledge=knowledge
            )
        )
    return tuple(findings)


def _validate_raw_spec_binding_hashes(
    *,
    root: MakeAstRoot,
    resolution_pairs: tuple[tuple[MakeAstNode, MakeAstModuleResolution], ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Require raw-spec hash evidence only for import-ready or stronger claims.

    Returns:
    The validation result for readiness-scoped raw-spec binding hash evidence.
    """
    if not _requires_raw_spec_hash_evidence(root):
        return ()
    return tuple(
        _raw_spec_binding_hash_missing_finding(node=node, resolution=resolution)
        for node, resolution in resolution_pairs
        if resolution.status == RESOLVED_STATUS
        and not node.raw_spec_binding.raw_spec_sha256
    )


def _requires_raw_spec_hash_evidence(root: MakeAstRoot) -> bool:
    """Return if root metadata claims catalog-backed readiness or stronger."""
    return _json_has_exact_text(
        root.scenario.metadata,
        values=RAW_SPEC_HASH_CLAIM_LEVELS | RAW_SPEC_HASH_ARTIFACT_PHASES,
    ) or _json_has_exact_text(
        root.raw_payload.get("artifact_phase"),
        values=RAW_SPEC_HASH_ARTIFACT_PHASES,
    )


def _json_has_exact_text(value: object, *, values: frozenset[str]) -> bool:
    """Return if JSON-like data contains one exact normalized text value."""
    if isinstance(value, str):
        return value.strip().casefold() in values
    if _is_json_object(value):
        return any(
            _json_has_exact_text(item, values=values) for item in value.values()
        )
    if isinstance(value, list):
        return any(
            _json_has_exact_text(item, values=values)
            for item in cast("list[object]", value)
        )
    return False


def _validate_raw_spec_binding_version(
    *,
    node: MakeAstNode,
    module: CatalogModule,
    resolution: MakeAstModuleResolution,
) -> tuple[BlueprintValidationFinding, ...]:
    """Emit nonblocking refresh guidance for stale raw-spec module metadata.

    Returns:
        The validation findings for stale raw-spec binding metadata.
    """
    if RAW_SPEC_BINDING_VERSION_DRIFT not in resolution.issues:
        return ()
    stale_module_id = node.raw_spec_binding.catalog_module_id or "<missing>"
    return (
        build_validation_finding(
            code=RAW_SPEC_BINDING_VERSION_DRIFT_CODE,
            severity="warning",
            node=(node.node_id, node.source_trace.path),
            catalog_module_id=module.module_id,
            messages=(
                (
                    "A raw-spec module binding should be refreshed to the "
                    "current catalog module."
                ),
                " ".join(
                    (
                        (
                            f"Node {node.node_id} "
                            f"metadata.raw_spec.catalog_module_id"
                        ),
                        (
                            f"{stale_module_id!r} is stale; refresh it to "
                            f"{module.module_id!r}."
                        ),
                    )
                ),
            ),
        ),
    )


def _raw_spec_binding_hash_missing_finding(
    *,
    node: MakeAstNode,
    resolution: MakeAstModuleResolution,
) -> BlueprintValidationFinding:
    """Return the computed result for the caller."""
    catalog_module_id = resolution.catalog_module_id
    internal_message = " ".join(
        (
            f"Node {node.node_id} resolves to catalog module",
            (
                f"{catalog_module_id or '<unknown>'} without "
                f"metadata.raw_spec.raw_spec_sha256."
            ),
        )
    )
    return build_validation_finding(
        code=RAW_SPEC_BINDING_HASH_MISSING_CODE,
        severity="error",
        node=(node.node_id, node.source_trace.path),
        catalog_module_id=catalog_module_id,
        messages=(
            (
                "A catalog-backed readiness claim is missing raw-spec hash "
                "evidence."
            ),
            internal_message,
        ),
    )


def _validate_required_parameters(
    *,
    node: MakeAstNode,
    module: CatalogModule,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate required parameter mappings for one resolved module.

    Returns:
    The validation result for required parameter mappings for one resolved
    module.
    """
    findings: list[BlueprintValidationFinding] = []
    findings.extend(_validate_mapping_object(node=node, key="parameters"))
    findings.extend(_validate_mapping_object(node=node, key="mapper"))
    for field in module.parameters:
        if not field.required or _field_is_mapped(node=node, field=field):
            continue
        field_path = ".".join(field.path)
        internal_message = " ".join(
            (
                f"Node {node.node_id} is missing required parameter",
                f"{field.field_id} at {field_path}.",
            )
        )
        findings.append(
            build_validation_finding(
                code="mapping.required_parameter_missing",
                severity="error",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=module.module_id,
                messages=(
                    "A required module field is not mapped.",
                    internal_message,
                ),
            )
        )
    return tuple(findings)


def _validate_mapping_object(
    *,
    node: MakeAstNode,
    key: str,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate a node mapping container when it is present.

    Returns:
        The validation result for a node mapping container when it is present.
    """
    value = node.raw_payload.get(key)
    if value is None or isinstance(value, dict):
        return ()
    return (
        build_validation_finding(
            code=f"mapping.{key}_not_object",
            severity="error",
            node=(node.node_id, node.source_trace.path),
            catalog_module_id=None,
            messages=(
                "A module mapping container has an invalid shape.",
                f"Node {node.node_id} field {key!r} must be an object.",
            ),
        ),
    )


def _validate_deprecated_module(
    *,
    node: MakeAstNode,
    module: CatalogModule,
) -> tuple[BlueprintValidationFinding, ...]:
    """Emit warning metadata for deprecated resolved modules.

    Returns:
        The documented result.
    """
    if not module.deprecated:
        return ()
    return (
        build_validation_finding(
            code=DEPRECATED_MODULE,
            severity="warning",
            node=(node.node_id, node.source_trace.path),
            catalog_module_id=module.module_id,
            messages=(
                "A resolved Make module is deprecated.",
                (
                    f"Node {node.node_id} resolves to deprecated module "
                    f"{module.module_id}."
                ),
            ),
        ),
    )


def _validate_error_handlers(
    *,
    node: MakeAstNode,
    module: CatalogModule,
    knowledge: KnowledgeStoreQuery | None,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate basic error-route coverage for mutating catalog modules.

    Returns:
    The validation result for basic error-route coverage for mutating catalog
    modules.
    """
    if module.module_kind not in MUTATING_MODULE_KINDS or node.error_handlers:
        return ()
    rule = (
        None
        if knowledge is None
        else knowledge.rule_by_code("error_route.missing")
    )
    severity = (
        "optimization" if rule is None else _knowledge_severity(rule.severity)
    )
    rule_message = (
        f"Node {node.node_id} has no direct error handler."
        if rule is None
        else (
            f"Node {node.node_id} violates {rule.rule_id} from"
            f"{rule.adr_anchor}."
        )
    )
    return (
        build_validation_finding(
            code="error_route.missing",
            severity=severity,
            node=(node.node_id, node.source_trace.path),
            catalog_module_id=module.module_id,
            messages=(
                "A module can be improved with an error handler.",
                rule_message,
            ),
        ),
    )


def _validate_ast_shape_safety(
    *,
    root: MakeAstRoot,
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate raw node shapes that can break Make import/render safety.

    Returns:
    The validation result for raw node shapes that can break Make import/render
    safety.
    """
    findings: list[BlueprintValidationFinding] = []
    findings.extend(
        validate_root_notes(
            root.scenario.metadata.get("notes"),
            {node.node_id for node in nodes},
        )
    )
    findings.extend(_validate_duplicate_node_ids(nodes))
    for node in nodes:
        if "module" in node.raw_payload and not isinstance(
            node.raw_payload["module"], str
        ):
            invalid_module_token = node.raw_payload["module"]
            internal_message = " ".join(
                (
                    f"Node {node.node_id} uses invalid module token",
                    f"{_json_value_type_label(invalid_module_token)}.",
                )
            )
            findings.append(
                build_validation_finding(
                    code="ast.module_token_invalid",
                    severity="error",
                    node=(node.node_id, node.source_trace.path),
                    catalog_module_id=None,
                    messages=(
                        "A module token has an invalid JSON type.",
                        internal_message,
                    ),
                )
            )
        if isinstance(node.raw_payload.get("id"), bool):
            findings.append(
                build_validation_finding(
                    code="ast.node_id_boolean",
                    severity="error",
                    node=(node.node_id, node.source_trace.path),
                    catalog_module_id=None,
                    messages=(
                        "A module ID has an invalid JSON type.",
                        (
                            f"Node at {node.source_trace.path!r} uses a "
                            f"boolean "
                            f"ID."
                        ),
                    ),
                )
            )
        findings.extend(_validate_node_id_shape(node))
        version = node.raw_payload.get("version")
        if _invalid_node_version(version):
            findings.append(
                build_validation_finding(
                    code="ast.node_version_invalid",
                    severity="error",
                    node=(node.node_id, node.source_trace.path),
                    catalog_module_id=None,
                    messages=(
                        "A module version has an invalid JSON type.",
                        (
                            f"Node {node.node_id} uses invalid version "
                            f"{_json_value_type_label(version)}."
                        ),
                    ),
                )
            )
        findings.extend(_validate_metadata_container_shape(node))
        findings.extend(_validate_designer_container_shape(node))
        findings.extend(_validate_designer_shape(node))
        findings.extend(_validate_error_handler_shapes(node))
    return tuple(findings)


def _invalid_node_version(value: object) -> bool:
    """Return whether a present node version is not a positive integer."""
    if value is None:
        return False
    if isinstance(value, bool):
        return True
    return not isinstance(value, int) or value <= 0


def _validate_node_id_shape(
    node: MakeAstNode,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate present node IDs that are not usable string or positive integer.

    IDs.

    Returns:
        The validation result for present node IDs that are not usable string or
        positive integer IDs.
    """
    if "id" not in node.raw_payload:
        return ()
    raw_id = node.raw_payload["id"]
    if isinstance(raw_id, bool):
        return ()
    if isinstance(raw_id, int) and raw_id > 0:
        return ()
    if isinstance(raw_id, str) and raw_id.strip():
        return ()
    return (
        build_validation_finding(
            code="ast.node_id_invalid",
            severity="error",
            node=(node.node_id, node.source_trace.path),
            catalog_module_id=None,
            messages=(
                "A module ID has an invalid value or JSON type.",
                (
                    f"Node at {node.source_trace.path!r} uses invalid ID "
                    f"{_json_value_type_label(raw_id)}."
                ),
            ),
        ),
    )


def _json_value_type_label(value: object) -> str:
    """Return a typed JSON value label for diagnostics."""
    if isinstance(value, bool):
        label = f"<boolean {str(value).casefold()}>"
    elif value is None:
        label = "<null>"
    elif isinstance(value, str):
        label = repr(value)
    elif isinstance(value, int | float):
        label = f"<number {value}>"
    elif isinstance(value, list):
        label = "<array>"
    elif isinstance(value, dict):
        label = "<object>"
    else:
        label = f"<{type(value).__name__}>"
    return label


def _validate_duplicate_node_ids(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate that AST node IDs are unique before ID-keyed consumers run.

    Returns:
    The validation result for that AST node IDs are unique before ID-keyed
    consumers run.
    """
    seen: set[str] = set()
    reported: set[str] = set()
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if node.node_id not in seen:
            seen.add(node.node_id)
            continue
        if node.node_id in reported:
            continue
        reported.add(node.node_id)
        findings.append(
            build_validation_finding(
                code="ast.node_id_duplicate",
                severity="error",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    "A module ID appears more than once.",
                    (
                        f"Node ID {node.node_id!r} appears more than once in "
                        f"the AST."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_metadata_container_shape(
    node: MakeAstNode,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate node metadata before metadata-backed checks read it.

    Returns:
        Metadata-container validation findings.
    """
    if "metadata" not in node.raw_payload or _is_json_object(
        node.raw_payload.get("metadata")
    ):
        return ()
    return (
        build_validation_finding(
            code="ast.metadata_invalid",
            severity="error",
            node=(node.node_id, node.source_trace.path),
            catalog_module_id=None,
            messages=(
                "A module metadata container has an invalid shape.",
                f"Node {node.node_id} metadata must be an object when present.",
            ),
        ),
    )


def _validate_designer_container_shape(
    node: MakeAstNode,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate designer containers before reading nested designer payloads.

    Returns:
    The validation result for designer containers before reading nested designer
    payloads.
    """
    metadata = node.raw_payload.get("metadata")
    if not _is_json_object(metadata):
        return ()
    designer = metadata.get("designer")
    if designer is None or _is_json_object(designer):
        return ()
    return (
        build_validation_finding(
            code="ast.designer_invalid",
            severity="error",
            node=(node.node_id, node.source_trace.path),
            catalog_module_id=None,
            messages=(
                "A module designer container has an invalid shape.",
                f"Node {node.node_id} designer metadata must be an object.",
            ),
        ),
    )


def _validate_designer_shape(
    node: MakeAstNode,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate one node designer payload when it is present.

    Returns:
        The validation result for one node designer payload when it is present.
    """
    metadata = _object_or_empty(node.raw_payload.get("metadata"))
    designer = _object_or_empty(metadata.get("designer"))
    findings: list[BlueprintValidationFinding] = []
    if {"x", "y"}.issubset(designer) and not _has_integer_coordinates(designer):
        findings.append(
            build_validation_finding(
                code="ast.designer_coordinates_invalid",
                severity="error",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    "A module designer position has invalid coordinates.",
                    f"Node {node.node_id} has malformed designer coordinates.",
                ),
            )
        )
    if "messages" in designer and not isinstance(
        designer.get("messages"), list
    ):
        findings.append(
            build_validation_finding(
                code="ast.designer_messages_invalid",
                severity="error",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    "A module designer message list has an invalid shape.",
                    f"Node {node.node_id} has malformed designer messages.",
                ),
            )
        )
    return tuple(findings)


def _validate_error_handler_shapes(
    node: MakeAstNode,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate direct error-handler export shapes.

    Returns:
        The validation result for direct error-handler export shapes.
    """
    findings: list[BlueprintValidationFinding] = []
    for error_key in DIRECT_ERROR_KEYS:
        raw_handlers = node.raw_payload.get(error_key)
        if raw_handlers is None:
            continue
        if isinstance(raw_handlers, list) and not raw_handlers:
            findings.append(_error_handler_empty_finding(node, error_key))
            continue
        handlers: list[object] = (
            cast("list[object]", raw_handlers)
            if isinstance(raw_handlers, list)
            else [raw_handlers]
        )
        for index, handler in enumerate(handlers, start=1):
            if _empty_error_handler_child(handler):
                findings.append(_error_handler_empty_finding(node, error_key))
                continue
            if not _valid_error_handler_child(handler):
                findings.append(
                    _error_handler_shape_finding(node, error_key, index)
                )
    return tuple(findings)


def _empty_error_handler_child(value: object) -> bool:
    """Return whether one direct error-handler child declares an empty flow.

    wrapper.
    """
    if not _is_json_object(value):
        return False
    flow = value.get("flow")
    return isinstance(flow, list) and not flow


def _valid_error_handler_child(value: object) -> bool:
    """Return if one direct error-handler child has an import-safe shape."""
    if not _is_json_object(value):
        return False
    if "module" in value:
        return True
    flow = value.get("flow")
    if not isinstance(flow, list) or not flow:
        return False
    return all(
        _valid_error_handler_child(child)
        for child in cast("list[object]", flow)
    )


def _error_handler_shape_finding(
    node: MakeAstNode,
    error_key: str,
    index: int,
) -> BlueprintValidationFinding:
    """Return one error-handler shape finding."""
    return build_validation_finding(
        code="ast.error_handler_child_invalid",
        severity="error",
        node=(node.node_id, node.source_trace.path),
        catalog_module_id=None,
        messages=(
            "An error handler has an invalid Make import shape.",
            (
                f"Node {node.node_id} {error_key}[{index}] must be a module or "
                f"flow wrapper."
            ),
        ),
    )


def _error_handler_empty_finding(
    node: MakeAstNode,
    error_key: str,
) -> BlueprintValidationFinding:
    """Return one empty error-handler finding."""
    return build_validation_finding(
        code="ast.error_handler_empty",
        severity="error",
        node=(node.node_id, node.source_trace.path),
        catalog_module_id=None,
        messages=(
            "An error handler must declare a deterministic recovery path.",
            (
                f"Node {node.node_id} {error_key} is present but contains no "
                f"handler modules."
            ),
        ),
    )


def _validate_schedule(
    schedule: MakeAstScheduleConfig | None,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate schedule or trigger basics.

    Returns:
        The validation result for schedule or trigger basics.
    """
    if schedule is None:
        return (
            build_validation_finding(
                code="schedule.missing",
                severity="explanation",
                node=(None, ()),
                catalog_module_id=None,
                messages=(
                    "No schedule or trigger metadata is declared.",
                    "The AST root has no schedule or trigger metadata.",
                ),
            ),
        )
    schedule_id = schedule.raw_payload.get("id")
    if _invalid_schedule_id(schedule_id):
        return (
            build_validation_finding(
                code="schedule.id_invalid",
                severity="error",
                node=(None, ("metadata", "schedule", "id")),
                catalog_module_id=None,
                messages=(
                    "Schedule metadata has an invalid identifier.",
                    (
                        "Schedule ID must be a non-empty string when "
                        "present; received "
                        f"{_json_value_type_label(schedule_id)}. Raw "
                        f"schedule metadata "
                        "is redacted."
                    ),
                ),
            ),
        )
    if schedule.raw_payload:
        interval_minutes = _schedule_interval_minutes(schedule.raw_payload)
        if interval_minutes is not None and interval_minutes < 1:
            return (
                build_validation_finding(
                    code=SCHEDULE_SUB_MINUTE_INTERVAL_CODE,
                    severity="warning",
                    node=(None, ("metadata", "schedule")),
                    catalog_module_id=None,
                    messages=(
                        "Schedule metadata declares a sub-minute cadence.",
                        (
                            f"Schedule {schedule.schedule_id} has a local "
                            f"cadence of "
                            f"{interval_minutes:g} minutes."
                        ),
                    ),
                ),
            )
        return ()
    return (
        build_validation_finding(
            code="schedule.empty",
            severity="warning",
            node=(None, ()),
            catalog_module_id=None,
            messages=(
                "Schedule metadata is empty.",
                f"Schedule {schedule.schedule_id} has no payload fields.",
            ),
        ),
    )


def _invalid_schedule_id(value: object) -> bool:
    """Return whether a present schedule ID is not explicit non-empty text."""
    if value is None:
        return False
    return not isinstance(value, str) or not value.strip()


def _schedule_interval_minutes(payload: JsonObject) -> float | None:
    """Return explicit schedule cadence in minutes when local metadata carries.

    it.
    """
    every_minutes = _positive_json_number(payload.get("every_minutes"))
    if every_minutes is not None:
        return every_minutes
    every = _positive_json_number(payload.get("every"))
    unit = _optional_json_text(payload.get("unit"))
    if every is not None and unit is not None:
        unit_minutes = _schedule_unit_minutes(unit)
        if unit_minutes > 0:
            return every * unit_minutes
    interval_seconds = _positive_json_number(payload.get("interval"))
    if interval_seconds is not None:
        return interval_seconds / 60
    return None


def _positive_json_number(value: object) -> float | None:
    """Return a finite positive number from JSON-like schedule metadata."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        parsed = float(value)
        return parsed if parsed > 0 and math.isfinite(parsed) else None
    if isinstance(value, str):
        try:
            parsed = float(value.strip())
        except ValueError:
            return None
        return parsed if parsed > 0 and math.isfinite(parsed) else None
    return None


def _optional_json_text(value: object) -> str | None:
    """Return non-empty text from JSON-like metadata."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _schedule_unit_minutes(unit: str) -> float:
    """Return minutes for one supported local schedule unit."""
    normalized = unit.casefold().rstrip("s")
    if normalized in {"m", "min", "minute"}:
        return 1
    if normalized in {"h", "hr", "hour"}:
        return 60
    if normalized in {"d", "day", "daily"}:
        return 1_440
    if normalized in {"w", "week", "weekly"}:
        return 10_080
    if normalized in {"s", "sec", "second"}:
        return 1 / 60
    return 0


def _validate_webhook_responses(
    *,
    root: MakeAstRoot,
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate basic webhook response declaration risks.

    Returns:
        The validation result for basic webhook response declaration risks.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if (
            node.kind != "webhook"
            or module_looks_like_webhook_response(node.module_token)
            or webhook_has_response_on_all_paths(root=root, webhook_node=node)
        ):
            continue
        findings.append(
            build_validation_finding(
                code="webhook.response_missing",
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    "A webhook should define its response behavior.",
                    (
                        f"Webhook node {node.node_id} has no response or "
                        f"respond field."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_webhook_response_body_size_limits(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate locally declared Webhook response body-size limits.

    Returns:
        The validation result for local Webhook response body-size evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if not module_looks_like_webhook_response(
            node.module_token
        ) or not _webhook_response_body_exceeds_size_limit(node):
            continue
        findings.append(
            build_validation_finding(
                code=WEBHOOK_RESPONSE_BODY_SIZE_LIMIT_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "A webhook response body should stay within the 5 MB "
                        "limit."
                    ),
                    (
                        f"Webhook response node {node.node_id} declares a "
                        f"body size "
                        "above 5 MB."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_webhook_response_content_types(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate Webhook responses with bodies declare Content-Type headers.

    Returns:
        The validation result for local Webhook response Content-Type evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if (
            not module_looks_like_webhook_response(node.module_token)
            or not _webhook_response_has_body(node)
            or _webhook_response_declares_content_type(node)
        ):
            continue
        findings.append(
            build_validation_finding(
                code=WEBHOOK_RESPONSE_CONTENT_TYPE_MISSING_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "A webhook response body should declare a Content-Type "
                        "header."
                    ),
                    (
                        f"Webhook response node {node.node_id} returns body "
                        f"content "
                        "without local Content-Type header evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_webhook_ingress_budgets(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate custom webhook payload-size and concurrency budget evidence.

    Returns:
        The validation result for custom webhook ingress budget evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if not _custom_webhook_entry_node(node) or (
            _webhook_has_payload_size_budget(node)
            and _webhook_has_concurrency_budget(node)
        ):
            continue
        findings.append(
            build_validation_finding(
                code=WEBHOOK_INGRESS_BUDGET_MISSING_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "A custom webhook should declare payload-size and "
                        "concurrency budgets."
                    ),
                    (
                        f"Webhook node {node.node_id} lacks local "
                        f"payload-size or "
                        "concurrency budget evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_webhook_method_guards(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate local accepted HTTP method evidence for custom webhooks.

    Returns:
        The validation result for custom webhook method guard evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if not _custom_webhook_entry_node(node) or _webhook_has_method_guard(
            node
        ):
            continue
        findings.append(
            build_validation_finding(
                code=WEBHOOK_METHOD_GUARD_MISSING_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "A custom webhook should declare accepted HTTP method "
                        "evidence."
                    ),
                    (
                        f"Webhook node {node.node_id} lacks local accepted "
                        f"HTTP method evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_webhook_backpressure(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate local burst/backpressure evidence for custom webhooks.

    Returns:
        The validation result for custom webhook backpressure evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if not _custom_webhook_entry_node(
            node
        ) or _webhook_has_backpressure_evidence(node):
            continue
        findings.append(
            build_validation_finding(
                code=WEBHOOK_BACKPRESSURE_MISSING_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    "A custom webhook should declare burst handling evidence.",
                    (
                        f"Webhook node {node.node_id} lacks local queue, "
                        f"dedupe, "
                        "rate-limit, or worker-limit evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_semantic_rules(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate local HTTP semantic rules owned by the top-level validator.

    Returns:
        The validation result for local HTTP semantic evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    findings.extend(_validate_http_success_status_contracts(nodes))
    findings.extend(_validate_http_error_status_evaluation(nodes))
    findings.extend(_validate_http_redirect_policies(nodes))
    findings.extend(_validate_http_authorization_redirect_leaks(nodes))
    findings.extend(_validate_http_empty_body_parse_guards(nodes))
    findings.extend(_validate_http_response_content_type_guards(nodes))
    findings.extend(_validate_http_permanent_error_retry_policies(nodes))
    findings.extend(_validate_http_not_found_classifications(nodes))
    findings.extend(_validate_http_conflict_branches(nodes))
    findings.extend(_validate_http_conflict_resumes(nodes))
    findings.extend(_validate_http_rate_limit_branches(nodes))
    findings.extend(_validate_http_server_error_backoff(nodes))
    findings.extend(_validate_http_blind_error_catchalls(nodes))
    findings.extend(_validate_http_accept_headers(nodes))
    findings.extend(_validate_http_get_body_usage(nodes))
    findings.extend(_validate_http_retryable_mutation_idempotency(nodes))
    findings.extend(_validate_http_patch_semantics(nodes))
    findings.extend(_validate_http_put_replacement_guards(nodes))
    findings.extend(_validate_http_delete_body_guards(nodes))
    findings.extend(_validate_http_head_response_body_expectations(nodes))
    findings.extend(_validate_http_options_usage_guards(nodes))
    findings.extend(_validate_http_response_schema_guards(nodes))
    findings.extend(_validate_http_request_body_size_budgets(nodes))
    findings.extend(_validate_http_response_size_budgets(nodes))
    findings.extend(_validate_http_raw_json_body_validation(nodes))
    findings.extend(_validate_http_json_body_shapes(nodes))
    findings.extend(_validate_http_upstream_status_mappings(nodes))
    findings.extend(_validate_http_user_agent_context(nodes))
    findings.extend(_validate_http_restore_label_dependencies(nodes))
    return tuple(findings)


def _validate_http_success_status_contracts(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate accepted success status evidence for HTTP requests.

    Returns:
        The validation result for local HTTP success status evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if not _http_request_node(
            node
        ) or _http_declares_success_status_contract(node):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_SUCCESS_STATUS_CONTRACT_MISSING_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "An HTTP request should declare accepted success "
                        "status "
                        ""
                        "evidence."
                    ),
                    (
                        f"HTTP node {node.node_id} lacks local accepted "
                        f"success "
                        f"status evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_error_status_evaluation(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate Make HTTP error-state evaluation is enabled when explicitly.

    configured.

    Returns:
        The validation result for local HTTP error-state evaluation settings.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if not _http_request_node(
            node
        ) or not _http_error_status_evaluation_disabled(node):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_ERROR_STATUS_EVALUATION_DISABLED_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "A Make HTTP request should evaluate non-success "
                        "states "
                        ""
                        "as errors."
                    ),
                    (
                        f"HTTP node {node.node_id} explicitly disables local "
                        "handleErrors evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_redirect_policies(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate redirect policy evidence for HTTP requests with redirects.

    enabled.

    Returns:
        The validation result for local HTTP redirect policy evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if not _http_request_node(node) or not _http_redirects_enabled(node):
            continue
        if (
            _http_declares_redirect_limit(node)
            and _http_declares_redirect_host_policy(node)
            and _http_declares_redirect_credential_policy(node)
        ):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_REDIRECT_POLICY_MISSING_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "An HTTP request following redirects should declare "
                        "redirect policy evidence."
                    ),
                    (
                        f"HTTP node {node.node_id} lacks local redirect "
                        f"limit, allowed-host, "
                        "or credential-forwarding evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_authorization_redirect_leaks(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate authorization header forwarding policy for redirects.

    Returns:
        The validation result for local redirect credential leak evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if (
            not _http_request_node(node)
            or not _http_redirects_enabled(node)
            or not _http_declares_authorization_header(node)
            or (
                _http_declares_redirect_host_policy(node)
                and _http_declares_redirect_credential_policy(node)
            )
        ):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_AUTHORIZATION_REDIRECT_LEAK_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "HTTP redirects with Authorization headers should "
                        "declare "
                        "allowed hosts and credential forwarding policy."
                    ),
                    (
                        f"HTTP node {node.node_id} follows redirects with an "
                        "Authorization header but lacks local redirect host or "
                        "credential-forwarding evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_empty_body_parse_guards(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate empty-body parse guards for HTTP requests that parse responses.

    Returns:
        The validation result for local HTTP empty-body parse guard evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if (
            not _http_request_node(node)
            or not _http_parse_response_enabled(node)
            or not _http_response_may_be_empty(node)
            or _http_declares_empty_body_parse_guard(node)
        ):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_EMPTY_BODY_PARSE_GUARD_MISSING_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "An HTTP request parsing possibly empty responses "
                        "should declare "
                        "an empty-body guard."
                    ),
                    (
                        f"HTTP node {node.node_id} accepts empty-body "
                        f"responses without "
                        "local parse guard evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_response_content_type_guards(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate response content-type guards for HTTP requests parsing JSON.

    Returns:
    The validation result for local HTTP response content-type guard evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if (
            not _http_request_node(node)
            or not _http_parses_json_response(node)
            or _http_declares_response_content_type_guard(node)
        ):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_RESPONSE_CONTENT_TYPE_GUARD_MISSING_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "An HTTP request parsing JSON responses should "
                        "declare response "
                        "Content-Type validation."
                    ),
                    (
                        f"HTTP node {node.node_id} parses JSON responses "
                        f"without local "
                        "response Content-Type guard or coercion evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_permanent_error_retry_policies(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate HTTP retry policies that include permanent error evidence.

    Returns:
        The validation result for local HTTP permanent-error retry evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if not _http_request_node(node) or not _http_retries_permanent_errors(
            node
        ):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_PERMANENT_ERROR_RETRY_POLICY_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "An HTTP retry policy should not retry permanent error "
                        "responses."
                    ),
                    (
                        f"HTTP node {node.node_id} retries 400, 401, 403, "
                        f"validation, "
                        "schema, malformed-payload, or missing-field errors."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_not_found_classifications(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate 404 semantic classification evidence for HTTP requests.

    Returns:
        The validation result for local HTTP 404 classification evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if (
            not _http_request_node(node)
            or not _http_handles_not_found_status(node)
            or _http_declares_not_found_classification(node)
        ):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_NOT_FOUND_CLASSIFICATION_MISSING_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "An HTTP request accepting 404 should classify "
                        "not-found semantics."
                    ),
                    (
                        f"HTTP node {node.node_id} handles 404 without "
                        f"expected-missing, "
                        "unexpected-missing, stale-reference, or "
                        "deleted-upstream evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_conflict_branches(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate 409 conflict branch evidence for mutating HTTP requests.

    Returns:
        The validation result for local HTTP 409 conflict handling evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if (
            not _http_request_node(node)
            or _http_method(node) not in HTTP_WRITE_METHODS
            or not _http_handles_conflict_status(node)
            or _http_declares_conflict_branch(node)
        ):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_CONFLICT_BRANCH_MISSING_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "A mutating HTTP request accepting 409 should declare "
                        "conflict handling."
                    ),
                    (
                        f"HTTP node {node.node_id} handles 409 without local "
                        f"conflict branch evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_conflict_resumes(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate 409 resume or dedupe evidence for mutating HTTP requests.

    Returns:
        The validation result for local HTTP 409 resume or dedupe evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if (
            not _http_request_node(node)
            or _http_method(node) not in HTTP_WRITE_METHODS
            or not _http_handles_conflict_status(node)
            or not _http_declares_conflict_branch(node)
            or _http_declares_conflict_resume(node)
        ):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_CONFLICT_RESUME_MISSING_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "A mutating HTTP request accepting 409 should "
                        "resume or "
                        ""
                        "deduplicate."
                    ),
                    (
                        f"HTTP node {node.node_id} handles 409 without local "
                        "retrieve-existing, dedupe, or idempotent-resume "
                        "evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_rate_limit_branches(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate 429 rate-limit handling evidence for HTTP requests.

    Returns:
        The validation result for local HTTP 429 rate-limit handling evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if (
            not _http_request_node(node)
            or not _http_handles_rate_limit_status(node)
            or _http_declares_rate_limit_branch(node)
        ):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_RATE_LIMIT_BRANCH_MISSING_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "An HTTP request accepting 429 should declare "
                        "rate-limit handling."
                    ),
                    (
                        f"HTTP node {node.node_id} handles 429 without "
                        f"local rate-limit "
                        "branch evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_server_error_backoff(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate 5xx backoff or queueing evidence for HTTP requests.

    Returns:
        The validation result for local HTTP 5xx backoff evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if (
            not _http_request_node(node)
            or not _http_handles_server_error_status(node)
            or _http_declares_server_error_backoff(node)
        ):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_SERVER_ERROR_BACKOFF_MISSING_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "An HTTP request accepting 5xx should declare bounded "
                        "recovery handling."
                    ),
                    (
                        f"HTTP node {node.node_id} handles 5xx without "
                        f"local bounded "
                        "backoff, queueing, or DLQ evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_blind_error_catchalls(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate generic error catch-all evidence for mixed HTTP status classes.

    Returns:
        The validation result for local HTTP status-class routing evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if not _http_request_node(node) or not _http_has_blind_error_catchall(
            node
        ):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_BLIND_ERROR_CATCHALL_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "A generic HTTP error catch-all should not cover auth, "
                        "rate-limit, and server-error classes without "
                        "separate semantics."
                    ),
                    (
                        f"HTTP node {node.node_id} declares a generic error "
                        f"catch-all "
                        "for mixed status classes without local "
                        "class-specific handling "
                        "evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_accept_headers(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate Accept header evidence for HTTP requests expecting JSON.

    Returns:
        The validation result for local HTTP JSON Accept header evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if (
            not _http_request_node(node)
            or not _http_expects_json_response(node)
            or _http_declares_json_accept_header(node)
            or _http_provider_forbids_accept_header(node)
        ):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_ACCEPT_HEADER_MISSING_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "An HTTP request expecting JSON should declare an "
                        "Accept header."
                    ),
                    (
                        f"HTTP node {node.node_id} expects JSON without local "
                        f"Accept header evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_get_body_usage(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate GET request body usage evidence for HTTP requests.

    Returns:
        The validation result for local HTTP GET request body evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if (
            not _http_request_node(node)
            or _http_method(node) != "GET"
            or not _http_has_request_body(node)
            or _http_declares_get_body_allowlist(node)
        ):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_GET_BODY_NOT_ALLOWED_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "An HTTP GET request should not declare a body without "
                        "an allowlist."
                    ),
                    (
                        f"HTTP node {node.node_id} declares a GET request "
                        f"body without "
                        "local known-nonstandard-API allowlist evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_retryable_mutation_idempotency(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate idempotency evidence for retryable HTTP mutations.

    Returns:
        The validation result for local retryable HTTP mutation evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if (
            not _http_request_node(node)
            or _http_method(node) not in HTTP_MUTATING_METHODS
            or not _http_has_retry_policy_evidence(node)
            or _http_declares_idempotency_evidence(node)
        ):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_RETRYABLE_MUTATION_IDEMPOTENCY_MISSING_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "A retryable HTTP mutation should declare idempotency "
                        "evidence."
                    ),
                    (
                        f"HTTP node {node.node_id} declares retry behavior "
                        f"for a "
                        "mutating method without local idempotency-key or "
                        "deterministic "
                        "transaction-id evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_patch_semantics(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate PATCH request semantics evidence for HTTP requests.

    Returns:
        The validation result for local HTTP PATCH semantics evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if (
            not _http_request_node(node)
            or _http_method(node) != "PATCH"
            or _http_declares_patch_semantics(node)
        ):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_PATCH_SEMANTICS_MISSING_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    "A PATCH request should declare its patch semantics.",
                    (
                        f"HTTP node {node.node_id} uses PATCH without local "
                        f"JSON Patch, "
                        "JSON Merge Patch, or provider-specific "
                        "partial-update evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_put_replacement_guards(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate PUT replacement semantics evidence for HTTP requests.

    Returns:
        The validation result for local HTTP PUT replacement evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if (
            not _http_request_node(node)
            or _http_method(node) != "PUT"
            or _http_declares_put_replacement_guard(node)
        ):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_PUT_REPLACEMENT_GUARD_MISSING_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "A PUT request should acknowledge full replacement "
                        "semantics."
                    ),
                    (
                        f"HTTP node {node.node_id} uses PUT without local "
                        f"full-replacement "
                        "or partial-update conversion evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_delete_body_guards(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate DELETE request body support evidence for HTTP requests.

    Returns:
        The validation result for local HTTP DELETE body evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if (
            not _http_request_node(node)
            or _http_method(node) != "DELETE"
            or not _http_has_request_body(node)
            or _http_declares_delete_body_guard(node)
        ):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_DELETE_BODY_GUARD_MISSING_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "A DELETE request body should declare provider support "
                        "evidence."
                    ),
                    (
                        f"HTTP node {node.node_id} declares a DELETE "
                        f"request body without "
                        "local provider-support or delete-body semantics "
                        "evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_head_response_body_expectations(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate HEAD response-body expectation evidence for HTTP requests.

    Returns:
        The validation result for local HTTP HEAD response body evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if (
            not _http_request_node(node)
            or _http_method(node) != "HEAD"
            or not _http_expects_response_body(node)
        ):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_HEAD_RESPONSE_BODY_EXPECTED_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "A HEAD request should not expect or parse a response "
                        "body."
                    ),
                    (
                        f"HTTP node {node.node_id} uses HEAD with local "
                        f"response-body "
                        "parsing or schema expectation evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_options_usage_guards(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate OPTIONS request usage evidence for HTTP requests.

    Returns:
        The validation result for local HTTP OPTIONS usage evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if (
            not _http_request_node(node)
            or _http_method(node) != "OPTIONS"
            or _http_declares_options_allowed_use(node)
        ):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_OPTIONS_USAGE_GUARD_MISSING_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "An OPTIONS request should declare capability or CORS "
                        "usage."
                    ),
                    (
                        f"HTTP node {node.node_id} uses OPTIONS without "
                        f"local CORS, "
                        "preflight, or capability-discovery evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_response_schema_guards(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate response schema or fallback evidence for parsed HTTP responses.

    Returns:
        The validation result for local HTTP response schema evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if (
            not _http_request_node(node)
            or not _http_response_needs_schema_guard(node)
            or _http_declares_response_schema_guard(node)
        ):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_RESPONSE_SCHEMA_GUARD_MISSING_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "A parsed HTTP response should declare schema or "
                        "fallback evidence."
                    ),
                    (
                        f"HTTP node {node.node_id} parses or expects "
                        f"structured response "
                        "data without local response-schema or fallback "
                        "evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_request_body_size_budgets(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate request body size-budget evidence for mapped HTTP bodies.

    Returns:
        The validation result for local HTTP request body size-budget evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if (
            not _http_request_node(node)
            or _http_method(node) not in HTTP_MUTATING_METHODS
            or not _http_body_maps_size_sensitive_source(node)
            or _http_declares_body_size_budget(node)
        ):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_REQUEST_BODY_SIZE_BUDGET_MISSING_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "A mapped HTTP request body should declare size-budget "
                        "evidence."
                    ),
                    (
                        f"HTTP node {node.node_id} maps payload, file, or "
                        f"array-like "
                        "body data without local request-body size-budget "
                        "evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_response_size_budgets(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate response size-budget evidence for parsed HTTP responses.

    Returns:
        The validation result for local HTTP response size-budget evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if (
            not _http_request_node(node)
            or not _http_response_needs_schema_guard(node)
            or _http_declares_response_size_budget(node)
        ):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_RESPONSE_SIZE_BUDGET_MISSING_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "A parsed HTTP response should declare size-budget "
                        "evidence."
                    ),
                    (
                        f"HTTP node {node.node_id} parses or expects "
                        f"structured response "
                        "data without local response-size budget evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_raw_json_body_validation(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate raw JSON body validation evidence for HTTP requests.

    Returns:
        The validation result for local raw JSON body validation evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if not _http_request_node(
            node
        ) or not _http_uses_unvalidated_raw_json_body(node):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_RAW_JSON_BODY_VALIDATION_MISSING_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "A raw string body sent as JSON should declare JSON "
                        "validation."
                    ),
                    (
                        f"HTTP node {node.node_id} declares "
                        f"application/json for a raw "
                        "string body without local JSON body validation "
                        "evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_json_body_shapes(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate JSON request body syntax and top-level shape.

    Returns:
        The validation result for local JSON body shape evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if not _http_request_node(
            node
        ) or not _http_uses_invalid_json_body_shape(node):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_JSON_BODY_SYNTAX_INVALID_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "A JSON request body should be valid JSON object, "
                        "array, or string syntax."
                    ),
                    (
                        f"HTTP node {node.node_id} declares "
                        f"application/json with a "
                        "body that is not locally parseable as an object, "
                        "array, or string."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_upstream_status_mappings(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate webhook response status mapping for HTTP-backed API scenarios.

    Returns:
        The validation result for local upstream-status mapping evidence.
    """
    if (
        not any(_webhook_entry_node(node) for node in nodes)
        or not any(
            _http_declares_non_success_status_contract(node) for node in nodes
        )
        or _scenario_declares_upstream_status_mapping(nodes)
    ):
        return ()
    return tuple(
        build_validation_finding(
            code=HTTP_UPSTREAM_STATUS_MAPPING_MISSING_CODE,
            severity="warning",
            node=(node.node_id, node.source_trace.path),
            catalog_module_id=None,
            messages=(
                "A webhook response should map upstream HTTP status semantics.",
                (
                    f"Webhook response node {node.node_id} returns a static "
                    f"500 for an "
                    "HTTP-backed scenario without local upstream-status "
                    "mapping evidence."
                ),
            ),
        )
        for node in nodes
        if _webhook_response_collapses_to_static_500(node)
    )


def _validate_http_user_agent_context(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate User-Agent or scenario-context header evidence for external.

    HTTP.

    requests.

    Returns:
        The validation result for local external HTTP request context evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if (
            not _http_request_node(node)
            or not _http_targets_static_external_endpoint(node)
            or _http_declares_user_agent_context(node)
            or _http_provider_forbids_user_agent(node)
        ):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_USER_AGENT_CONTEXT_MISSING_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "An external HTTP request should declare User-Agent or "
                        "context headers."
                    ),
                    (
                        f"HTTP node {node.node_id} targets a static "
                        f"external endpoint "
                        "without local User-Agent or scenario-context evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_http_restore_label_dependencies(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate runtime HTTP config does not rely on restore or label text.

    Returns:
        The validation result for HTTP restore-label dependency evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if not _http_request_node(node) or not _http_depends_on_restore_label(
            node
        ):
            continue
        findings.append(
            build_validation_finding(
                code=HTTP_RESTORE_LABEL_DEPENDENCY_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "An HTTP request should keep runtime URL, method, "
                        "and auth "
                        "configuration out of restore labels."
                    ),
                    (
                        f"HTTP node {node.node_id} has restore or label "
                        f"metadata that "
                        "looks like runtime HTTP configuration missing from "
                        "parameters "
                        "or mapper fields."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_mailhook_sender_allowlists(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate mailhook sender allowlist evidence.

    Returns:
        The validation result for mailhook sender allowlist evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if not _mailhook_entry_node(node) or _mailhook_has_sender_allowlist(
            node
        ):
            continue
        findings.append(
            build_validation_finding(
                code=MAILHOOK_SENDER_ALLOWLIST_MISSING_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "A mailhook should declare trusted sender or domain "
                        "evidence."
                    ),
                    (
                        f"Mailhook node {node.node_id} lacks local "
                        f"sender-address "
                        "or sender-domain allowlist evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_webhook_signature_timestamps(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate timestamp and drift-window evidence for signed webhooks.

    Returns:
        The validation result for signed webhook timestamp evidence.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if (
            not _webhook_entry_node(node)
            or not _webhook_has_signature_check(node)
            or (
                _webhook_has_timestamp_evidence(node)
                and _webhook_has_drift_window_evidence(node)
            )
        ):
            continue
        findings.append(
            build_validation_finding(
                code=WEBHOOK_SIGNATURE_TIMESTAMP_MISSING_CODE,
                severity="warning",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "A signed webhook should declare timestamp and "
                        "drift-window checks."
                    ),
                    (
                        f"Webhook node {node.node_id} has signature "
                        f"evidence without "
                        "local timestamp and bounded drift-window evidence."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_knowledge_promoted_rules(
    *,
    root: MakeAstRoot,
    nodes: tuple[MakeAstNode, ...],
    knowledge: KnowledgeStoreQuery | None,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate rules promoted through the Make knowledge store.

    Returns:
        Validation findings derived from promoted knowledge rules.
    """
    if knowledge is None:
        return ()
    findings: list[BlueprintValidationFinding] = []
    findings.extend(
        _validate_webhook_sequential_response_conflicts(root, nodes, knowledge)
    )
    findings.extend(_validate_webhook_security_rules(nodes, knowledge))
    findings.extend(_validate_webhook_payload_contract_rules(nodes, knowledge))
    findings.extend(_validate_http_request_rules(nodes, knowledge))
    findings.extend(_validate_iterator_rules(nodes, knowledge))
    findings.extend(_validate_aggregator_rules(nodes, knowledge))
    findings.extend(_validate_text_processing_rules(nodes, knowledge))
    findings.extend(_validate_parse_json_rules(nodes, knowledge))
    findings.extend(_validate_data_store_rules(nodes, knowledge))
    findings.extend(_validate_basic_trigger_rules(nodes, knowledge))
    findings.extend(_validate_mcp_tool_rules(nodes, knowledge))
    findings.extend(_validate_custom_app_rules(nodes, knowledge))
    findings.extend(_validate_transaction_safety_rules(nodes, knowledge))
    findings.extend(_validate_scenario_governance_rules(root, nodes, knowledge))
    findings.extend(
        _validate_reviewed_designer_message_warnings(nodes, knowledge)
    )
    return tuple(findings)


def _validate_scenario_governance_rules(
    root: MakeAstRoot,
    nodes: tuple[MakeAstNode, ...],
    knowledge: KnowledgeStoreQuery,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate promoted scenario-level governance metadata rules.

    Returns:
    The validation result for explicit governance or production-profile
    evidence.
    """
    if not _scenario_declares_governance_profile(root):
        return ()

    findings: list[BlueprintValidationFinding] = []
    rule = knowledge.rule_by_code("scenario.owner_missing")
    if rule is not None and not _scenario_has_owner(root):
        findings.append(
            _promoted_scenario_rule_finding(
                root=root,
                rule=rule,
                client_message=(
                    "A governed production scenario should declare owner or "
                    "escalation evidence."
                ),
                internal_message=(
                    "Scenario metadata declares governance or production "
                    "profile without "
                    "owner, team, on-call, or escalation evidence."
                ),
            )
        )

    rule = knowledge.rule_by_code("scenario.change_reason_missing")
    if rule is not None and not _scenario_has_change_reason(root):
        findings.append(
            _promoted_scenario_rule_finding(
                root=root,
                rule=rule,
                client_message=(
                    "A governed production scenario should declare "
                    "change-reason evidence."
                ),
                internal_message=(
                    "Scenario metadata declares governance or production "
                    "profile without "
                    "change-reason, change-ticket, release-note, or "
                    "migration-note evidence."
                ),
            )
        )

    rule = knowledge.rule_by_code("scenario.rollback_plan_missing")
    if rule is not None and not _scenario_has_rollback_plan(root):
        findings.append(
            _promoted_scenario_rule_finding(
                root=root,
                rule=rule,
                client_message=(
                    "A governed production scenario should declare "
                    "rollback-plan evidence."
                ),
                internal_message=(
                    "Scenario metadata declares governance or production "
                    "profile without "
                    "rollback-plan, restore-plan, or "
                    "previous-blueprint-hash evidence."
                ),
            )
        )

    rule = knowledge.rule_by_code("scenario.incident_note_missing")
    if (
        rule is not None
        and _scenario_declares_incident_profile(root)
        and not _scenario_has_incident_notes(root)
    ):
        findings.append(
            _promoted_scenario_rule_finding(
                root=root,
                rule=rule,
                client_message=(
                    "A governed critical scenario should declare incident "
                    "or runbook evidence."
                ),
                internal_message=(
                    "Scenario metadata declares critical incident posture "
                    "without incident, "
                    "runbook, pager, severity, or on-call evidence."
                ),
            )
        )

    rule = knowledge.rule_by_code("scenario.production_debug_marker")
    if rule is not None:
        findings.extend(
            _promoted_rule_finding(
                node=node,
                rule=rule,
                client_message=(
                    "A governed production scenario should not retain debug "
                    "or test markers."
                ),
            )
            for node in nodes
            if _node_has_production_debug_marker(node)
        )

    return tuple(findings)


def _validate_reviewed_designer_message_warnings(
    nodes: tuple[MakeAstNode, ...],
    knowledge: KnowledgeStoreQuery,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate reviewed Make designer-message warnings from the knowledge.

    store.

    Returns:
        The validation result for reviewed designer-message evidence.
    """
    findings: list[BlueprintValidationFinding] = [
        _reviewed_root_designer_message_finding(message=message)
        for message in knowledge.reviewed_root_designer_messages()
    ]
    for node in nodes:
        findings.extend(
            _reviewed_designer_message_finding(node=node, message=message)
            for message in knowledge.reviewed_designer_messages_for_node(
                node_id=node.node_id,
                module_slug=node.module_token,
            )
        )
    return tuple(findings)


def _reviewed_root_designer_message_finding(
    *,
    message: KnowledgeDesignerMessageEvidence,
) -> BlueprintValidationFinding:
    """Return one scenario-level warning derived from Make designer evidence."""
    return build_validation_finding(
        code="make_designer.warning",
        severity="warning",
        node=(None, ("metadata", "designer", "messages")),
        catalog_module_id=None,
        messages=(
            (
                f"{MAKE_DESIGNER_WARNING_CLIENT_PREFIX}: "
                "Make Designer reports a reviewed scenario warning."
            ),
            (
                "Scenario has reviewed Make designer warning "
                f"{message.finding_id}: {message.message}"
            ),
        ),
    )


def _reviewed_designer_message_finding(
    *,
    node: MakeAstNode,
    message: KnowledgeDesignerMessageEvidence,
) -> BlueprintValidationFinding:
    """Return the computed result for the caller."""
    return build_validation_finding(
        code="make_designer.warning",
        severity="warning",
        node=(node.node_id, node.source_trace.path),
        catalog_module_id=None,
        messages=(
            (
                f"{MAKE_DESIGNER_WARNING_CLIENT_PREFIX}: "
                "Make Designer reports a reviewed warning for this module."
            ),
            (
                f"Node {node.node_id} has reviewed Make designer warning "
                f"{message.finding_id}: {message.message}"
            ),
        ),
    )


def _validate_webhook_sequential_response_conflicts(
    root: MakeAstRoot,
    nodes: tuple[MakeAstNode, ...],
    knowledge: KnowledgeStoreQuery,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate promoted webhook sequential-processing response conflicts.

    Returns:
    The validation result for promoted webhook sequential-response conflicts.
    """
    sequential_rule = knowledge.rule_by_code(
        "webhook.sequential_response_conflict"
    )
    if sequential_rule is None:
        return ()

    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if (
            node.kind != "webhook"
            or not webhook_has_response_on_any_path(
                root=root, webhook_node=node
            )
            or not _webhook_uses_sequential_processing(node)
        ):
            continue
        findings.append(
            build_validation_finding(
                code=sequential_rule.rule_code,
                severity=_knowledge_severity(sequential_rule.severity),
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "Sequential webhook processing conflicts with a "
                        "webhook "
                        ""
                        "response."
                    ),
                    (
                        f"Node {node.node_id} violates "
                        f"{sequential_rule.rule_id} "
                        f"from {sequential_rule.adr_anchor}."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_webhook_security_rules(
    nodes: tuple[MakeAstNode, ...],
    knowledge: KnowledgeStoreQuery,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate promoted Advanced Webhooks security rules.

    Returns:
        The validation result for promoted Advanced Webhooks security rules.
    """
    ip_allowlist_rule = knowledge.rule_by_code(
        "webhook.security_ip_allowlist_missing"
    )
    signature_rule = knowledge.rule_by_code(
        "webhook.security_signature_missing"
    )
    sensitive_cleartext_rule = knowledge.rule_by_code(
        "webhook.security_sensitive_cleartext"
    )
    if (
        ip_allowlist_rule is None
        and signature_rule is None
        and sensitive_cleartext_rule is None
    ):
        return ()

    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if not _webhook_entry_node(node):
            continue
        protected_payload = _webhook_requires_protection(node)
        if (
            ip_allowlist_rule is not None
            and protected_payload
            and not _webhook_has_ip_allowlist(node)
        ):
            findings.append(
                _promoted_rule_finding(
                    node=node,
                    rule=ip_allowlist_rule,
                    client_message=(
                        "A protected webhook should declare allowed caller IPs."
                    ),
                )
            )
        if (
            signature_rule is not None
            and protected_payload
            and not _webhook_has_signature_check(node)
        ):
            findings.append(
                _promoted_rule_finding(
                    node=node,
                    rule=signature_rule,
                    client_message=(
                        "A protected webhook should verify caller signature "
                        "or hash evidence."
                    ),
                )
            )
        if (
            sensitive_cleartext_rule is not None
            and _webhook_carries_sensitive_payload(node)
            and not _webhook_declares_encryption(node)
        ):
            findings.append(
                _promoted_rule_finding(
                    node=node,
                    rule=sensitive_cleartext_rule,
                    client_message=(
                        "Sensitive webhook payloads should declare "
                        "encryption handling."
                    ),
                )
            )
    return tuple(findings)


def _validate_webhook_payload_contract_rules(
    nodes: tuple[MakeAstNode, ...],
    knowledge: KnowledgeStoreQuery,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate promoted webhook payload contract rules.

    Returns:
        The validation result for promoted webhook payload contract rules.
    """
    payload_contract_rule = knowledge.rule_by_code(
        "webhook.payload_contract_missing"
    )
    if payload_contract_rule is None:
        return ()
    return tuple(
        _promoted_rule_finding(
            node=node,
            rule=payload_contract_rule,
            client_message=(
                "A webhook that receives mapped payload data should declare "
                "a payload schema."
            ),
        )
        for node in nodes
        if _webhook_entry_node(node)
        and _webhook_receives_payload(node)
        and not _webhook_has_payload_contract(node)
    )


def _validate_http_request_rules(
    nodes: tuple[MakeAstNode, ...],
    knowledge: KnowledgeStoreQuery,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate promoted HTTP request behavior rules.

    Returns:
        The validation result for promoted HTTP request behavior rules.
    """
    parse_response_rule = knowledge.rule_by_code("http.parse_response_missing")
    method_url_rule = knowledge.rule_by_code("http.method_url_missing")
    upload_body_rule = knowledge.rule_by_code(
        "http.file_upload_body_type_invalid"
    )
    json_content_type_rule = knowledge.rule_by_code(
        "http.json_content_type_missing"
    )
    if (
        parse_response_rule is None
        and method_url_rule is None
        and upload_body_rule is None
        and json_content_type_rule is None
    ):
        return ()

    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if not _http_request_node(node):
            continue
        if method_url_rule is not None and not _http_declares_method_and_url(
            node
        ):
            findings.append(
                _promoted_rule_finding(
                    node=node,
                    rule=method_url_rule,
                    client_message=(
                        "An HTTP request should declare both method and URL "
                        "before API use."
                    ),
                )
            )
        if (
            parse_response_rule is not None
            and _http_expects_structured_response(node)
            and not _http_parse_response_enabled(node)
        ):
            findings.append(
                _promoted_rule_finding(
                    node=node,
                    rule=parse_response_rule,
                    client_message=(
                        "An HTTP API request expecting structured data "
                        "should parse the response."
                    ),
                )
            )
        if (
            upload_body_rule is not None
            and _http_uploads_file(node)
            and not _http_uses_multipart_body(node)
        ):
            findings.append(
                _promoted_rule_finding(
                    node=node,
                    rule=upload_body_rule,
                    client_message=(
                        "An HTTP file upload should use multipart form-data "
                        "body handling."
                    ),
                )
            )
        if (
            json_content_type_rule is not None
            and _http_sends_json_body(node)
            and not _http_declares_json_content_type(node)
        ):
            findings.append(
                _promoted_rule_finding(
                    node=node,
                    rule=json_content_type_rule,
                    client_message=(
                        "An HTTP request with a JSON body should declare "
                        "JSON content type."
                    ),
                )
            )
    return tuple(findings)


def _validate_iterator_rules(
    nodes: tuple[MakeAstNode, ...],
    knowledge: KnowledgeStoreQuery,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate promoted iterator input-shape rules.

    Returns:
        The validation result for promoted iterator input-shape rules.
    """
    array_input_rule = knowledge.rule_by_code("iterator.array_input_missing")
    item_limit_rule = knowledge.rule_by_code("iterator.item_limit_missing")
    if array_input_rule is None and item_limit_rule is None:
        return ()

    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if not _iterator_node(node):
            continue
        has_array_input = _iterator_has_array_input(node)
        if array_input_rule is not None and not has_array_input:
            findings.append(
                _promoted_rule_finding(
                    node=node,
                    rule=array_input_rule,
                    client_message=(
                        "An iterator should declare the source array to split."
                    ),
                )
            )
        if (
            item_limit_rule is not None
            and has_array_input
            and not _iterator_has_item_limit(node)
        ):
            findings.append(
                _promoted_rule_finding(
                    node=node,
                    rule=item_limit_rule,
                    client_message=(
                        "An iterator should declare item-count limit or "
                        "chunking evidence."
                    ),
                )
            )
    return tuple(findings)


def _validate_aggregator_rules(
    nodes: tuple[MakeAstNode, ...],
    knowledge: KnowledgeStoreQuery,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate promoted aggregator source and strategy rules.

    Returns:
        The validation result for promoted aggregator source and strategy rules.
    """
    source_rule = knowledge.rule_by_code("aggregator.source_missing")
    strategy_rule = knowledge.rule_by_code("aggregator.strategy_missing")
    bundle_limit_rule = knowledge.rule_by_code(
        "aggregator.bundle_limit_missing"
    )
    if (
        source_rule is None
        and strategy_rule is None
        and bundle_limit_rule is None
    ):
        return ()

    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if not _aggregator_node(node):
            continue
        has_source = _aggregator_has_source(node)
        if source_rule is not None and not has_source:
            findings.append(
                _promoted_rule_finding(
                    node=node,
                    rule=source_rule,
                    client_message=(
                        "An aggregator should declare the module or array it "
                        "consumes."
                    ),
                )
            )
        if strategy_rule is not None and not _aggregator_has_strategy(node):
            findings.append(
                _promoted_rule_finding(
                    node=node,
                    rule=strategy_rule,
                    client_message=(
                        "An aggregator should declare aggregation strategy "
                        "or output format."
                    ),
                )
            )
        if (
            bundle_limit_rule is not None
            and has_source
            and not _aggregator_has_bundle_limit(node)
        ):
            findings.append(
                _promoted_rule_finding(
                    node=node,
                    rule=bundle_limit_rule,
                    client_message=(
                        "An aggregator should declare bundle-count limit or "
                        "chunking evidence."
                    ),
                )
            )
    return tuple(findings)


def _validate_text_processing_rules(
    nodes: tuple[MakeAstNode, ...],
    knowledge: KnowledgeStoreQuery,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate promoted text parser and regex configuration rules.

    Returns:
    The validation result for promoted text parser and regex configuration
    rules.
    """
    pattern_rule = knowledge.rule_by_code("text_parser.pattern_missing")
    input_rule = knowledge.rule_by_code("text_parser.input_missing")
    if pattern_rule is None and input_rule is None:
        return ()

    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if not _text_parser_node(node):
            continue
        if pattern_rule is not None and not _text_parser_has_pattern(node):
            findings.append(
                _promoted_rule_finding(
                    node=node,
                    rule=pattern_rule,
                    client_message=(
                        "A regex text parser should declare the pattern it "
                        "applies."
                    ),
                )
            )
        if input_rule is not None and not _text_parser_has_input(node):
            findings.append(
                _promoted_rule_finding(
                    node=node,
                    rule=input_rule,
                    client_message=(
                        "A regex text parser should declare the input text."
                    ),
                )
            )
    return tuple(findings)


def _validate_parse_json_rules(
    nodes: tuple[MakeAstNode, ...],
    knowledge: KnowledgeStoreQuery,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate promoted Parse JSON schema evidence rules.

    Returns:
        The validation result for promoted Parse JSON schema rules.
    """
    schema_rule = knowledge.rule_by_code("parse_json.schema_missing")
    if schema_rule is None:
        return ()
    return tuple(
        _promoted_rule_finding(
            node=node,
            rule=schema_rule,
            client_message=(
                "A Parse JSON module should declare schema or data-structure "
                "evidence."
            ),
        )
        for node in nodes
        if _parse_json_node(node) and not _parse_json_has_schema(node)
    )


def _validate_data_store_rules(
    nodes: tuple[MakeAstNode, ...],
    knowledge: KnowledgeStoreQuery,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate promoted data-store durability rules.

    Returns:
        The validation result for promoted data-store durability rules.
    """
    delete_recovery_rule = knowledge.rule_by_code(
        "data_store.delete_recovery_missing"
    )
    write_key_rule = knowledge.rule_by_code("data_store.write_key_missing")
    ttl_rule = knowledge.rule_by_code("data_store.ttl_missing")
    secret_storage_rule = knowledge.rule_by_code("data_store.secret_storage")
    if (
        delete_recovery_rule is None
        and write_key_rule is None
        and ttl_rule is None
        and secret_storage_rule is None
    ):
        return ()

    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if (
            delete_recovery_rule is not None
            and _data_store_delete_node(node)
            and not _data_store_has_recovery_posture(node)
        ):
            findings.append(
                _promoted_rule_finding(
                    node=node,
                    rule=delete_recovery_rule,
                    client_message=(
                        "A data store delete operation should declare "
                        "backup or recovery posture."
                    ),
                )
            )
        if (
            ttl_rule is not None
            and _data_store_write_node(node)
            and _data_store_ephemeral_state_node(node)
            and not _data_store_has_ttl(node)
        ):
            findings.append(
                _promoted_rule_finding(
                    node=node,
                    rule=ttl_rule,
                    client_message=(
                        "Temporary data store state should declare TTL or "
                        "cleanup evidence."
                    ),
                )
            )
        if (
            secret_storage_rule is not None
            and _data_store_write_node(node)
            and _data_store_has_secret_storage(node)
        ):
            findings.append(
                _promoted_rule_finding(
                    node=node,
                    rule=secret_storage_rule,
                    client_message=(
                        "A data store write appears to persist secret-like "
                        "values."
                    ),
                )
            )
        if (
            write_key_rule is not None
            and _data_store_write_node(node)
            and not _data_store_has_key(node)
        ):
            findings.append(
                _promoted_rule_finding(
                    node=node,
                    rule=write_key_rule,
                    client_message=(
                        "A data store write should declare a stable record key."
                    ),
                )
            )
    return tuple(findings)


def _validate_basic_trigger_rules(
    nodes: tuple[MakeAstNode, ...],
    knowledge: KnowledgeStoreQuery,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate promoted basic-trigger output interface rules.

    Returns:
        The validation result for promoted basic-trigger output interface rules.
    """
    interface_rule = knowledge.rule_by_code("basic_trigger.interface_missing")
    if interface_rule is None:
        return ()
    return tuple(
        _promoted_rule_finding(
            node=node,
            rule=interface_rule,
            client_message=(
                "A basic trigger should declare the output bundle fields it "
                "emits."
            ),
        )
        for node in nodes
        if _basic_trigger_node(node) and not _basic_trigger_has_interface(node)
    )


def _validate_mcp_tool_rules(
    nodes: tuple[MakeAstNode, ...],
    knowledge: KnowledgeStoreQuery,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate promoted MCP tool contract rules.

    Returns:
        The validation result for promoted MCP tool contract rules.
    """
    contract_rule = knowledge.rule_by_code("mcp_tool.contract_missing")
    if contract_rule is None:
        return ()
    return tuple(
        _promoted_rule_finding(
            node=node,
            rule=contract_rule,
            client_message=(
                "An MCP tool should declare input and output contracts."
            ),
        )
        for node in nodes
        if _mcp_tool_node(node) and not _tool_contract_declared(node)
    )


def _validate_custom_app_rules(
    nodes: tuple[MakeAstNode, ...],
    knowledge: KnowledgeStoreQuery,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate promoted custom-app schema contract rules.

    Returns:
        The validation result for promoted custom-app schema contract rules.
    """
    schema_rule = knowledge.rule_by_code("custom_app.schema_contract_missing")
    if schema_rule is None:
        return ()
    return tuple(
        _promoted_rule_finding(
            node=node,
            rule=schema_rule,
            client_message=(
                "A custom app module should declare schema contract evidence."
            ),
        )
        for node in nodes
        if _custom_app_node(node) and not _custom_app_has_schema_contract(node)
    )


def _validate_transaction_safety_rules(
    nodes: tuple[MakeAstNode, ...],
    knowledge: KnowledgeStoreQuery,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate promoted rollback and transaction-safety profile rules.

    Returns:
        The validation result for promoted transaction-safety profile rules.
    """
    rule = knowledge.rule_by_code("transaction.rollback_posture_missing")
    if rule is None:
        return ()

    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if _node_declares_transaction_safety_posture(node):
            continue
        profile = _transaction_risk_profile_for_node(
            node=node, knowledge=knowledge
        )
        if profile is None:
            continue
        findings.append(
            _promoted_rule_finding(
                node=node,
                rule=rule,
                client_message=(
                    "A rollback-unsafe mutation should declare recovery, "
                    "idempotency, "
                    "audit, or compensation posture."
                ),
            )
        )
    return tuple(findings)


def _transaction_risk_profile_for_node(
    *,
    node: MakeAstNode,
    knowledge: KnowledgeStoreQuery,
) -> KnowledgeTransactionProfile | None:
    """Return the first rollback-risk profile that applies to one node."""
    token_key = module_token_semantic_key(node.module_token)
    profiles = knowledge.transaction_profiles_matching(
        module_token_key=token_key
    )
    for profile in profiles:
        if (
            profile.mutates_state
            and profile.rollback_capability not in ROLLBACK_SAFE_CAPABILITIES
            and _transaction_profile_operation_applies(
                node=node, profile=profile
            )
        ):
            return profile
    return None


def _transaction_profile_operation_applies(
    *,
    node: MakeAstNode,
    profile: KnowledgeTransactionProfile,
) -> bool:
    """Return whether one profile operation kind applies to a node payload."""
    token_key = module_token_semantic_key(node.module_token)
    if profile.operation_kind == "external_write":
        method = _mapping_text(node.raw_payload, "method").upper()
        return _http_request_node(node) and method in HTTP_WRITE_METHODS
    if profile.operation_kind == "delete":
        return "delete" in token_key
    if profile.operation_kind == "internal_write":
        return any(
            marker in token_key
            for marker in ("add", "create", "set", "update", "upsert")
        )
    return True


def _node_declares_transaction_safety_posture(node: MakeAstNode) -> bool:
    """Return whether a node declares transaction-safety posture evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=TRANSACTION_SAFETY_POSTURE_TOKENS,
        node_local=True,
    )


def _promoted_rule_finding(
    *,
    node: MakeAstNode,
    rule: KnowledgeRuleFact,
    client_message: str,
) -> BlueprintValidationFinding:
    """Return one finding derived from a promoted knowledge rule."""
    return build_validation_finding(
        code=rule.rule_code,
        severity=_knowledge_severity(rule.severity),
        node=(node.node_id, node.source_trace.path),
        catalog_module_id=None,
        messages=(
            client_message,
            (
                f"Node {node.node_id} violates {rule.rule_id} from "
                f"{rule.adr_anchor}."
            ),
        ),
    )


def _promoted_scenario_rule_finding(
    *,
    root: MakeAstRoot,
    rule: KnowledgeRuleFact,
    client_message: str,
    internal_message: str,
) -> BlueprintValidationFinding:
    """Return the computed result for the caller."""
    return build_validation_finding(
        code=rule.rule_code,
        severity=_knowledge_severity(rule.severity),
        node=(None, ("metadata",)),
        catalog_module_id=None,
        messages=(
            client_message,
            (
                f"Scenario {root.scenario.name!r} violates {rule.rule_id} "
                f"from {rule.adr_anchor}: {internal_message}"
            ),
        ),
    )


def _validate_semantic_module_usage(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate deterministic module-specific semantic misuse.

    Returns:
        The validation result for deterministic module-specific semantic misuse.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if "downloadfile" not in module_token_semantic_key(node.module_token):
            continue
        if _mapping_text(node.raw_payload, "method").upper() != "POST":
            continue
        findings.append(
            build_validation_finding(
                code="semantic.download_file_post",
                severity="error",
                node=(node.node_id, node.source_trace.path),
                catalog_module_id=None,
                messages=(
                    (
                        "A download-file module cannot be used as an HTTP POST "
                        "action."
                    ),
                    (
                        f"Node {node.node_id} uses {node.module_token!r} with "
                        f"method POST."
                    ),
                ),
            )
        )
    return tuple(findings)


def _validate_operation_volume_review(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Flag modules that can multiply operations or bundle volume.

    Returns:
        The documented result.
    """
    return tuple(
        _operation_volume_review_finding(node)
        for node in nodes
        if _operation_volume_review_needed(node)
    )


def _operation_volume_review_needed(node: MakeAstNode) -> bool:
    """Return whether a node should trigger operation-volume review."""
    if node.kind in OPERATION_VOLUME_KINDS:
        return True
    token_key = module_token_semantic_key(node.module_token)
    return any(
        fragment in token_key for fragment in OPERATION_VOLUME_TOKEN_FRAGMENTS
    )


def _webhook_uses_sequential_processing(node: MakeAstNode) -> bool:
    """Return whether a webhook node declares sequential processing."""
    text_blob = _json_text_blob(node.raw_payload, node_local=True)
    return any(
        marker in text_blob
        for marker in (
            "sequential ",
            "process sequentially ",
            "queue sequential ",
            "strict order",
        )
    )


def _webhook_entry_node(node: MakeAstNode) -> bool:
    """Return if one node is a webhook entry point, not a response action."""
    return node.kind == "webhook" and not module_looks_like_webhook_response(
        node.module_token
    )


def _custom_webhook_entry_node(node: MakeAstNode) -> bool:
    """Return whether one node is a custom webhook entry point."""
    return _webhook_entry_node(
        node
    ) and "customwebhook" in module_token_semantic_key(node.module_token)


def _mailhook_entry_node(node: MakeAstNode) -> bool:
    """Return whether one node is a mailhook entry point."""
    return "mailhook" in module_token_semantic_key(node.module_token)


def _webhook_requires_protection(node: MakeAstNode) -> bool:
    """Return whether a webhook payload carries protected-call evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=WEBHOOK_PROTECTED_TOKENS,
        node_local=True,
    )


def _webhook_carries_sensitive_payload(node: MakeAstNode) -> bool:
    """Return whether a webhook payload exposes sensitive-data evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=WEBHOOK_SENSITIVE_TOKENS,
        node_local=True,
    )


def _webhook_has_ip_allowlist(node: MakeAstNode) -> bool:
    """Return whether a webhook declares caller IP allowlist evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=WEBHOOK_IP_ALLOWLIST_KEYS,
        node_local=True,
    )


def _webhook_has_signature_check(node: MakeAstNode) -> bool:
    """Return if a webhook declares signature or hash verification evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=WEBHOOK_SIGNATURE_TOKENS,
        node_local=True,
    )


def _webhook_has_timestamp_evidence(node: MakeAstNode) -> bool:
    """Return whether a webhook declares signed timestamp evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=WEBHOOK_TIMESTAMP_TOKENS,
        node_local=True,
    )


def _webhook_has_drift_window_evidence(node: MakeAstNode) -> bool:
    """Return whether a webhook declares bounded timestamp drift evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=WEBHOOK_DRIFT_WINDOW_TOKENS,
        node_local=True,
    )


def _webhook_declares_encryption(node: MakeAstNode) -> bool:
    """Return whether a webhook declares payload encryption evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=WEBHOOK_ENCRYPTION_TOKENS,
        node_local=True,
    )


def _webhook_receives_payload(node: MakeAstNode) -> bool:
    """Return if a webhook appears to receive mapped request payload data."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=WEBHOOK_PAYLOAD_REQUEST_TOKENS,
        node_local=True,
    )


def _webhook_has_payload_contract(node: MakeAstNode) -> bool:
    """Return whether a webhook declares a payload schema or data structure."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=WEBHOOK_PAYLOAD_CONTRACT_TOKENS,
        node_local=True,
    )


def _webhook_has_payload_size_budget(node: MakeAstNode) -> bool:
    """Return whether a webhook declares payload-size budget evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=WEBHOOK_PAYLOAD_SIZE_BUDGET_TOKENS,
        node_local=True,
    )


def _webhook_has_method_guard(node: MakeAstNode) -> bool:
    """Return whether a webhook declares accepted HTTP method evidence."""
    return _json_has_http_method_guard(node.raw_payload, node_local=True)


def _webhook_has_backpressure_evidence(node: MakeAstNode) -> bool:
    """Return whether a webhook declares burst/backpressure evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=WEBHOOK_BACKPRESSURE_TOKENS,
        node_local=True,
    )


def _webhook_has_concurrency_budget(node: MakeAstNode) -> bool:
    """Return whether a webhook declares concurrency budget evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=WEBHOOK_CONCURRENCY_BUDGET_TOKENS,
        node_local=True,
    )


def _mailhook_has_sender_allowlist(node: MakeAstNode) -> bool:
    """Return whether a mailhook declares sender allowlist evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=MAILHOOK_SENDER_ALLOWLIST_TOKENS,
        node_local=True,
    )


def _http_request_node(node: MakeAstNode) -> bool:
    """Return whether one node is an HTTP request module."""
    token_key = module_token_semantic_key(node.module_token)
    return (
        node.kind == "http_api"
        or "makerequest" in token_key
        or token_key.startswith("http")
    )


def _http_method(node: MakeAstNode) -> str:
    """Return the configured HTTP method when it can be inferred locally."""
    method = _mapping_text(node.raw_payload, "method").upper()
    if method:
        return method
    text_blob = _json_text_blob(node.raw_payload, node_local=True).upper()
    for candidate in ("DELETE", "PATCH", "POST", "PUT", "GET"):
        if candidate in text_blob:
            return candidate
    return ""


def _http_declares_method_and_url(node: MakeAstNode) -> bool:
    """Return whether an HTTP request explicitly maps both method and URL."""
    return bool(_mapping_text(node.raw_payload, "method")) and bool(
        _mapping_text(node.raw_payload, "url")
    )


def _http_expects_structured_response(node: MakeAstNode) -> bool:
    """Return if an HTTP request expects JSON, array, or collection output."""
    if _http_method(node) != "GET":
        return False
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_STRUCTURED_RESPONSE_TOKENS,
        node_local=True,
    )


def _http_expects_json_response(node: MakeAstNode) -> bool:
    """Return whether an HTTP request declares JSON response expectations."""
    return _http_parses_json_response(node) or _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_JSON_RESPONSE_EXPECTATION_TOKENS,
        node_local=True,
    )


def _http_parse_response_enabled(node: MakeAstNode) -> bool:
    """Return whether an HTTP request declares response parsing."""
    return _json_has_truthy_key_token(
        node.raw_payload,
        tokens=HTTP_PARSE_RESPONSE_KEYS,
        node_local=True,
    )


def _http_declares_success_status_contract(node: MakeAstNode) -> bool:
    """Return whether an HTTP request declares accepted success statuses."""
    return _json_has_http_success_status_contract(
        node.raw_payload, node_local=True
    )


def _http_error_status_evaluation_disabled(node: MakeAstNode) -> bool:
    """Return whether Make HTTP `handleErrors` is explicitly disabled."""
    return _json_has_falsey_key_token(
        node.raw_payload,
        tokens=HTTP_HANDLE_ERRORS_KEY_TOKENS,
        node_local=True,
    )


def _http_redirects_enabled(node: MakeAstNode) -> bool:
    """Return whether an HTTP request declares redirect following."""
    return _json_has_truthy_key_token(
        node.raw_payload,
        tokens=HTTP_REDIRECT_ENABLED_TOKENS,
        node_local=True,
    )


def _http_declares_redirect_limit(node: MakeAstNode) -> bool:
    """Return whether an HTTP request declares redirect hop limits."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_REDIRECT_LIMIT_TOKENS,
        node_local=True,
    )


def _http_declares_redirect_host_policy(node: MakeAstNode) -> bool:
    """Return whether an HTTP request declares allowed redirect hosts."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_REDIRECT_HOST_POLICY_TOKENS,
        node_local=True,
    )


def _http_declares_redirect_credential_policy(node: MakeAstNode) -> bool:
    """Return whether an HTTP request declares credential forwarding posture."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_REDIRECT_CREDENTIAL_POLICY_TOKENS,
        node_local=True,
    )


def _http_declares_authorization_header(node: MakeAstNode) -> bool:
    """Return whether an HTTP request declares an Authorization header."""
    return _json_has_http_header_name(
        node.raw_payload,
        header_name="authorization",
        node_local=True,
    )


def _http_response_may_be_empty(node: MakeAstNode) -> bool:
    """Return whether local success-status evidence admits an empty response."""
    return _json_has_http_empty_body_status_contract(
        node.raw_payload, node_local=True
    )


def _http_declares_empty_body_parse_guard(node: MakeAstNode) -> bool:
    """Return if an HTTP request declares empty-body parse guard evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_EMPTY_BODY_PARSE_GUARD_TOKENS,
        node_local=True,
    )


def _http_parses_json_response(node: MakeAstNode) -> bool:
    """Return whether an HTTP request declares JSON response parsing."""
    return _http_parse_response_enabled(node) and _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_JSON_RESPONSE_PARSE_TOKENS,
        node_local=True,
    )


def _http_declares_response_content_type_guard(node: MakeAstNode) -> bool:
    """Return whether an HTTP request declares response Content-Type guard.

    evidence.
    """
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_RESPONSE_CONTENT_TYPE_GUARD_TOKENS,
        node_local=True,
    )


def _http_retries_permanent_errors(node: MakeAstNode) -> bool:
    """Return whether an HTTP request retry policy includes permanent errors."""
    return _json_has_http_permanent_error_retry_policy(
        node.raw_payload, node_local=True
    )


def _http_handles_auth_error_status(node: MakeAstNode) -> bool:
    """Return whether local status evidence includes 401 auth handling."""
    return _json_has_http_auth_error_status_contract(
        node.raw_payload, node_local=True
    )


def _http_declares_auth_error_branch(node: MakeAstNode) -> bool:
    """Return whether an HTTP request declares 401 auth branch evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_AUTH_ERROR_HANDLING_TOKENS,
        node_local=True,
    )


def _http_handles_not_found_status(node: MakeAstNode) -> bool:
    """Return whether local status evidence includes 404 handling."""
    return _json_has_http_not_found_status_contract(
        node.raw_payload, node_local=True
    )


def _http_declares_not_found_classification(node: MakeAstNode) -> bool:
    """Return whether an HTTP request declares 404 semantic classification.

    evidence.
    """
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_NOT_FOUND_CLASSIFICATION_TOKENS,
        node_local=True,
    )


def _http_handles_conflict_status(node: MakeAstNode) -> bool:
    """Return whether local status evidence includes 409 conflict handling."""
    return _json_has_http_conflict_status_contract(
        node.raw_payload, node_local=True
    )


def _http_declares_conflict_branch(node: MakeAstNode) -> bool:
    """Return whether an HTTP request declares 409 conflict branch evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_CONFLICT_HANDLING_TOKENS,
        node_local=True,
    )


def _http_declares_conflict_resume(node: MakeAstNode) -> bool:
    """Return whether an HTTP request declares 409 resume or dedupe evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_CONFLICT_RESUME_TOKENS,
        node_local=True,
    )


def _http_handles_rate_limit_status(node: MakeAstNode) -> bool:
    """Return whether local status evidence includes 429 rate-limit handling."""
    return _json_has_http_rate_limit_status_contract(
        node.raw_payload, node_local=True
    )


def _http_declares_rate_limit_branch(node: MakeAstNode) -> bool:
    """Return if an HTTP request declares 429 rate-limit branch evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_RATE_LIMIT_HANDLING_TOKENS,
        node_local=True,
    )


def _http_handles_server_error_status(node: MakeAstNode) -> bool:
    """Return whether local status evidence includes 5xx handling."""
    return _json_has_http_server_error_status_contract(
        node.raw_payload, node_local=True
    )


def _http_declares_server_error_backoff(node: MakeAstNode) -> bool:
    """Return if an HTTP request declares 5xx backoff or queueing evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_SERVER_ERROR_BACKOFF_TOKENS,
        node_local=True,
    )


def _http_has_blind_error_catchall(node: MakeAstNode) -> bool:
    """Return whether a generic catch-all handles mixed status classes."""
    return (
        _http_handles_auth_error_status(node)
        and _http_handles_rate_limit_status(node)
        and _http_handles_server_error_status(node)
        and _http_declares_generic_error_catchall(node)
        and not _http_declares_distinct_error_status_class_handling(node)
    )


def _http_declares_generic_error_catchall(node: MakeAstNode) -> bool:
    """Return if an HTTP request declares generic error catch-all evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_GENERIC_ERROR_CATCHALL_TOKENS,
        node_local=True,
    )


def _http_declares_distinct_error_status_class_handling(
    node: MakeAstNode,
) -> bool:
    """Return if auth, rate-limit, and server-error classes have evidence."""
    return (
        _http_declares_auth_error_branch(node)
        and _http_declares_rate_limit_branch(node)
        and _http_declares_server_error_backoff(node)
    )


def _http_declares_json_accept_header(node: MakeAstNode) -> bool:
    """Return whether an HTTP request declares Accept: application/json."""
    return _json_has_http_header_value(
        node.raw_payload,
        header_name="accept",
        value_tokens=HTTP_JSON_ACCEPT_HEADER_TOKENS,
        node_local=True,
    )


def _http_provider_forbids_accept_header(node: MakeAstNode) -> bool:
    """Return if local evidence says the provider forbids Accept headers."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_ACCEPT_HEADER_FORBIDDEN_TOKENS,
        node_local=True,
    )


def _http_has_request_body(node: MakeAstNode) -> bool:
    """Return whether an HTTP request declares request-body evidence."""
    return _json_has_evidence_key_token(
        _node_configuration_payload(node),
        tokens=HTTP_REQUEST_BODY_KEYS,
    )


def _http_declares_get_body_allowlist(node: MakeAstNode) -> bool:
    """Return if local evidence allowlists a nonstandard GET request body."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_GET_BODY_ALLOWLIST_TOKENS,
        node_local=True,
    )


def _http_has_retry_policy_evidence(node: MakeAstNode) -> bool:
    """Return whether an HTTP request declares retry behavior evidence."""
    return _json_has_http_retry_policy(node.raw_payload, node_local=True)


def _http_declares_idempotency_evidence(node: MakeAstNode) -> bool:
    """Return whether an HTTP mutation declares idempotency or transaction.

    evidence.
    """
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_IDEMPOTENCY_EVIDENCE_TOKENS,
        node_local=True,
    )


def _http_declares_patch_semantics(node: MakeAstNode) -> bool:
    """Return if a PATCH request declares partial-update semantics evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_PATCH_SEMANTICS_TOKENS,
        node_local=True,
    )


def _http_declares_put_replacement_guard(node: MakeAstNode) -> bool:
    """Return if a PUT request declares replacement or conversion evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_PUT_REPLACEMENT_GUARD_TOKENS,
        node_local=True,
    )


def _http_declares_delete_body_guard(node: MakeAstNode) -> bool:
    """Return if a DELETE request body declares provider-support evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_DELETE_BODY_GUARD_TOKENS,
        node_local=True,
    )


def _http_expects_response_body(node: MakeAstNode) -> bool:
    """Return whether an HTTP request declares response-body expectations."""
    return _json_has_evidence_key_token(
        _node_configuration_payload(node),
        tokens=HTTP_RESPONSE_BODY_EXPECTATION_KEYS,
    )


def _http_declares_options_allowed_use(node: MakeAstNode) -> bool:
    """Return if an OPTIONS request declares CORS or capability evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_OPTIONS_ALLOWED_USE_TOKENS,
        node_local=True,
    )


def _http_response_needs_schema_guard(node: MakeAstNode) -> bool:
    """Return if an HTTP response is parsed or expected as structured data."""
    return (
        _http_parse_response_enabled(node)
        or _http_expects_json_response(node)
        or _http_expects_structured_response(node)
    )


def _http_declares_response_schema_guard(node: MakeAstNode) -> bool:
    """Return whether an HTTP response declares schema or fallback evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_RESPONSE_SCHEMA_GUARD_TOKENS,
        node_local=True,
    )


def _http_body_maps_size_sensitive_source(node: MakeAstNode) -> bool:
    """Return whether a request body visibly maps payload, file, or array-like.

    data.
    """
    body_text = _mapping_text(node.raw_payload, "body")
    if "{{" not in body_text or "}}" not in body_text:
        return False
    normalized_body = module_token_semantic_key(body_text)
    return any(
        token in normalized_body
        for token in HTTP_SIZE_SENSITIVE_BODY_MAPPING_TOKENS
    )


def _http_declares_body_size_budget(node: MakeAstNode) -> bool:
    """Return whether an HTTP request declares body size-budget evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_BODY_SIZE_BUDGET_TOKENS,
        node_local=True,
    )


def _http_declares_response_size_budget(node: MakeAstNode) -> bool:
    """Return whether an HTTP response declares size-budget evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_RESPONSE_SIZE_BUDGET_TOKENS,
        node_local=True,
    )


def _http_uses_unvalidated_raw_json_body(node: MakeAstNode) -> bool:
    """Return if application/json is paired with unvalidated raw body text."""
    if (
        _http_method(node) not in HTTP_WRITE_METHODS
        or not _http_declares_request_json_content_type(node)
        or _http_declares_json_body_validation(node)
    ):
        return False
    body_text = _mapping_text(node.raw_payload, "body").strip()
    if not body_text:
        return False
    return _http_declares_raw_body_type(
        node
    ) or not _http_body_text_is_json_container(body_text)


def _http_uses_invalid_json_body_shape(node: MakeAstNode) -> bool:
    """Return whether a JSON request body has invalid local JSON shape."""
    if _http_method(
        node
    ) not in HTTP_WRITE_METHODS or not _http_declares_request_json_content_type(
        node
    ):
        return False
    body_text = _mapping_text(node.raw_payload, "body").strip()
    if not body_text or not _http_body_text_looks_json_value(body_text):
        return False
    try:
        parsed = cast("object", json.loads(body_text))
    except json.JSONDecodeError:
        return True
    return not isinstance(parsed, dict | list | str)


def _http_declares_request_json_content_type(node: MakeAstNode) -> bool:
    """Return if an HTTP request declares Content-Type: application/json."""
    return _json_has_http_header_value(
        node.raw_payload,
        header_name="content-type",
        value_tokens=HTTP_JSON_ACCEPT_HEADER_TOKENS,
        node_local=True,
    )


def _http_declares_raw_body_type(node: MakeAstNode) -> bool:
    """Return whether an HTTP request declares raw body mode."""
    normalized_keys = tuple(
        module_token_semantic_key(token) for token in HTTP_RAW_BODY_TYPE_KEYS
    )
    for container_key in ("parameters", "mapper"):
        container = _object_or_empty(node.raw_payload.get(container_key))
        for key, value in container.items():
            if module_token_semantic_key(key) not in normalized_keys:
                continue
            if _json_has_key_or_text_token(
                value, tokens=HTTP_RAW_BODY_TYPE_TOKENS
            ):
                return True
    return False


def _http_body_text_is_json_container(value: str) -> bool:
    """Return if raw body text is visibly an object or array JSON container."""
    stripped = value.strip()
    return (stripped.startswith("{") and stripped.endswith("}")) or (
        stripped.startswith("[") and stripped.endswith("]")
    )


def _http_body_text_looks_json_value(value: str) -> bool:
    """Return whether request body text starts like a JSON object, array, or.

    string.
    """
    stripped = value.strip()
    return (
        stripped.startswith(("{", "[", '"', "-"))
        or stripped[:1].isdigit()
        or stripped in {"true", "false", "null"}
    )


def _http_declares_json_body_validation(node: MakeAstNode) -> bool:
    """Return whether an HTTP request declares JSON body validation evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_JSON_BODY_VALIDATION_TOKENS,
        node_local=True,
    )


def _http_declares_non_success_status_contract(node: MakeAstNode) -> bool:
    """Return whether an HTTP request declares non-success status evidence."""
    return _http_request_node(node) and (
        _http_handles_auth_error_status(node)
        or _http_handles_not_found_status(node)
        or _http_handles_conflict_status(node)
        or _http_handles_rate_limit_status(node)
        or _http_handles_server_error_status(node)
    )


def _scenario_declares_upstream_status_mapping(
    nodes: tuple[MakeAstNode, ...],
) -> bool:
    """Return if any local node declares upstream status mapping evidence."""
    return any(
        _json_has_key_or_text_token(
            node.raw_payload,
            tokens=HTTP_UPSTREAM_STATUS_MAPPING_TOKENS,
            node_local=True,
        )
        for node in nodes
    )


def _webhook_response_collapses_to_static_500(node: MakeAstNode) -> bool:
    """Return whether a webhook response node returns a static 500 status."""
    return module_looks_like_webhook_response(
        node.module_token
    ) and _json_has_exact_status_code(
        node.raw_payload,
        status_code=500,
        node_local=True,
    )


def _webhook_response_body_exceeds_size_limit(node: MakeAstNode) -> bool:
    """Return whether a webhook response declares a body size above 5 MB."""
    return _json_has_byte_count_over_limit(
        node.raw_payload,
        tokens=WEBHOOK_RESPONSE_BODY_SIZE_KEYS,
        limit=WEBHOOK_RESPONSE_BODY_SIZE_LIMIT_BYTES,
        node_local=True,
    )


def _webhook_response_has_body(node: MakeAstNode) -> bool:
    """Return whether a webhook response declares body content."""
    return _json_has_evidence_key_token(
        _node_configuration_payload(node),
        tokens=WEBHOOK_RESPONSE_BODY_CONTENT_KEYS,
        node_local=True,
    )


def _webhook_response_declares_content_type(node: MakeAstNode) -> bool:
    """Return if a webhook response declares a concrete Content-Type header."""
    return _json_has_http_header_value(
        node.raw_payload,
        header_name="content-type",
        value_tokens=WEBHOOK_RESPONSE_CONTENT_TYPE_TOKENS,
        node_local=True,
    )


def _http_targets_static_external_endpoint(node: MakeAstNode) -> bool:
    """Return if an HTTP request targets a static external HTTP(S) endpoint."""
    url = _mapping_text(node.raw_payload, "url")
    if not url or "{{" in url or "}}" in url:
        return False
    parts = urlsplit(url)
    return parts.scheme.casefold() in {
        "http ",
        "https",
    } and not _http_local_host(parts.hostname)


def _http_local_host(hostname: str | None) -> bool:
    """Return whether a hostname is a local development endpoint."""
    if hostname is None:
        return False
    normalized = hostname.casefold().strip("[]").rstrip(".")
    return normalized in HTTP_LOCAL_HOSTS or any(
        candidate.is_loopback for candidate in host_ip_candidates(normalized)
    )


def _http_declares_user_agent_context(node: MakeAstNode) -> bool:
    """Return whether an HTTP request declares User-Agent or context headers."""
    return any(
        _json_has_http_header_name(
            node.raw_payload, header_name=header_name, node_local=True
        )
        for header_name in HTTP_USER_AGENT_CONTEXT_HEADER_NAMES
    ) or _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_USER_AGENT_CONTEXT_TOKENS,
        node_local=True,
    )


def _http_provider_forbids_user_agent(node: MakeAstNode) -> bool:
    """Return whether an HTTP request declares provider-forbids User-Agent.

    evidence.
    """
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_PROVIDER_FORBIDS_USER_AGENT_TOKENS,
        node_local=True,
    )


def _http_depends_on_restore_label(node: MakeAstNode) -> bool:
    """Return if restore or label text appears to hold missing HTTP config."""
    label_payload = _http_restore_label_payload(node)
    if not label_payload:
        return False
    return (
        (
            _http_restore_label_has_url_hint(label_payload)
            and not _mapping_text(node.raw_payload, "url")
        )
        or (
            _json_mentions_http_method(label_payload)
            and not _mapping_text(node.raw_payload, "method")
        )
        or (
            _json_has_key_or_text_token(
                label_payload,
                tokens=HTTP_RESTORE_LABEL_AUTH_TOKENS,
            )
            and not _http_declares_runtime_auth_config(node)
        )
    )


def _http_restore_label_payload(node: MakeAstNode) -> JsonObject:
    """Return human-facing restore and label metadata for one HTTP node."""
    metadata = _object_or_empty(node.raw_payload.get("metadata"))
    designer = _object_or_empty(metadata.get("designer"))
    payload: JsonObject = {}
    for source, source_payload in (
        ("node", node.raw_payload),
        ("metadata", metadata),
        ("designer", designer),
    ):
        for key in ("label", "name"):
            value = source_payload.get(key)
            if _has_evidence_value(value):
                payload[f"{source}_{key}"] = value
    restore = metadata.get("restore")
    if _has_evidence_value(restore):
        payload["metadata_restore"] = restore
    return payload


def _http_restore_label_has_url_hint(value: object) -> bool:
    """Return whether restore or label metadata visibly names an HTTP URL."""
    text_blob = _json_text_blob(value, node_local=True)
    return "http://" in text_blob or "https://" in text_blob


def _http_declares_runtime_auth_config(node: MakeAstNode) -> bool:
    """Return whether parameters or mapper carry HTTP auth configuration."""
    runtime_payload: JsonObject = {
        "parameters": _object_or_empty(node.raw_payload.get("parameters")),
        "mapper": _object_or_empty(node.raw_payload.get("mapper")),
    }
    return _json_has_http_header_name(
        runtime_payload,
        header_name="authorization",
        node_local=True,
    ) or _json_has_key_or_text_token(
        runtime_payload,
        tokens=HTTP_RUNTIME_AUTH_TOKENS,
        node_local=True,
    )


def _http_uploads_file(node: MakeAstNode) -> bool:
    """Return whether an HTTP request locally appears to upload a file."""
    return _http_method(
        node
    ) in HTTP_WRITE_METHODS and _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_FILE_UPLOAD_TOKENS,
        node_local=True,
    )


def _http_uses_multipart_body(node: MakeAstNode) -> bool:
    """Return if an HTTP request declares multipart/form-data body handling."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_MULTIPART_TOKENS,
        node_local=True,
    )


def _http_sends_json_body(node: MakeAstNode) -> bool:
    """Return whether an HTTP request appears to send a JSON body."""
    if _http_method(node) not in HTTP_WRITE_METHODS:
        return False
    body_text = _mapping_text(node.raw_payload, "body").strip()
    return body_text.startswith(("{", "[")) or _json_has_key_or_text_token(
        _node_configuration_payload(node),
        tokens=HTTP_JSON_BODY_TOKENS,
    )


def _http_declares_json_content_type(node: MakeAstNode) -> bool:
    """Return whether an HTTP request declares JSON content type."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=HTTP_CONTENT_TYPE_TOKENS,
        node_local=True,
    )


def _iterator_node(node: MakeAstNode) -> bool:
    """Return whether one node is an iterator module."""
    return node.kind == "iterator" or "iterator" in module_token_semantic_key(
        node.module_token
    )


def _iterator_has_array_input(node: MakeAstNode) -> bool:
    """Return whether an iterator declares its source array input."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=ITERATOR_ARRAY_INPUT_TOKENS,
        node_local=True,
    )


def _iterator_has_item_limit(node: MakeAstNode) -> bool:
    """Return whether an iterator declares item-count or chunking evidence."""
    return _json_has_key_or_text_token(
        _node_configuration_payload(node),
        tokens=ITERATOR_ITEM_LIMIT_TOKENS,
    )


def _aggregator_node(node: MakeAstNode) -> bool:
    """Return whether one node is an aggregator module."""
    token_key = module_token_semantic_key(node.module_token)
    return node.kind == "aggregator" or "aggregator" in token_key


def _aggregator_has_source(node: MakeAstNode) -> bool:
    """Return whether an aggregator declares its source module or array."""
    return _json_has_key_or_text_token(
        _node_configuration_payload(node),
        tokens=AGGREGATOR_SOURCE_TOKENS,
    )


def _aggregator_has_bundle_limit(node: MakeAstNode) -> bool:
    """Return if an aggregator declares bundle-count or chunking evidence."""
    return _json_has_key_or_text_token(
        _node_configuration_payload(node),
        tokens=AGGREGATOR_BUNDLE_LIMIT_TOKENS,
    )


def _aggregator_has_strategy(node: MakeAstNode) -> bool:
    """Return whether an aggregator declares its aggregation strategy."""
    return _json_has_key_or_text_token(
        _node_configuration_payload(node),
        tokens=AGGREGATOR_STRATEGY_TOKENS,
    )


def _text_parser_node(node: MakeAstNode) -> bool:
    """Return whether one node is a text parser or regex-focused module."""
    token_key = module_token_semantic_key(node.module_token)
    return any(
        module_token_semantic_key(token) in token_key
        for token in ("match pattern", "regex", "text parser")
    )


def _text_parser_has_pattern(node: MakeAstNode) -> bool:
    """Return whether a text parser declares a regex or pattern."""
    return _json_has_key_or_text_token(
        _node_configuration_payload(node),
        tokens=TEXT_PARSER_PATTERN_TOKENS,
    )


def _text_parser_has_input(node: MakeAstNode) -> bool:
    """Return whether a text parser declares the text it processes."""
    return _json_has_key_or_text_token(
        _node_configuration_payload(node),
        tokens=TEXT_PARSER_INPUT_TOKENS,
    )


def _parse_json_node(node: MakeAstNode) -> bool:
    """Return whether one node is a Parse JSON module."""
    token_key = module_token_semantic_key(node.module_token)
    return "parsejson" in token_key or (
        "parse" in token_key
        and "json" in token_key
        and "textparser" not in token_key
    )


def _parse_json_has_schema(node: MakeAstNode) -> bool:
    """Return whether a Parse JSON module declares local schema evidence."""
    return _json_has_key_or_text_token(
        _node_configuration_payload(node),
        tokens=PARSE_JSON_SCHEMA_TOKENS,
    )


def _data_store_delete_node(node: MakeAstNode) -> bool:
    """Return whether one node is a data-store delete operation."""
    token_key = module_token_semantic_key(node.module_token)
    return "datastore" in token_key and "delete" in token_key


def _data_store_has_recovery_posture(node: MakeAstNode) -> bool:
    """Return if a data-store delete declares recovery or audit evidence."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=DATA_STORE_RECOVERY_TOKENS,
        node_local=True,
    )


def _data_store_write_node(node: MakeAstNode) -> bool:
    """Return whether one node is a data-store write operation."""
    token_key = module_token_semantic_key(node.module_token)
    if "datastore" not in token_key or "delete" in token_key:
        return False
    return any(
        marker in token_key
        for marker in ("add", "create", "set", "update", "upsert")
    )


def _data_store_has_key(node: MakeAstNode) -> bool:
    """Return whether a data-store write declares a stable key."""
    return _json_has_key_or_text_token(
        _node_configuration_payload(node),
        tokens=DATA_STORE_KEY_TOKENS,
    )


def _data_store_ephemeral_state_node(node: MakeAstNode) -> bool:
    """Return whether a data-store write declares temporary state semantics."""
    return _json_has_key_or_text_token(
        _node_configuration_payload(node),
        tokens=DATA_STORE_EPHEMERAL_STATE_TOKENS,
    )


def _data_store_has_ttl(node: MakeAstNode) -> bool:
    """Return whether a data-store write declares TTL or cleanup evidence."""
    return _json_has_key_or_text_token(
        _node_configuration_payload(node),
        tokens=DATA_STORE_TTL_TOKENS,
    )


def _data_store_has_secret_storage(node: MakeAstNode) -> bool:
    """Return whether a data-store write stores secret-like local evidence."""
    return _json_has_secret_storage_evidence(
        _node_configuration_payload(node),
        path=(),
    )


def _basic_trigger_node(node: MakeAstNode) -> bool:
    """Return whether one node is a basic trigger."""
    return module_token_semantic_key(
        "basic trigger"
    ) in module_token_semantic_key(node.module_token)


def _basic_trigger_has_interface(node: MakeAstNode) -> bool:
    """Return whether a basic trigger declares output fields."""
    return _json_has_key_or_text_token(
        node.raw_payload,
        tokens=WEBHOOK_PAYLOAD_CONTRACT_TOKENS,
        node_local=True,
    )


def _mcp_tool_node(node: MakeAstNode) -> bool:
    """Return whether one node is an MCP tool module."""
    return node.kind == "mcp_tool" or "mcp" in module_token_semantic_key(
        node.module_token
    )


def _tool_contract_declared(node: MakeAstNode) -> bool:
    """Return whether a tool-like node declares input and output contracts."""
    payload = _node_configuration_payload(node)
    return _json_has_key_or_text_token(
        payload,
        tokens=TOOL_CONTRACT_INPUT_TOKENS,
    ) and _json_has_key_or_text_token(
        payload,
        tokens=TOOL_CONTRACT_OUTPUT_TOKENS,
    )


def _custom_app_node(node: MakeAstNode) -> bool:
    """Return whether one node appears to belong to a custom app."""
    token_key = module_token_semantic_key(node.module_token)
    return module_token_semantic_key("custom app") in token_key or (
        "custom" in token_key and "app" in token_key
    )


def _custom_app_has_schema_contract(node: MakeAstNode) -> bool:
    """Return whether a custom app module declares schema contract evidence."""
    return bool(
        node.raw_spec_binding.catalog_module_id
    ) or _json_has_key_or_text_token(
        node.raw_payload,
        tokens=WEBHOOK_PAYLOAD_CONTRACT_TOKENS,
        node_local=True,
    )


def _node_configuration_payload(node: MakeAstNode) -> JsonObject:
    """Return config containers that exclude top-level node identity fields."""
    return {
        "parameters": _object_or_empty(node.raw_payload.get("parameters")),
        "mapper": _object_or_empty(node.raw_payload.get("mapper")),
        "metadata": _object_or_empty(node.raw_payload.get("metadata")),
    }


def _scenario_declares_governance_profile(root: MakeAstRoot) -> bool:
    """Return if root metadata declares production or governance posture."""
    return _json_has_key_or_text_token(
        root.scenario.metadata,
        tokens=SCENARIO_GOVERNANCE_PROFILE_TOKENS,
    )


def _scenario_declares_incident_profile(root: MakeAstRoot) -> bool:
    """Return whether root metadata declares critical incident posture."""
    return _json_has_key_or_text_token(
        root.scenario.metadata,
        tokens=SCENARIO_INCIDENT_PROFILE_TOKENS,
    )


def _scenario_has_owner(root: MakeAstRoot) -> bool:
    """Return whether root metadata declares owner or escalation evidence."""
    return _json_has_key_or_text_token(
        root.scenario.metadata,
        tokens=SCENARIO_OWNER_TOKENS,
    )


def _scenario_has_change_reason(root: MakeAstRoot) -> bool:
    """Return whether root metadata declares change-reason evidence."""
    return _json_has_key_or_text_token(
        root.scenario.metadata,
        tokens=SCENARIO_CHANGE_REASON_TOKENS,
    )


def _scenario_has_rollback_plan(root: MakeAstRoot) -> bool:
    """Return whether root metadata declares rollback-plan evidence."""
    return _json_has_key_or_text_token(
        root.scenario.metadata,
        tokens=SCENARIO_ROLLBACK_TOKENS,
    )


def _scenario_has_incident_notes(root: MakeAstRoot) -> bool:
    """Return whether root metadata declares incident or runbook evidence."""
    return _json_has_key_or_text_token(
        root.scenario.metadata,
        tokens=SCENARIO_INCIDENT_NOTE_TOKENS,
    )


def _node_has_production_debug_marker(node: MakeAstNode) -> bool:
    """Return whether a node visibly carries debug or test-channel evidence."""
    identity_text = module_token_semantic_key(
        f"{node.module_token} {node.label}"
    )
    if any(
        module_token_semantic_key(token) in identity_text
        for token in SCENARIO_PRODUCTION_DEBUG_TOKENS
    ):
        return True
    return _json_has_key_or_text_token(
        _node_configuration_payload(node),
        tokens=SCENARIO_PRODUCTION_DEBUG_TOKENS,
    )


def _knowledge_severity(value: str) -> BlueprintFindingSeverity:
    """Return a valid validation severity for a knowledge-store value."""
    if value in {"error", "warning", "optimization", "explanation"}:
        return cast("BlueprintFindingSeverity", value)
    return "warning"


def _operation_volume_review_finding(
    node: MakeAstNode,
) -> BlueprintValidationFinding:
    """Return one operation-volume review finding."""
    return build_validation_finding(
        code="semantic.operation_volume_review",
        severity="optimization",
        node=(node.node_id, node.source_trace.path),
        catalog_module_id=None,
        messages=(
            "A module can multiply bundle or operation volume.",
            (
                f"Node {node.node_id} module {node.module_token!r} needs "
                f"branch "
                f"and volume review."
            ),
        ),
    )


def _validate_designer_runtime_messages(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate deterministic runtime-blocking Make designer messages.

    Returns:
    The validation result for deterministic runtime-blocking Make designer
    messages.
    """
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        for message in _designer_message_texts(node):
            if not any(
                keyword in message.casefold() for keyword in AUTH_ERROR_KEYWORDS
            ):
                continue
            findings.append(
                build_validation_finding(
                    code="semantic.authentication_required",
                    severity="error",
                    node=(node.node_id, node.source_trace.path),
                    catalog_module_id=None,
                    messages=(
                        "A module requires authentication before it can run.",
                        (
                            f"Node {node.node_id} designer message requires "
                            f"authentication."
                        ),
                    ),
                )
            )
    return tuple(findings)


def _validate_trigger_semantics(
    *,
    nodes: tuple[MakeAstNode, ...],
    resolutions_by_node_identity: dict[int, MakeAstModuleResolution],
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate deterministic trigger placement semantics.

    Returns:
        The validation result for deterministic trigger placement semantics.
    """
    findings: list[BlueprintValidationFinding] = []
    root_triggers: list[MakeAstNode] = []
    top_level_nodes = [
        node
        for node in nodes
        if node.source_trace.parent_node_id is None
        and node.source_trace.container_kind == "flow"
    ]
    for index, node in enumerate(top_level_nodes):
        if not _trigger_like(
            node=node, resolution=resolutions_by_node_identity.get(id(node))
        ):
            continue
        root_triggers.append(node)
        if index != 0:
            findings.append(_trigger_position_finding(node))
    if len(root_triggers) > 1:
        findings.append(_multiple_root_triggers_finding(root_triggers))
    for node in nodes:
        if node in top_level_nodes:
            continue
        if _trigger_like(
            node=node, resolution=resolutions_by_node_identity.get(id(node))
        ):
            findings.append(_nested_trigger_finding(node))
    return tuple(findings)


def _validate_mapping_risks(
    root: MakeAstRoot,
) -> tuple[BlueprintValidationFinding, ...]:
    """Convert expression intelligence risks to validation findings.

    Returns:
        The documented result.
    """
    return tuple(
        _mapping_risk_finding(risk) for risk in analyze_mapping_risks(root)
    )


def _mapping_risk_finding(risk: MappingRisk) -> BlueprintValidationFinding:
    """Return one validation finding from one mapping risk."""
    return build_validation_finding(
        code=risk.code,
        severity=risk.severity,
        node=(risk.node_id, risk.source_path),
        catalog_module_id=None,
        messages=(
            risk.client_message,
            (
                f"{risk.internal_message}; repair: "
                f"{risk.repair_suggestion.internal_detail}"
            ),
        ),
    )


def _field_is_mapped(*, node: MakeAstNode, field: CatalogField) -> bool:
    """Return whether a field path exists in parameters or mapper."""
    for mapping_key in ("parameters", "mapper"):
        value = _object_or_empty(node.raw_payload.get(mapping_key))
        if _json_path_has_value(value, field.path):
            return True
        if mapping_key == "parameters" and _connection_field_alias_is_mapped(
            payload=value,
            field=field,
        ):
            return True
    return False


def _connection_field_alias_is_mapped(
    *, payload: JsonObject, field: CatalogField
) -> bool:
    """Return if a Make connection field is present under a legacy alias."""
    return any(
        _json_path_has_value(payload, (alias,))
        for alias in make_connection_parameter_aliases_for_field(field)
    )


def _json_path_has_value(payload: JsonObject, path: tuple[str, ...]) -> bool:
    """Return whether one JSON path exists and has a meaningful value."""
    current: object = payload
    for part in path:
        if not _is_json_object(current):
            return False
        if part not in current:
            return False
        current = current[part]
    return _is_meaningful_json_value(current)


def _is_meaningful_json_value(value: object) -> bool:
    """Return if one JSON boundary value carries required-field evidence."""
    if value is None or _is_empty_json_string(value):
        return False
    if isinstance(value, dict):
        return bool(cast("dict[object, object]", value))
    if isinstance(value, list):
        return bool(cast("list[object]", value))
    return True


def _is_empty_json_string(value: object) -> bool:
    """Return whether a JSON boundary value is specifically an empty string."""
    return isinstance(value, str) and not value.strip()


def _object_or_empty(value: object) -> JsonObject:
    """Return an object value or an empty object for mapping inspection."""
    return value if _is_json_object(value) else {}


def _mapping_text(node_payload: JsonObject, key: str) -> str:
    """Return one text field from node parameters or mapper."""
    for container_key in ("parameters", "mapper"):
        value = _object_or_empty(node_payload.get(container_key)).get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _designer_message_texts(node: MakeAstNode) -> tuple[str, ...]:
    """Return text from Make designer messages when they are list-shaped."""
    designer = _object_or_empty(
        _object_or_empty(node.raw_payload.get("metadata")).get("designer")
    )
    messages = designer.get("messages")
    if not isinstance(messages, list):
        return ()
    texts: list[str] = []
    for message in cast("list[object]", messages):
        if not _is_json_object(message):
            continue
        text = _message_text(message)
        if text is not None:
            texts.append(text)
    return tuple(texts)


def _message_text(message: JsonObject) -> str | None:
    for key in ("message", "text"):
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _json_has_key_or_text_token(
    value: object,
    *,
    tokens: tuple[str, ...],
    node_local: bool = False,
    path: tuple[AstPathPart, ...] = (),
) -> bool:
    """Return whether JSON-like data contains one token in keys or values."""
    if node_local and _descends_into_child_node(path):
        return False
    normalized_tokens = tuple(
        module_token_semantic_key(token) for token in tokens
    )
    if isinstance(value, str):
        normalized_value = module_token_semantic_key(value)
        return any(token in normalized_value for token in normalized_tokens)
    if _is_json_object(value):
        return _json_object_has_key_or_text_token(
            value,
            tokens=tokens,
            normalized_tokens=normalized_tokens,
            node_local=node_local,
            path=path,
        )
    if isinstance(value, list):
        return _json_list_has_key_or_text_token(
            cast("list[object]", value),
            tokens=tokens,
            node_local=node_local,
            path=path,
        )
    if value is None:
        return False
    normalized_value = module_token_semantic_key(str(value))
    return any(token in normalized_value for token in normalized_tokens)


def _json_object_has_key_or_text_token(
    value: JsonObject,
    *,
    tokens: tuple[str, ...],
    normalized_tokens: tuple[str, ...],
    node_local: bool,
    path: tuple[AstPathPart, ...],
) -> bool:
    """Return whether a JSON object contains one token in keys or values."""
    for key, item in value.items():
        normalized_key = module_token_semantic_key(key)
        if any(
            token in normalized_key for token in normalized_tokens
        ) and _has_evidence_value(item):
            return True
        if _json_has_key_or_text_token(
            item,
            tokens=tokens,
            node_local=node_local,
            path=(*path, key),
        ):
            return True
    return False


def _json_list_has_key_or_text_token(
    value: list[object],
    *,
    tokens: tuple[str, ...],
    node_local: bool,
    path: tuple[AstPathPart, ...],
) -> bool:
    """Return whether a JSON list contains one token in keys or values."""
    return any(
        _json_has_key_or_text_token(
            item,
            tokens=tokens,
            node_local=node_local,
            path=(*path, index),
        )
        for index, item in enumerate(value)
    )


def _json_has_secret_storage_evidence(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
) -> bool:
    """Return whether JSON-like data stores secret-like fields or mappings."""
    normalized_tokens = tuple(
        module_token_semantic_key(token)
        for token in DATA_STORE_SECRET_STORAGE_TOKENS
    )
    if isinstance(value, str):
        return _path_mentions_token(
            path, normalized_tokens
        ) and _has_evidence_value(value)
    if _is_json_object(value):
        return any(
            (
                _text_mentions_token(key, normalized_tokens)
                and _has_evidence_value(item)
            )
            or _json_has_secret_storage_evidence(item, path=(*path, key))
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(
            _json_has_secret_storage_evidence(item, path=(*path, index))
            for index, item in enumerate(cast("list[object]", value))
        )
    return False


def _path_mentions_token(
    path: tuple[AstPathPart, ...],
    normalized_tokens: tuple[str, ...],
) -> bool:
    """Return whether any string path part names one token."""
    return any(
        isinstance(part, str) and _text_mentions_token(part, normalized_tokens)
        for part in path
    )


def _text_mentions_token(
    value: str, normalized_tokens: tuple[str, ...]
) -> bool:
    """Return whether one text value contains a normalized token."""
    normalized_value = module_token_semantic_key(value)
    return any(token in normalized_value for token in normalized_tokens)


def _json_has_evidence_key_token(
    value: object,
    *,
    tokens: tuple[str, ...],
    node_local: bool = False,
    path: tuple[AstPathPart, ...] = (),
) -> bool:
    """Return if JSON-like data contains a token-bearing key with evidence."""
    if node_local and _descends_into_child_node(path):
        return False
    normalized_tokens = tuple(
        module_token_semantic_key(token) for token in tokens
    )
    if _is_json_object(value):
        for key, item in value.items():
            normalized_key = module_token_semantic_key(key)
            if normalized_key in normalized_tokens and _has_evidence_value(
                item
            ):
                return True
            if _json_has_evidence_key_token(
                item,
                tokens=tokens,
                node_local=node_local,
                path=(*path, key),
            ):
                return True
    if isinstance(value, list):
        return any(
            _json_has_evidence_key_token(
                item,
                tokens=tokens,
                node_local=node_local,
                path=(*path, index),
            )
            for index, item in enumerate(cast("list[object]", value))
        )
    return False


def _json_has_http_header_value(
    value: object,
    *,
    header_name: str,
    value_tokens: tuple[str, ...],
    node_local: bool = False,
    path: tuple[AstPathPart, ...] = (),
) -> bool:
    """Return whether JSON-like data declares one HTTP header value."""
    if node_local and _descends_into_child_node(path):
        return False
    normalized_header_name = module_token_semantic_key(header_name)
    normalized_value_tokens = tuple(
        module_token_semantic_key(token) for token in value_tokens
    )
    if _is_json_object(value):
        if _http_header_object_matches(
            value,
            normalized_header_name=normalized_header_name,
            normalized_value_tokens=normalized_value_tokens,
        ):
            return True
        for key, item in value.items():
            normalized_key = module_token_semantic_key(key)
            if (
                normalized_key == normalized_header_name
                and _http_header_value_matches(
                    item,
                    normalized_value_tokens=normalized_value_tokens,
                )
            ):
                return True
            if _json_has_http_header_value(
                item,
                header_name=header_name,
                value_tokens=value_tokens,
                node_local=node_local,
                path=(*path, key),
            ):
                return True
    if isinstance(value, list):
        return any(
            _json_has_http_header_value(
                item,
                header_name=header_name,
                value_tokens=value_tokens,
                node_local=node_local,
                path=(*path, index),
            )
            for index, item in enumerate(cast("list[object]", value))
        )
    return False


def _json_has_http_header_name(
    value: object,
    *,
    header_name: str,
    node_local: bool = False,
    path: tuple[AstPathPart, ...] = (),
) -> bool:
    """Return whether JSON-like data declares one HTTP header name."""
    if node_local and _descends_into_child_node(path):
        return False
    normalized_header_name = module_token_semantic_key(header_name)
    if _is_json_object(value):
        if _http_header_object_name_matches(
            value,
            normalized_header_name=normalized_header_name,
        ):
            return True
        for key, item in value.items():
            if module_token_semantic_key(key) == normalized_header_name:
                return True
            if _json_has_http_header_name(
                item,
                header_name=header_name,
                node_local=node_local,
                path=(*path, key),
            ):
                return True
    if isinstance(value, list):
        return any(
            _json_has_http_header_name(
                item,
                header_name=header_name,
                node_local=node_local,
                path=(*path, index),
            )
            for index, item in enumerate(cast("list[object]", value))
        )
    return False


def _http_header_object_matches(
    value: JsonObject,
    *,
    normalized_header_name: str,
    normalized_value_tokens: tuple[str, ...],
) -> bool:
    """Return whether one header object declares the expected header value."""
    header_name = (
        _json_object_text(value, "name")
        or _json_object_text(value, "key")
        or _json_object_text(value, "header")
    )
    if module_token_semantic_key(header_name) != normalized_header_name:
        return False
    header_value = _json_object_text(value, "value") or _json_object_text(
        value, "content"
    )
    return _http_header_value_matches(
        header_value,
        normalized_value_tokens=normalized_value_tokens,
    )


def _http_header_object_name_matches(
    value: JsonObject,
    *,
    normalized_header_name: str,
) -> bool:
    """Return whether one header object declares the expected header name."""
    header_name = (
        _json_object_text(value, "name")
        or _json_object_text(value, "key")
        or _json_object_text(value, "header")
    )
    return module_token_semantic_key(header_name) == normalized_header_name


def _json_object_text(value: JsonObject, key: str) -> str:
    """Return one direct non-empty text field from a JSON object."""
    item = value.get(key)
    if isinstance(item, str) and item.strip():
        return item.strip()
    return ""


def _http_header_value_matches(
    value: object,
    *,
    normalized_value_tokens: tuple[str, ...],
) -> bool:
    """Return whether one header value matches expected value tokens."""
    if not isinstance(value, str):
        return False
    normalized_value = module_token_semantic_key(value)
    return any(token in normalized_value for token in normalized_value_tokens)


def _json_has_exact_status_code(
    value: object,
    *,
    status_code: int,
    node_local: bool = False,
    path: tuple[AstPathPart, ...] = (),
) -> bool:
    """Return whether JSON-like data declares an exact response status code."""
    if node_local and _descends_into_child_node(path):
        return False
    normalized_keys = tuple(
        module_token_semantic_key(token)
        for token in WEBHOOK_RESPONSE_STATUS_KEYS
    )
    if _is_json_object(value):
        for key, item in value.items():
            if module_token_semantic_key(
                key
            ) in normalized_keys and _json_mentions_exact_status_code(
                item, status_code=status_code
            ):
                return True
            if _json_has_exact_status_code(
                item,
                status_code=status_code,
                node_local=node_local,
                path=(*path, key),
            ):
                return True
    if isinstance(value, list):
        return any(
            _json_has_exact_status_code(
                item,
                status_code=status_code,
                node_local=node_local,
                path=(*path, index),
            )
            for index, item in enumerate(cast("list[object]", value))
        )
    return False


def _json_mentions_exact_status_code(
    value: object, *, status_code: int
) -> bool:
    """Return whether a JSON-like value names one exact status code."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value == status_code
    if isinstance(value, float):
        return value.is_integer() and int(value) == status_code
    if isinstance(value, str):
        return value.strip() == str(status_code)
    if _is_json_object(value):
        return any(
            _json_mentions_exact_status_code(item, status_code=status_code)
            for item in value.values()
        )
    return isinstance(value, list) and any(
        _json_mentions_exact_status_code(item, status_code=status_code)
        for item in cast("list[object]", value)
    )


def _json_has_byte_count_over_limit(
    value: object,
    *,
    tokens: tuple[str, ...],
    limit: int,
    node_local: bool = False,
    path: tuple[AstPathPart, ...] = (),
) -> bool:
    """Return whether JSON-like size metadata exceeds a byte limit."""
    if node_local and _descends_into_child_node(path):
        return False
    normalized_tokens = tuple(
        module_token_semantic_key(token) for token in tokens
    )
    if _is_json_object(value):
        for key, item in value.items():
            normalized_key = module_token_semantic_key(key)
            if any(token in normalized_key for token in normalized_tokens):
                byte_count = _byte_count_value(item)
                if byte_count is not None and byte_count > limit:
                    return True
            if _json_has_byte_count_over_limit(
                item,
                tokens=tokens,
                limit=limit,
                node_local=node_local,
                path=(*path, key),
            ):
                return True
    if isinstance(value, list):
        return any(
            _json_has_byte_count_over_limit(
                item,
                tokens=tokens,
                limit=limit,
                node_local=node_local,
                path=(*path, index),
            )
            for index, item in enumerate(cast("list[object]", value))
        )
    return False


def _byte_count_value(value: object) -> int | None:
    """Return a byte count from numeric or simple unit-suffixed metadata."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if math.isfinite(value) and value >= 0 else None
    if isinstance(value, str):
        return _byte_count_text(value)
    return None


def _byte_count_text(value: str) -> int | None:
    """Return a byte count from text like `5242881`, `5121 KB`, or `5.1 MB`."""
    cleaned = value.strip().replace(",", "")
    if not cleaned:
        return None
    parts = cleaned.split()
    if not parts:
        return None
    try:
        amount = float(parts[0])
    except ValueError:
        return None
    if not math.isfinite(amount) or amount < 0:
        return None
    unit = parts[1].casefold().rstrip(".") if len(parts) > 1 else "bytes"
    multipliers = {
        "b": 1,
        "byte": 1,
        "bytes": 1,
        "kb": 1024,
        "kib": 1024,
        "kilobyte": 1024,
        "kilobytes": 1024,
        "mb": 1024 * 1024,
        "mib": 1024 * 1024,
        "megabyte": 1024 * 1024,
        "megabytes": 1024 * 1024,
    }
    multiplier = multipliers.get(unit)
    if multiplier is None:
        return None
    return int(amount * multiplier)


def _json_has_truthy_key_token(
    value: object,
    *,
    tokens: tuple[str, ...],
    node_local: bool = False,
    path: tuple[AstPathPart, ...] = (),
) -> bool:
    """Return whether JSON-like data has a truthy field matching a token."""
    if node_local and _descends_into_child_node(path):
        return False
    normalized_tokens = tuple(
        module_token_semantic_key(token) for token in tokens
    )
    if _is_json_object(value):
        for key, item in value.items():
            normalized_key = module_token_semantic_key(key)
            if any(
                token in normalized_key for token in normalized_tokens
            ) and _truthy_json(item):
                return True
            if _json_has_truthy_key_token(
                item,
                tokens=tokens,
                node_local=node_local,
                path=(*path, key),
            ):
                return True
    if isinstance(value, list):
        return any(
            _json_has_truthy_key_token(
                item,
                tokens=tokens,
                node_local=node_local,
                path=(*path, index),
            )
            for index, item in enumerate(cast("list[object]", value))
        )
    return False


def _json_has_falsey_key_token(
    value: object,
    *,
    tokens: tuple[str, ...],
    node_local: bool = False,
    path: tuple[AstPathPart, ...] = (),
) -> bool:
    """Return the computed result for the caller."""
    if node_local and _descends_into_child_node(path):
        return False
    normalized_tokens = tuple(
        module_token_semantic_key(token) for token in tokens
    )
    if _is_json_object(value):
        for key, item in value.items():
            normalized_key = module_token_semantic_key(key)
            if any(
                token in normalized_key for token in normalized_tokens
            ) and _falsey_json(item):
                return True
            if _json_has_falsey_key_token(
                item,
                tokens=tokens,
                node_local=node_local,
                path=(*path, key),
            ):
                return True
    if isinstance(value, list):
        return any(
            _json_has_falsey_key_token(
                item,
                tokens=tokens,
                node_local=node_local,
                path=(*path, index),
            )
            for index, item in enumerate(cast("list[object]", value))
        )
    return False


def _json_has_http_success_status_contract(
    value: object,
    *,
    node_local: bool = False,
    path: tuple[AstPathPart, ...] = (),
) -> bool:
    """Return whether JSON-like data declares accepted HTTP success status.

    evidence.
    """
    if node_local and _descends_into_child_node(path):
        return False
    normalized_keys = tuple(
        module_token_semantic_key(token) for token in HTTP_SUCCESS_STATUS_KEYS
    )
    if _is_json_object(value):
        for key, item in value.items():
            normalized_key = module_token_semantic_key(key)
            if _http_success_status_key(normalized_key, normalized_keys) and (
                _json_mentions_http_success_status(item)
            ):
                return True
            if _json_has_http_success_status_contract(
                item,
                node_local=node_local,
                path=(*path, key),
            ):
                return True
    if isinstance(value, list):
        return any(
            _json_has_http_success_status_contract(
                item,
                node_local=node_local,
                path=(*path, index),
            )
            for index, item in enumerate(cast("list[object]", value))
        )
    return False


def _json_has_http_empty_body_status_contract(
    value: object,
    *,
    node_local: bool = False,
    path: tuple[AstPathPart, ...] = (),
) -> bool:
    """Return whether accepted HTTP status evidence permits an empty body."""
    if node_local and _descends_into_child_node(path):
        return False
    normalized_keys = tuple(
        module_token_semantic_key(token) for token in HTTP_SUCCESS_STATUS_KEYS
    )
    if _is_json_object(value):
        for key, item in value.items():
            normalized_key = module_token_semantic_key(key)
            if _http_success_status_key(normalized_key, normalized_keys) and (
                _json_mentions_http_empty_body_status(item)
            ):
                return True
            if _json_has_http_empty_body_status_contract(
                item,
                node_local=node_local,
                path=(*path, key),
            ):
                return True
    if isinstance(value, list):
        return any(
            _json_has_http_empty_body_status_contract(
                item,
                node_local=node_local,
                path=(*path, index),
            )
            for index, item in enumerate(cast("list[object]", value))
        )
    return False


def _json_has_http_not_found_status_contract(
    value: object,
    *,
    node_local: bool = False,
    path: tuple[AstPathPart, ...] = (),
) -> bool:
    """Return whether accepted HTTP status evidence includes 404."""
    if node_local and _descends_into_child_node(path):
        return False
    normalized_keys = tuple(
        module_token_semantic_key(token) for token in HTTP_SUCCESS_STATUS_KEYS
    )
    if _is_json_object(value):
        for key, item in value.items():
            normalized_key = module_token_semantic_key(key)
            if _http_success_status_key(normalized_key, normalized_keys) and (
                _json_mentions_http_not_found_status(item)
            ):
                return True
            if _json_has_http_not_found_status_contract(
                item,
                node_local=node_local,
                path=(*path, key),
            ):
                return True
    if isinstance(value, list):
        return any(
            _json_has_http_not_found_status_contract(
                item,
                node_local=node_local,
                path=(*path, index),
            )
            for index, item in enumerate(cast("list[object]", value))
        )
    return False


def _json_has_http_auth_error_status_contract(
    value: object,
    *,
    node_local: bool = False,
    path: tuple[AstPathPart, ...] = (),
) -> bool:
    """Return whether accepted HTTP status evidence includes 401."""
    if node_local and _descends_into_child_node(path):
        return False
    normalized_keys = tuple(
        module_token_semantic_key(token) for token in HTTP_SUCCESS_STATUS_KEYS
    )
    if _is_json_object(value):
        for key, item in value.items():
            normalized_key = module_token_semantic_key(key)
            if _http_success_status_key(normalized_key, normalized_keys) and (
                _json_mentions_http_auth_error_status(item)
            ):
                return True
            if _json_has_http_auth_error_status_contract(
                item,
                node_local=node_local,
                path=(*path, key),
            ):
                return True
    if isinstance(value, list):
        return any(
            _json_has_http_auth_error_status_contract(
                item,
                node_local=node_local,
                path=(*path, index),
            )
            for index, item in enumerate(cast("list[object]", value))
        )
    return False


def _json_has_http_conflict_status_contract(
    value: object,
    *,
    node_local: bool = False,
    path: tuple[AstPathPart, ...] = (),
) -> bool:
    """Return whether accepted HTTP status evidence includes 409."""
    if node_local and _descends_into_child_node(path):
        return False
    normalized_keys = tuple(
        module_token_semantic_key(token) for token in HTTP_SUCCESS_STATUS_KEYS
    )
    if _is_json_object(value):
        for key, item in value.items():
            normalized_key = module_token_semantic_key(key)
            if _http_success_status_key(normalized_key, normalized_keys) and (
                _json_mentions_http_conflict_status(item)
            ):
                return True
            if _json_has_http_conflict_status_contract(
                item,
                node_local=node_local,
                path=(*path, key),
            ):
                return True
    if isinstance(value, list):
        return any(
            _json_has_http_conflict_status_contract(
                item,
                node_local=node_local,
                path=(*path, index),
            )
            for index, item in enumerate(cast("list[object]", value))
        )
    return False


def _json_has_http_rate_limit_status_contract(
    value: object,
    *,
    node_local: bool = False,
    path: tuple[AstPathPart, ...] = (),
) -> bool:
    """Return whether accepted HTTP status evidence includes 429."""
    if node_local and _descends_into_child_node(path):
        return False
    normalized_keys = tuple(
        module_token_semantic_key(token) for token in HTTP_SUCCESS_STATUS_KEYS
    )
    if _is_json_object(value):
        for key, item in value.items():
            normalized_key = module_token_semantic_key(key)
            if _http_success_status_key(normalized_key, normalized_keys) and (
                _json_mentions_http_rate_limit_status(item)
            ):
                return True
            if _json_has_http_rate_limit_status_contract(
                item,
                node_local=node_local,
                path=(*path, key),
            ):
                return True
    if isinstance(value, list):
        return any(
            _json_has_http_rate_limit_status_contract(
                item,
                node_local=node_local,
                path=(*path, index),
            )
            for index, item in enumerate(cast("list[object]", value))
        )
    return False


def _json_has_http_server_error_status_contract(
    value: object,
    *,
    node_local: bool = False,
    path: tuple[AstPathPart, ...] = (),
) -> bool:
    """Return whether accepted HTTP status evidence includes 5xx."""
    if node_local and _descends_into_child_node(path):
        return False
    normalized_keys = tuple(
        module_token_semantic_key(token) for token in HTTP_SUCCESS_STATUS_KEYS
    )
    if _is_json_object(value):
        for key, item in value.items():
            normalized_key = module_token_semantic_key(key)
            if _http_success_status_key(normalized_key, normalized_keys) and (
                _json_mentions_http_server_error_status(item)
            ):
                return True
            if _json_has_http_server_error_status_contract(
                item,
                node_local=node_local,
                path=(*path, key),
            ):
                return True
    if isinstance(value, list):
        return any(
            _json_has_http_server_error_status_contract(
                item,
                node_local=node_local,
                path=(*path, index),
            )
            for index, item in enumerate(cast("list[object]", value))
        )
    return False


def _http_success_status_key(
    normalized_key: str,
    normalized_keys: tuple[str, ...],
) -> bool:
    """Return if a normalized key denotes an HTTP success status contract."""
    return normalized_key in normalized_keys or (
        "status" in normalized_key
        and (
            "accepted" in normalized_key
            or "expected" in normalized_key
            or "ok" in normalized_key
            or "success" in normalized_key
            or "code" in normalized_key
        )
    )


def _json_mentions_http_empty_body_status(value: object) -> bool:
    """Return whether JSON-like data names an empty-body success status."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value in HTTP_EMPTY_BODY_STATUS_CODES
    if isinstance(value, float):
        return value.is_integer() and int(value) in HTTP_EMPTY_BODY_STATUS_CODES
    if isinstance(value, str):
        return _text_mentions_http_empty_body_status(value)
    if _is_json_object(value):
        return any(
            _json_mentions_http_empty_body_status(item)
            for item in value.values()
        )
    return isinstance(value, list) and any(
        _json_mentions_http_empty_body_status(item)
        for item in cast("list[object]", value)
    )


def _text_mentions_http_empty_body_status(value: str) -> bool:
    """Return whether text names an empty-body HTTP success status."""
    normalized_value = module_token_semantic_key(value)
    return any(
        module_token_semantic_key(token) in normalized_value
        for token in HTTP_EMPTY_BODY_STATUS_TOKENS
    )


def _json_mentions_http_auth_error_status(value: object) -> bool:
    """Return whether JSON-like data names an HTTP 401 status."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value in HTTP_AUTH_ERROR_STATUS_CODES
    if isinstance(value, float):
        return value.is_integer() and int(value) in HTTP_AUTH_ERROR_STATUS_CODES
    if isinstance(value, str):
        return _text_mentions_http_auth_error_status(value)
    if _is_json_object(value):
        return any(
            _json_mentions_http_auth_error_status(item)
            for item in value.values()
        )
    return isinstance(value, list) and any(
        _json_mentions_http_auth_error_status(item)
        for item in cast("list[object]", value)
    )


def _text_mentions_http_auth_error_status(value: str) -> bool:
    """Return whether text names an HTTP 401 status."""
    normalized_value = module_token_semantic_key(value)
    return any(
        module_token_semantic_key(token) in normalized_value
        for token in HTTP_AUTH_ERROR_STATUS_TOKENS
    )


def _json_mentions_http_not_found_status(value: object) -> bool:
    """Return whether JSON-like data names an HTTP 404 status."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value in HTTP_NOT_FOUND_STATUS_CODES
    if isinstance(value, float):
        return value.is_integer() and int(value) in HTTP_NOT_FOUND_STATUS_CODES
    if isinstance(value, str):
        return _text_mentions_http_not_found_status(value)
    if _is_json_object(value):
        return any(
            _json_mentions_http_not_found_status(item)
            for item in value.values()
        )
    return isinstance(value, list) and any(
        _json_mentions_http_not_found_status(item)
        for item in cast("list[object]", value)
    )


def _text_mentions_http_not_found_status(value: str) -> bool:
    """Return whether text names an HTTP 404 status."""
    normalized_value = module_token_semantic_key(value)
    return any(
        module_token_semantic_key(token) in normalized_value
        for token in HTTP_NOT_FOUND_STATUS_TOKENS
    )


def _json_mentions_http_conflict_status(value: object) -> bool:
    """Return whether JSON-like data names an HTTP 409 status."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value in HTTP_CONFLICT_STATUS_CODES
    if isinstance(value, float):
        return value.is_integer() and int(value) in HTTP_CONFLICT_STATUS_CODES
    if isinstance(value, str):
        return _text_mentions_http_conflict_status(value)
    if _is_json_object(value):
        return any(
            _json_mentions_http_conflict_status(item) for item in value.values()
        )
    return isinstance(value, list) and any(
        _json_mentions_http_conflict_status(item)
        for item in cast("list[object]", value)
    )


def _text_mentions_http_conflict_status(value: str) -> bool:
    """Return whether text names an HTTP 409 status."""
    normalized_value = module_token_semantic_key(value)
    return any(
        module_token_semantic_key(token) in normalized_value
        for token in HTTP_CONFLICT_STATUS_TOKENS
    )


def _json_mentions_http_rate_limit_status(value: object) -> bool:
    """Return whether JSON-like data names an HTTP 429 status."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value in HTTP_RATE_LIMIT_STATUS_CODES
    if isinstance(value, float):
        return value.is_integer() and int(value) in HTTP_RATE_LIMIT_STATUS_CODES
    if isinstance(value, str):
        return _text_mentions_http_rate_limit_status(value)
    if _is_json_object(value):
        return any(
            _json_mentions_http_rate_limit_status(item)
            for item in value.values()
        )
    return isinstance(value, list) and any(
        _json_mentions_http_rate_limit_status(item)
        for item in cast("list[object]", value)
    )


def _text_mentions_http_rate_limit_status(value: str) -> bool:
    """Return whether text names an HTTP 429 status."""
    normalized_value = module_token_semantic_key(value)
    return any(
        module_token_semantic_key(token) in normalized_value
        for token in HTTP_RATE_LIMIT_STATUS_TOKENS
    )


def _json_mentions_http_server_error_status(value: object) -> bool:
    """Return whether JSON-like data names an HTTP 5xx status."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value in HTTP_SERVER_ERROR_STATUS_CODES
    if isinstance(value, float):
        return (
            value.is_integer() and int(value) in HTTP_SERVER_ERROR_STATUS_CODES
        )
    if isinstance(value, str):
        return _text_mentions_http_server_error_status(value)
    if _is_json_object(value):
        return any(
            _json_mentions_http_server_error_status(item)
            for item in value.values()
        )
    return isinstance(value, list) and any(
        _json_mentions_http_server_error_status(item)
        for item in cast("list[object]", value)
    )


def _text_mentions_http_server_error_status(value: str) -> bool:
    """Return whether text names an HTTP 5xx status."""
    normalized_value = module_token_semantic_key(value)
    return any(
        module_token_semantic_key(token) in normalized_value
        for token in HTTP_SERVER_ERROR_STATUS_TOKENS
    )


def _json_has_http_permanent_error_retry_policy(
    value: object,
    *,
    node_local: bool = False,
    path: tuple[AstPathPart, ...] = (),
) -> bool:
    """Return whether JSON-like data retries permanent HTTP errors."""
    if node_local and _descends_into_child_node(path):
        return False
    if _is_json_object(value):
        for key, item in value.items():
            normalized_key = module_token_semantic_key(key)
            if _http_retry_policy_key(
                normalized_key
            ) and _json_mentions_http_permanent_error(item):
                return True
            if _json_has_http_permanent_error_retry_policy(
                item,
                node_local=node_local,
                path=(*path, key),
            ):
                return True
    if isinstance(value, list):
        return any(
            _json_has_http_permanent_error_retry_policy(
                item,
                node_local=node_local,
                path=(*path, index),
            )
            for index, item in enumerate(cast("list[object]", value))
        )
    return False


def _json_has_http_retry_policy(
    value: object,
    *,
    node_local: bool = False,
    path: tuple[AstPathPart, ...] = (),
) -> bool:
    """Return whether JSON-like data declares retry policy evidence."""
    if node_local and _descends_into_child_node(path):
        return False
    if _is_json_object(value):
        for key, item in value.items():
            normalized_key = module_token_semantic_key(key)
            if _http_retry_policy_key(normalized_key) and _has_evidence_value(
                item
            ):
                return True
            if _json_has_http_retry_policy(
                item,
                node_local=node_local,
                path=(*path, key),
            ):
                return True
    if isinstance(value, list):
        return any(
            _json_has_http_retry_policy(
                item,
                node_local=node_local,
                path=(*path, index),
            )
            for index, item in enumerate(cast("list[object]", value))
        )
    return False


def _http_retry_policy_key(normalized_key: str) -> bool:
    """Return whether a normalized key denotes retry-policy configuration."""
    return "retry" in normalized_key


def _json_mentions_http_permanent_error(value: object) -> bool:
    """Return whether JSON-like data names a permanent HTTP error."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value in HTTP_PERMANENT_ERROR_STATUS_CODES
    if isinstance(value, float):
        return (
            value.is_integer()
            and int(value) in HTTP_PERMANENT_ERROR_STATUS_CODES
        )
    if isinstance(value, str):
        return _text_mentions_http_permanent_error(value)
    if _is_json_object(value):
        return any(
            _json_mentions_http_permanent_error(item) for item in value.values()
        )
    return isinstance(value, list) and any(
        _json_mentions_http_permanent_error(item)
        for item in cast("list[object]", value)
    )


def _text_mentions_http_permanent_error(value: str) -> bool:
    """Return whether text names a permanent HTTP error."""
    normalized_value = module_token_semantic_key(value)
    return any(
        module_token_semantic_key(token) in normalized_value
        for token in HTTP_PERMANENT_ERROR_TOKENS
    )


def _json_mentions_http_success_status(value: object) -> bool:
    """Return whether JSON-like data names a 2xx HTTP success status."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return _http_status_is_success(value)
    if isinstance(value, float):
        return value.is_integer() and _http_status_is_success(int(value))
    if isinstance(value, str):
        return _text_mentions_http_success_status(value)
    if _is_json_object(value):
        return any(
            _json_mentions_http_success_status(item) for item in value.values()
        )
    return isinstance(value, list) and any(
        _json_mentions_http_success_status(item)
        for item in cast("list[object]", value)
    )


def _text_mentions_http_success_status(value: str) -> bool:
    """Return whether text names an HTTP success status or 2xx range."""
    return any(
        token in {"OK", "SUCCESS", "SUCCESSFUL", "2XX"}
        or (token.isdigit() and _http_status_is_success(int(token)))
        for token in _word_tokens(value)
    )


def _http_status_is_success(status_code: int) -> bool:
    """Return if an integer status code is in the HTTP 2xx success range."""
    return HTTP_SUCCESS_STATUS_MIN <= status_code <= HTTP_SUCCESS_STATUS_MAX


def _json_has_http_method_guard(
    value: object,
    *,
    node_local: bool = False,
    path: tuple[AstPathPart, ...] = (),
) -> bool:
    """Return whether JSON-like data declares accepted HTTP method evidence."""
    if node_local and _descends_into_child_node(path):
        return False
    normalized_keys = tuple(
        module_token_semantic_key(token) for token in WEBHOOK_METHOD_GUARD_KEYS
    )
    if _is_json_object(value):
        for key, item in value.items():
            normalized_key = module_token_semantic_key(key)
            if normalized_key in normalized_keys and _json_mentions_http_method(
                item
            ):
                return True
            if _json_has_http_method_guard(
                item,
                node_local=node_local,
                path=(*path, key),
            ):
                return True
    if isinstance(value, list):
        return any(
            _json_has_http_method_guard(
                item,
                node_local=node_local,
                path=(*path, index),
            )
            for index, item in enumerate(cast("list[object]", value))
        )
    return False


def _json_mentions_http_method(value: object) -> bool:
    """Return whether JSON-like data names at least one HTTP method."""
    if isinstance(value, str):
        return any(
            token in WEBHOOK_HTTP_METHOD_VALUES for token in _word_tokens(value)
        )
    if _is_json_object(value):
        return any(_json_mentions_http_method(item) for item in value.values())
    if isinstance(value, list):
        return any(
            _json_mentions_http_method(item)
            for item in cast("list[object]", value)
        )
    return False


def _word_tokens(value: str) -> tuple[str, ...]:
    """Return upper-case alphanumeric word tokens from text."""
    normalized = "".join(
        character if character.isalnum() else " " for character in value
    )
    return tuple(part.upper() for part in normalized.split())


def _truthy_json(value: object) -> bool:
    """Return whether a JSON configuration value is meaningfully enabled."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        return module_token_semantic_key(value) not in {
            "",
            "false ",
            "no ",
            "none ",
            "off ",
            "0",
        }
    if isinstance(value, dict):
        return bool(cast("dict[object, object]", value))
    if isinstance(value, list):
        return bool(cast("list[object]", value))
    return value is not None


def _falsey_json(value: object) -> bool:
    """Return if a JSON configuration value explicitly disables a setting."""
    if isinstance(value, bool):
        return not value
    if isinstance(value, int | float):
        return value == 0
    if isinstance(value, str):
        return module_token_semantic_key(value) in {
            "false ",
            "no ",
            "none ",
            "off ",
            "0",
        }
    return False


def _has_evidence_value(value: object) -> bool:
    """Return whether a token-bearing key carries meaningful evidence."""
    if isinstance(value, dict):
        return any(
            _has_evidence_value(item)
            for item in cast("dict[object, object]", value).values()
        )
    if isinstance(value, list):
        return any(
            _has_evidence_value(item) for item in cast("list[object]", value)
        )
    return _truthy_json(value)


def _json_text_blob(
    value: object,
    *,
    node_local: bool = False,
    path: tuple[AstPathPart, ...] = (),
) -> str:
    """Return lower-case text recursively from JSON-like values."""
    if node_local and _descends_into_child_node(path):
        return ""
    if isinstance(value, str):
        return value.casefold()
    if _is_json_object(value):
        return " ".join(
            _json_text_blob(item, node_local=node_local, path=(*path, key))
            for key, item in value.items()
        )
    if isinstance(value, list):
        return " ".join(
            _json_text_blob(item, node_local=node_local, path=(*path, index))
            for index, item in enumerate(cast("list[object]", value))
        )
    if value is None:
        return ""
    return str(value).casefold()


def _descends_into_child_node(path: tuple[AstPathPart, ...]) -> bool:
    """Return whether a node-local scan path enters a nested child node."""
    string_parts = tuple(part for part in path if isinstance(part, str))
    if any(part in DIRECT_ERROR_KEYS for part in string_parts):
        return True
    return any(
        _has_flow_after_child_container(string_parts, child_key)
        for child_key in CHILD_FLOW_CONTAINER_KEYS
    )


def _has_flow_after_child_container(
    path: tuple[str, ...], child_key: str
) -> bool:
    """Return whether a route-like container path enters a child flow node."""
    if child_key not in path:
        return False
    child_index = path.index(child_key)
    return "flow" in path[child_index + 1 :]


def _trigger_like(
    *,
    node: MakeAstNode,
    resolution: MakeAstModuleResolution | None,
) -> bool:
    """Return whether a node is a scenario trigger."""
    module_kind = resolution.module_kind if resolution is not None else None
    return module_looks_like_trigger(node.module_token, module_kind=module_kind)


def _has_integer_coordinates(value: JsonObject) -> bool:
    """Return whether designer coordinates are real integers."""
    x = value.get("x")
    y = value.get("y")
    return (
        isinstance(x, int)
        and not isinstance(x, bool)
        and isinstance(y, int)
        and not isinstance(y, bool)
    )


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    """Return whether a value is a string-keyed JSON object."""
    if not isinstance(value, dict):
        return False
    raw_mapping = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in raw_mapping)


def _catalog_modules_by_id(
    catalog: CatalogSnapshot,
) -> dict[str, CatalogModule]:
    """Return catalog modules by stable module ID."""
    return {
        module.module_id: module
        for app in catalog.apps
        for version in app.versions
        for module in version.modules
    }


def _resolved_module(
    *,
    resolution: MakeAstModuleResolution,
    modules_by_id: dict[str, CatalogModule],
) -> CatalogModule | None:
    """Return the catalog module for a resolved binding."""
    if resolution.catalog_module_id is None:
        return None
    return modules_by_id.get(resolution.catalog_module_id)


def _unresolved_module_finding(
    *,
    resolution: MakeAstModuleResolution,
    node: MakeAstNode,
) -> BlueprintValidationFinding:
    """Return a blocking unresolved-module finding."""
    issues = ", ".join(resolution.issues) or "unknown"
    internal_message = " ".join(
        (
            f"Node {node.node_id} token {resolution.module_token!r}",
            f"is unresolved with issues: {issues}.",
        )
    )
    return build_validation_finding(
        code="module.unresolved",
        severity="error",
        node=(node.node_id, node.source_trace.path),
        catalog_module_id=None,
        messages=(
            "A module could not be matched to the Make catalog.",
            internal_message,
        ),
    )


def _missing_catalog_record_finding(
    *,
    resolution: MakeAstModuleResolution,
    node: MakeAstNode,
) -> BlueprintValidationFinding:
    """Return a finding for an internally inconsistent resolution report."""
    internal_message = " ".join(
        (
            f"Node {node.node_id} resolved to missing catalog module",
            f"{resolution.catalog_module_id!r}.",
        )
    )
    return build_validation_finding(
        code="module.catalog_record_missing",
        severity="error",
        node=(node.node_id, node.source_trace.path),
        catalog_module_id=resolution.catalog_module_id,
        messages=(
            "A module catalog record is missing.",
            internal_message,
        ),
    )


def _trigger_position_finding(node: MakeAstNode) -> BlueprintValidationFinding:
    """Return a finding for a top-level trigger in the wrong position."""
    return build_validation_finding(
        code="semantic.trigger_position_invalid",
        severity="error",
        node=(node.node_id, node.source_trace.path),
        catalog_module_id=None,
        messages=(
            "A scenario trigger must be the first top-level module.",
            (
                f"Trigger-like node {node.node_id} appears after another "
                f"top-level module."
            ),
        ),
    )


def _multiple_root_triggers_finding(
    root_triggers: list[MakeAstNode],
) -> BlueprintValidationFinding:
    """Return a finding for multiple top-level triggers."""
    trigger_list = ", ".join(sorted(node.node_id for node in root_triggers))
    return build_validation_finding(
        code="semantic.multiple_root_triggers",
        severity="error",
        node=(root_triggers[0].node_id, root_triggers[0].source_trace.path),
        catalog_module_id=None,
        messages=(
            "A scenario flow must contain at most one root trigger.",
            f"Top-level trigger-like nodes detected: {trigger_list}.",
        ),
    )


def _nested_trigger_finding(node: MakeAstNode) -> BlueprintValidationFinding:
    """Return a finding for a trigger inside a nested flow."""
    return build_validation_finding(
        code="semantic.nested_trigger",
        severity="error",
        node=(node.node_id, node.source_trace.path),
        catalog_module_id=None,
        messages=(
            "A trigger module cannot run inside a nested route or tool flow.",
            (
                f"Trigger-like node {node.node_id} appears in "
                f"{node.source_trace.container_kind}."
            ),
        ),
    )
