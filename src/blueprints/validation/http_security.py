# ruff: noqa: S105
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001046#repo.blueprint-validation.semantic-module-usage-rules
# - 001079#repo.make-linter.rule-intake-manual-gate
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Validate deterministic HTTP security hazards in Make blueprints.

Boundary contract:
- Owns: local HTTP URL, dynamic-host, chat webhook destination, header, and
static
  secret-literal findings.
- Must not: call external APIs, inspect live Make scenarios, or expose raw URLs.
- Allows: deterministic checks over already-parsed AST node configuration.
- Split when: private-network SSRF, redirect, GraphQL, or flow-sensitive secret
  rules need independent evidence models.
- Merge when: another validation slice owns these exact HTTP URL predicates.
"""

from __future__ import annotations

import re
from ipaddress import IPv4Address, IPv6Address, ip_network
from typing import TYPE_CHECKING, Final, TypeGuard, cast
from urllib.parse import parse_qsl, urlsplit

from blueprints.ast.module_roles import module_token_semantic_key
from blueprints.validation.expression_templates import (
    MakeExpressionTemplateParseError,
    iter_make_expression_templates,
)
from blueprints.validation.findings import build_validation_finding
from blueprints.validation.network_hosts import host_ip_candidates

if TYPE_CHECKING:
    from blueprints.ast.models import AstPathPart, JsonObject, MakeAstNode
    from blueprints.validation.models import BlueprintValidationFinding

HTTP_UNENCRYPTED_TRANSPORT_CODE: Final = "http.url_unencrypted_transport"
HTTP_BASIC_AUTH_URL_CREDENTIALS_CODE: Final = "http.basic_auth_url_credentials"
HTTP_SENSITIVE_QUERY_PARAMETER_CODE: Final = "http.sensitive_query_parameter"
HTTP_HEADER_CRLF_INJECTION_CODE: Final = "http.header_crlf_injection"
HTTP_DYNAMIC_HEADER_MAPPING_CODE: Final = "http.dynamic_header_mapping"
HTTP_PROXY_HEADER_TRUST_MISSING_CODE: Final = "http.proxy_header_trust_missing"
HTTP_HEADER_SECRET_MASKING_MISSING_CODE: Final = (
    "http.header_secret_masking_missing"
)
HTTP_STATIC_CREDENTIAL_LITERAL_CODE: Final = "http.static_secret_literal"
HTTP_DYNAMIC_URL_HOST_CODE: Final = "http.dynamic_url_host"
HTTP_QUERY_PARAMETER_ENCODING_MISSING_CODE: Final = (
    "http.query_parameter_encoding_missing"
)
HTTP_PATH_SEGMENT_ENCODING_MISSING_CODE: Final = (
    "http.path_segment_encoding_missing"
)
HTTP_TIMEOUT_POLICY_MISSING_CODE: Final = "http.timeout_policy_missing"
HTTP_LOCAL_UNTRUSTED_TIMEOUT_RETRY_MISSING_CODE: Final = (
    "http.local_untrusted_timeout_retry_missing"
)
HTTP_TLS_VERIFICATION_DISABLED_CODE: Final = "http.tls_verification_disabled"
HTTP_EXTERNAL_SENSITIVE_MAPPING_CODE: Final = "http.external_sensitive_mapping"
HTTP_DYNAMIC_CHAT_WEBHOOK_DESTINATION_CODE: Final = (
    "http.dynamic_chat_webhook_destination"
)
HTTP_PRIVATE_NETWORK_URL_CODE: Final = "http.private_network_url"
HTTP_EXTERNAL_API_ALLOWLIST_MISSING_CODE: Final = (
    "http.external_api_allowlist_missing"
)
HTTP_API_VERSION_PINNING_MISSING_CODE: Final = (
    "http.api_version_pinning_missing"
)
HTTP_COOKIE_PASSTHROUGH_HEADER_CODE: Final = "http.cookie_passthrough_header"
HTTP_URL_KEYS: Final[tuple[str, ...]] = ("url", "URL")
MAKE_MAPPING_MARKERS: Final[tuple[str, ...]] = ("{{", "}}")
URL_VALUE_ENCODING_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "encodeurl ",
        "encodeuricomponent ",
        "urlencode ",
        "urlencoded ",
        "urlencoding",
    )
)
HEADER_PATH_TOKENS: Final[frozenset[str]] = frozenset(("header", "headers"))
CRLF_INJECTION_MARKERS: Final[tuple[str, ...]] = ("\r", "\n", "%0d", "%0a")
HEADER_SANITIZER_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "crlfstrip ",
        "escapeheader ",
        "headerescape ",
        "replacecrlf ",
        "sanitizeheader ",
        "stripcrlf",
    )
)
PROXY_IDENTITY_HEADER_NAMES: Final[frozenset[str]] = frozenset(
    (
        "cfconnectingip ",
        "fastlyclientip ",
        "forwarded ",
        "trueclientip ",
        "xclientip ",
        "xclusterclientip ",
        "xforwardedfor ",
        "xrealip",
    )
)
PROXY_HEADER_UNTRUSTED_SOURCE_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "body ",
        "form ",
        "header ",
        "headers ",
        "input ",
        "payload ",
        "query ",
        "request ",
        "trigger ",
        "webhook",
    )
)
HTTP_PROXY_HEADER_TRUST_EVIDENCE_KEYS: Final[tuple[str, ...]] = (
    "client ip normalization ",
    "client ip trust policy ",
    "forwarded header trust ",
    "ingress proxy allowlist ",
    "ingress proxy verified ",
    "proxy header allowlist ",
    "proxy header normalization ",
    "proxy header trust policy ",
    "trusted proxy header policy ",
    "trusted proxy validation",
)
MIN_STATIC_LITERAL_LENGTH: Final = 8
SENSITIVE_QUERY_PARAMETER_KEYS: Final[frozenset[str]] = frozenset(
    (
        "accesskey ",
        "accesstoken ",
        "apikey ",
        "api_key ",
        "authorization ",
        "authtoken ",
        "bearer ",
        "clientsecret ",
        "client_secret ",
        "magiclink ",
        "magic_link ",
        "password ",
        "refresh ",
        "refreshtoken ",
        "refresh_token ",
        "resettoken ",
        "reset_token ",
        "secret ",
        "sessionid ",
        "session_id ",
        "signature ",
        "token",
    )
)
SECRET_FIELD_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "accesskey ",
        "accesstoken ",
        "auth ",
        "authentication ",
        "apikey ",
        "authorization ",
        "authtoken ",
        "bearer ",
        "clientsecret ",
        "cookie ",
        "password ",
        "privatekey ",
        "refreshtoken ",
        "resettoken ",
        "secret ",
        "sessionid ",
        "signature ",
        "token ",
        "xapikey",
    )
)
COOKIE_HEADER_NAMES: Final[frozenset[str]] = frozenset(("cookie",))
COOKIE_PASSTHROUGH_SOURCE_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "cookie ",
        "cookieheader ",
        "cookies ",
        "headercookie ",
        "requestcookie ",
        "requestcookies ",
        "sessioncookie ",
        "setcookie",
    )
)
SAFE_SECRET_PLACEHOLDER_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "changeme ",
        "dummy ",
        "example ",
        "placeholder ",
        "redacted ",
        "sample ",
        "secretplaceholder ",
        "yourapikey ",
        "yourtoken",
    )
)
HTTP_OUTBOUND_MAPPING_PATH_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "body ",
        "data ",
        "field ",
        "fields ",
        "form ",
        "header ",
        "headers ",
        "json ",
        "payload ",
        "query ",
        "record ",
        "row ",
        "url ",
        "value ",
        "values",
    )
)
CHAT_WEBHOOK_APP_TOKENS: Final[frozenset[str]] = frozenset(("discord", "slack"))
CHAT_WEBHOOK_DESTINATION_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "destinationwebhook ",
        "destinationwebhookurl ",
        "incomingwebhook ",
        "incomingwebhookurl ",
        "webhookdestination ",
        "webhookurl ",
        "webhookuri",
    )
)
CHAT_WEBHOOK_URL_FIELD_TOKENS: Final[frozenset[str]] = frozenset(("url", "uri"))
HTTP_TIMEOUT_POLICY_KEYS: Final[tuple[str, ...]] = (
    "connectiontimeout ",
    "networktimeout ",
    "readtimeout ",
    "requesttimeout ",
    "responsetimeout ",
    "timeout ",
    "timeoutms ",
    "timeoutpolicy ",
    "timeoutseconds",
)
HTTP_RETRY_POLICY_KEYS: Final[tuple[str, ...]] = (
    "backoff ",
    "exponential backoff ",
    "jitter ",
    "max attempts ",
    "maxattempts ",
    "retries ",
    "retry ",
    "retry attempts ",
    "retry policy ",
    "retryattempts ",
    "retrypolicy",
)
HTTP_TLS_VERIFICATION_FALSE_KEYS: Final[tuple[str, ...]] = (
    "certificate validation ",
    "cert validation ",
    "certvalidation ",
    "reject unauthorized ",
    "rejectunauthorized ",
    "ssl verify ",
    "sslverify ",
    "strict tls ",
    "stricttls ",
    "tls verify ",
    "tlsverify ",
    "validate certificate ",
    "validate certificates ",
    "verify ssl ",
    "verify tls ",
    "verifyssl",
)
HTTP_TLS_VERIFICATION_TRUE_DISABLE_KEYS: Final[tuple[str, ...]] = (
    "allow invalid certificates ",
    "allowinvalidcertificates ",
    "cert check disabled ",
    "certcheckdisabled ",
    "ignore certificate errors ",
    "ignorecertificateerrors ",
    "insecure skip verify ",
    "insecureskipverify ",
    "skip certificate validation ",
    "skipcertificatevalidation",
)
HTTP_DYNAMIC_HOST_ALLOWLIST_KEYS: Final[tuple[str, ...]] = (
    "allowed domains ",
    "allowed hosts ",
    "alloweddomains ",
    "allowedhosts ",
    "destination host allowlist ",
    "destinationhostallowlist ",
    "domain allowlist ",
    "domainallowlist ",
    "dynamic host allowlist ",
    "dynamichostallowlist ",
    "host allowlist ",
    "url host allowlist ",
    "urlhostallowlist",
)
HTTP_EXTERNAL_API_ALLOWLIST_KEYS: Final[tuple[str, ...]] = (
    "allowed domains ",
    "allowed hosts ",
    "approved api domains ",
    "approved domains ",
    "approved vendors ",
    "declared vendors ",
    "external api allowlist ",
    "host allowlist ",
    "vendor allowlist",
)
HTTP_API_VERSION_EVIDENCE_KEYS: Final[tuple[str, ...]] = (
    "api version ",
    "api-version ",
    "api_version ",
    "external api version ",
    "service api version ",
    "vendor api version ",
    "versioned api ",
    "x-api-version",
)
HTTP_API_VERSION_HEADER_NAMES: Final[frozenset[str]] = frozenset(
    (
        "accept ",
        "apiversion ",
        "xapiversion ",
        "xmsversion ",
        "stripeversion",
    )
)
HTTP_API_VERSION_QUERY_KEYS: Final[frozenset[str]] = frozenset(
    ("apiversion", "v", "version")
)
HTTP_API_VERSION_PATH_PATTERN: Final = re.compile(
    r"^v(?:\d+|\d{4}(?:[-_.]?\d{2}){0,2})(?:[-_.][A-Za-z0-9]+)?$",
    re.IGNORECASE,
)
PRODUCTION_PROFILE_KEYS: Final[tuple[str, ...]] = (
    "deployment ",
    "environment ",
    "env ",
    "profile ",
    "stage",
)
PRODUCTION_PROFILE_TOKENS: Final[tuple[str, ...]] = ("production",)
HTTP_HEADER_SECRET_MASKING_KEYS: Final[tuple[str, ...]] = (
    "header masking ",
    "headermasking ",
    "log redaction ",
    "logredaction ",
    "mask headers ",
    "masked headers ",
    "maskedheaders ",
    "maskheaders ",
    "redact headers ",
    "redacted headers ",
    "redactedheaders ",
    "redactheaders ",
    "secret header masking ",
    "secretheadermasking ",
    "sensitive header masking ",
    "sensitiveheadermasking",
)
PRIVATE_NETWORK_HOST_NAMES: Final[frozenset[str]] = frozenset(
    (
        "awslocal ",
        "localhost ",
        "localhostlocaldomain ",
        "metadata ",
        "metadatagoogleinternal ",
        "metadatainternal",
    )
)
PRIVATE_NETWORK_HOST_SUFFIXES: Final[tuple[str, ...]] = (
    ".cluster.local",
    ".internal",
    ".local",
    ".svc",
)
PRIVATE_NETWORK_IP_RANGES = tuple(
    ip_network(network)
    for network in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "224.0.0.0/4",
        "::/128",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
        "ff00::/8",
    )
)
SENSITIVE_MAPPING_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "accesskey ",
        "accesstoken ",
        "apikey ",
        "authorization ",
        "authtoken ",
        "bearer ",
        "clientsecret ",
        "cookie ",
        "email ",
        "password ",
        "phone ",
        "privatekey ",
        "refreshtoken ",
        "secret ",
        "sessionid ",
        "signature ",
        "ssn ",
        "token",
    )
)
SAFE_MAPPING_SOURCE_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "config ",
        "configuration ",
        "connection ",
        "connections ",
        "credential ",
        "credentials ",
        "environment ",
        "runtime ",
        "setting ",
        "settings",
    )
)
SECRET_VALUE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
    ),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
)


def validate_http_url_security(
    nodes: tuple[MakeAstNode, ...],
    *,
    scenario_metadata: JsonObject | None = None,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return deterministic HTTP URL security findings for Make HTTP nodes."""
    findings: list[BlueprintValidationFinding] = []
    root_metadata = _object_or_empty(scenario_metadata)
    for node in nodes:
        findings.extend(
            (
                build_validation_finding(
                    code=HTTP_DYNAMIC_CHAT_WEBHOOK_DESTINATION_CODE,
                    severity="warning",
                    node=(node.node_id, destination_path),
                    catalog_module_id=None,
                    messages=(
                        (
                            "Slack or Discord webhook destinations should "
                            "come from "
                            "fixed connection or configuration sources."
                        ),
                        (
                            f"Node {node.node_id} maps a dynamic value into "
                            f"a chat "
                            "webhook destination field; raw destination "
                            "text is redacted."
                        ),
                    ),
                )
            )
            for destination_path in _dynamic_chat_webhook_destination_paths(
                node
            )
        )
        if not _http_request_node(node):
            continue
        url_field = _node_text_field(node, HTTP_URL_KEYS)
        if url_field is None:
            continue
        url, source_path = url_field
        if _uses_external_plain_http(url):
            findings.append(
                build_validation_finding(
                    code=HTTP_UNENCRYPTED_TRANSPORT_CODE,
                    severity="error",
                    node=(node.node_id, source_path),
                    catalog_module_id=None,
                    messages=(
                        (
                            "An external HTTP request must use encrypted "
                            "transport."
                        ),
                        (
                            f"Node {node.node_id} configures an external "
                            f"http:// URL "
                            "without a localhost exception."
                        ),
                    ),
                )
            )
        if _contains_url_credentials(url):
            findings.append(
                build_validation_finding(
                    code=HTTP_BASIC_AUTH_URL_CREDENTIALS_CODE,
                    severity="error",
                    node=(node.node_id, source_path),
                    catalog_module_id=None,
                    messages=(
                        (
                            "HTTP credentials must not be embedded in the "
                            "request URL."
                        ),
                        (
                            f"Node {node.node_id} URL includes credentials "
                            f"before the host; "
                            "use a connection, auth header, or approved "
                            "auth setting."
                        ),
                    ),
                )
            )
        if _contains_sensitive_query_parameter(url):
            findings.append(
                build_validation_finding(
                    code=HTTP_SENSITIVE_QUERY_PARAMETER_CODE,
                    severity="warning",
                    node=(node.node_id, source_path),
                    catalog_module_id=None,
                    messages=(
                        (
                            "HTTP query strings should not carry "
                            "credential-style parameters."
                        ),
                        (
                            f"Node {node.node_id} URL query includes a "
                            f"sensitive "
                            "parameter key; raw query values are redacted."
                        ),
                    ),
                )
            )
        findings.extend(
            _query_parameter_encoding_findings(node, url, source_path)
        )
        findings.extend(_path_segment_encoding_findings(node, url, source_path))
        findings.extend(_timeout_policy_findings(node, url, source_path))
        findings.extend(
            _local_untrusted_timeout_retry_findings(node, url, source_path)
        )
        findings.extend(
            _tls_verification_disabled_findings(node, url, source_path)
        )
        if _targets_private_network(url):
            findings.append(
                build_validation_finding(
                    code=HTTP_PRIVATE_NETWORK_URL_CODE,
                    severity="warning",
                    node=(node.node_id, source_path),
                    catalog_module_id=None,
                    messages=(
                        (
                            "HTTP request URLs should not target private or "
                            "metadata "
                            "networks without an allowlist."
                        ),
                        (
                            f"Node {node.node_id} targets private, local, "
                            f"link-local, "
                            "multicast, or metadata network evidence; raw "
                            "URL text is "
                            "redacted."
                        ),
                    ),
                )
            )
        if _contains_dynamic_url_host(
            url
        ) and not _declares_http_dynamic_host_allowlist(node):
            findings.append(
                build_validation_finding(
                    code=HTTP_DYNAMIC_URL_HOST_CODE,
                    severity="warning",
                    node=(node.node_id, source_path),
                    catalog_module_id=None,
                    messages=(
                        (
                            "HTTP request URLs should keep the scheme and host "
                            "static or allowlisted."
                        ),
                        (
                            f"Node {node.node_id} URL has dynamic scheme or "
                            f"host evidence; "
                            "raw URL text is redacted."
                        ),
                    ),
                )
            )
        if _uses_static_external_http_target(url):
            findings.extend(
                _external_api_allowlist_findings(
                    node,
                    source_path,
                    scenario_metadata=root_metadata,
                )
            )
            findings.extend(
                _api_version_pinning_findings(
                    node,
                    url,
                    source_path,
                    scenario_metadata=root_metadata,
                )
            )
            findings.extend(
                (
                    build_validation_finding(
                        code=HTTP_EXTERNAL_SENSITIVE_MAPPING_CODE,
                        severity="warning",
                        node=(node.node_id, sensitive_path),
                        catalog_module_id=None,
                        messages=(
                            (
                                "External HTTP requests should not receive "
                                "sensitive mapped fields."
                            ),
                            (
                                f"Node {node.node_id} maps sensitive "
                                f"source-field evidence "
                                "into an external HTTP request; raw URL and "
                                "mapping text "
                                "are redacted."
                            ),
                        ),
                    )
                )
                for sensitive_path in _external_sensitive_mapping_paths(node)
            )
        findings.extend(
            (
                build_validation_finding(
                    code=HTTP_HEADER_CRLF_INJECTION_CODE,
                    severity="error",
                    node=(node.node_id, header_path),
                    catalog_module_id=None,
                    messages=(
                        (
                            "HTTP header values must not contain line-break "
                            "injection markers."
                        ),
                        (
                            f"Node {node.node_id} header configuration "
                            f"contains CRLF "
                            "injection evidence; raw header values are "
                            "redacted."
                        ),
                    ),
                )
            )
            for header_path in _header_crlf_injection_paths(node)
        )
        findings.extend(
            (
                build_validation_finding(
                    code=HTTP_DYNAMIC_HEADER_MAPPING_CODE,
                    severity="warning",
                    node=(node.node_id, header_path),
                    catalog_module_id=None,
                    messages=(
                        (
                            "HTTP header mappings should show header "
                            "sanitization evidence."
                        ),
                        (
                            f"Node {node.node_id} maps dynamic values into "
                            f"HTTP headers "
                            "without visible header sanitization; raw "
                            "header values are "
                            "redacted."
                        ),
                    ),
                )
            )
            for header_path in _dynamic_header_mapping_paths(node)
        )
        findings.extend(
            (
                build_validation_finding(
                    code=HTTP_PROXY_HEADER_TRUST_MISSING_CODE,
                    severity="warning",
                    node=(node.node_id, header_path),
                    catalog_module_id=None,
                    messages=(
                        (
                            "Proxy identity headers should show trusted-proxy "
                            "normalization evidence before forwarding "
                            "inbound values."
                        ),
                        (
                            f"Node {node.node_id} maps inbound-looking data "
                            f"into a "
                            "proxy or client-IP header without local "
                            "trust-policy "
                            "evidence; raw header values are redacted."
                        ),
                    ),
                )
            )
            for header_path in _proxy_header_trust_missing_paths(
                node,
                scenario_metadata=root_metadata,
            )
        )
        findings.extend(
            (
                build_validation_finding(
                    code=HTTP_HEADER_SECRET_MASKING_MISSING_CODE,
                    severity="warning",
                    node=(node.node_id, header_path),
                    catalog_module_id=None,
                    messages=(
                        (
                            "Secret-scoped HTTP headers should declare log "
                            "masking evidence."
                        ),
                        (
                            f"Node {node.node_id} maps a secret-scoped HTTP "
                            f"header "
                            "without visible masking evidence; raw header "
                            "values are "
                            "redacted."
                        ),
                    ),
                )
            )
            for header_path in _secret_header_masking_missing_paths(node)
        )
        findings.extend(
            (
                build_validation_finding(
                    code=HTTP_COOKIE_PASSTHROUGH_HEADER_CODE,
                    severity="warning",
                    node=(node.node_id, header_path),
                    catalog_module_id=None,
                    messages=(
                        (
                            "HTTP requests should not forward inbound "
                            "cookies as outbound "
                            "Cookie headers."
                        ),
                        (
                            f"Node {node.node_id} maps cookie-like source "
                            f"evidence into "
                            "an HTTP Cookie header; raw header values are "
                            "redacted."
                        ),
                    ),
                )
            )
            for header_path in _cookie_passthrough_header_paths(node)
        )
        findings.extend(
            (
                build_validation_finding(
                    code=HTTP_STATIC_CREDENTIAL_LITERAL_CODE,
                    severity="error",
                    node=(node.node_id, secret_path),
                    catalog_module_id=None,
                    messages=(
                        (
                            "HTTP request configuration must not contain "
                            "static "
                            ""
                            "secret values."
                        ),
                        (
                            f"Node {node.node_id} contains a static "
                            f"secret-like literal "
                            "in HTTP configuration; raw values are redacted."
                        ),
                    ),
                )
            )
            for secret_path in _static_secret_literal_paths(node)
        )
    return tuple(findings)


def _query_parameter_encoding_findings(
    node: MakeAstNode,
    url: str,
    source_path: tuple[AstPathPart, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Return query-encoding findings for one HTTP URL."""
    if not _contains_unencoded_dynamic_query_value(url):
        return ()
    return (
        build_validation_finding(
            code=HTTP_QUERY_PARAMETER_ENCODING_MISSING_CODE,
            severity="warning",
            node=(node.node_id, source_path),
            catalog_module_id=None,
            messages=(
                "HTTP dynamic query parameter values should be URL encoded.",
                (
                    f"Node {node.node_id} URL query maps a dynamic value "
                    f"without "
                    "visible URL-encoding evidence; raw query values are "
                    "redacted."
                ),
            ),
        ),
    )


def _path_segment_encoding_findings(
    node: MakeAstNode,
    url: str,
    source_path: tuple[AstPathPart, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Return path-segment encoding findings for one HTTP URL."""
    if not _contains_unencoded_dynamic_path_segment(url):
        return ()
    return (
        build_validation_finding(
            code=HTTP_PATH_SEGMENT_ENCODING_MISSING_CODE,
            severity="warning",
            node=(node.node_id, source_path),
            catalog_module_id=None,
            messages=(
                "HTTP dynamic path segments should be URL encoded.",
                (
                    f"Node {node.node_id} URL path maps a dynamic value "
                    f"without "
                    "visible URL-encoding evidence; raw URL text is redacted."
                ),
            ),
        ),
    )


def _timeout_policy_findings(
    node: MakeAstNode,
    url: str,
    source_path: tuple[AstPathPart, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Return timeout-policy findings for one HTTP URL."""
    if not _uses_static_external_http_target(
        url
    ) or _declares_http_timeout_policy(node):
        return ()
    return (
        build_validation_finding(
            code=HTTP_TIMEOUT_POLICY_MISSING_CODE,
            severity="warning",
            node=(node.node_id, source_path),
            catalog_module_id=None,
            messages=(
                (
                    "External HTTP requests should declare timeout policy "
                    "evidence."
                ),
                (
                    f"Node {node.node_id} targets a static non-local HTTP "
                    f"endpoint "
                    "without local timeout or timeout-policy evidence; raw "
                    "URL text "
                    "is redacted."
                ),
            ),
        ),
    )


def _local_untrusted_timeout_retry_findings(
    node: MakeAstNode,
    url: str,
    source_path: tuple[AstPathPart, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Return timeout/retry findings for local or private API targets."""
    if not _targets_local_or_private_network(url) or (
        _declares_http_timeout_policy(node)
        and _declares_http_retry_policy(node)
    ):
        return ()
    return (
        build_validation_finding(
            code=HTTP_LOCAL_UNTRUSTED_TIMEOUT_RETRY_MISSING_CODE,
            severity="warning",
            node=(node.node_id, source_path),
            catalog_module_id=None,
            messages=(
                (
                    "Local or private HTTP API calls should declare timeout "
                    "and "
                    ""
                    "retry policy evidence."
                ),
                (
                    f"Node {node.node_id} targets local or private network "
                    f"evidence "
                    "without both local timeout and retry-policy evidence; "
                    "raw URL "
                    "text is redacted."
                ),
            ),
        ),
    )


def _tls_verification_disabled_findings(
    node: MakeAstNode,
    url: str,
    source_path: tuple[AstPathPart, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Return TLS verification findings for explicit insecure certificate.

    posture.
    """
    if not _uses_static_https_target(
        url
    ) or not _declares_tls_verification_disabled(node):
        return ()
    return (
        build_validation_finding(
            code=HTTP_TLS_VERIFICATION_DISABLED_CODE,
            severity="error",
            node=(node.node_id, source_path),
            catalog_module_id=None,
            messages=(
                "HTTP requests must not disable TLS certificate verification.",
                (
                    f"Node {node.node_id} targets a static HTTPS endpoint "
                    f"while "
                    "declaring disabled TLS certificate verification; raw "
                    "URL and "
                    "certificate settings are redacted."
                ),
            ),
        ),
    )


def _external_api_allowlist_findings(
    node: MakeAstNode,
    source_path: tuple[AstPathPart, ...],
    *,
    scenario_metadata: JsonObject,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return production external API allowlist findings for one HTTP node."""
    if not _requires_external_api_allowlist(
        node,
        scenario_metadata=scenario_metadata,
    ) or _declares_http_external_api_allowlist(
        node,
        scenario_metadata=scenario_metadata,
    ):
        return ()
    return (
        build_validation_finding(
            code=HTTP_EXTERNAL_API_ALLOWLIST_MISSING_CODE,
            severity="warning",
            node=(node.node_id, source_path),
            catalog_module_id=None,
            messages=(
                (
                    "Production HTTP requests should declare approved external "
                    "API domains or vendors."
                ),
                (
                    f"Node {node.node_id} targets a static external API in a "
                    "production-scoped scenario without local approved-domain "
                    "or vendor evidence; raw URL text is redacted."
                ),
            ),
        ),
    )


def _api_version_pinning_findings(
    node: MakeAstNode,
    url: str,
    source_path: tuple[AstPathPart, ...],
    *,
    scenario_metadata: JsonObject,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return production external API version-pinning findings for one HTTP.

    node.
    """
    if (
        not _requires_external_api_allowlist(
            node, scenario_metadata=scenario_metadata
        )
        or not _static_target_looks_like_api(url)
        or _declares_http_api_version_evidence(
            node,
            url,
            scenario_metadata=scenario_metadata,
        )
    ):
        return ()
    return (
        build_validation_finding(
            code=HTTP_API_VERSION_PINNING_MISSING_CODE,
            severity="warning",
            node=(node.node_id, source_path),
            catalog_module_id=None,
            messages=(
                (
                    "Production external API calls should declare API version "
                    "evidence."
                ),
                (
                    f"Node {node.node_id} targets a static production "
                    f"API-shaped "
                    "endpoint without URL, header, or metadata version "
                    "evidence; "
                    "raw URL and header text are redacted."
                ),
            ),
        ),
    )


def _http_request_node(node: MakeAstNode) -> bool:
    """Return whether one node is an HTTP request module."""
    token_key = module_token_semantic_key(node.module_token)
    return (
        node.kind == "http_api"
        or "makerequest" in token_key
        or token_key.startswith("http")
    )


def _node_text_field(
    node: MakeAstNode,
    keys: tuple[str, ...],
) -> tuple[str, tuple[AstPathPart, ...]] | None:
    """Return one configured text field and its AST path without child-node.

    descent.
    """
    for container_key in ("parameters", "mapper"):
        container = _object_or_empty(node.raw_payload.get(container_key))
        for key in keys:
            value = container.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip(), (
                    *node.source_trace.path,
                    container_key,
                    key,
                )
    return None


def _uses_external_plain_http(url: str) -> bool:
    """Return whether a URL uses unencrypted external HTTP transport."""
    parts = urlsplit(url)
    return parts.scheme.casefold() == "http" and not _is_local_http_url(
        parts.hostname
    )


def _is_local_http_url(hostname: str | None) -> bool:
    """Return if an unencrypted HTTP host is a local development endpoint."""
    if hostname is None:
        return False
    normalized = hostname.casefold().strip("[]").rstrip(".")
    if normalized == "localhost":
        return True
    return any(
        candidate.is_loopback for candidate in host_ip_candidates(normalized)
    )


def _uses_static_external_http_target(url: str) -> bool:
    """Return whether a URL has a static external HTTP(S) target."""
    if _contains_make_mapping(url):
        parts = urlsplit(url)
        scheme_and_authority = f"{parts.scheme}://{parts.netloc}"
        if _contains_make_mapping(scheme_and_authority):
            return False
    parts = urlsplit(url)
    return parts.scheme.casefold() in {
        "http ",
        "https",
    } and not _is_local_http_url(parts.hostname)


def _uses_static_https_target(url: str) -> bool:
    """Return whether a URL has a static non-local HTTPS target."""
    if not _uses_static_external_http_target(url):
        return False
    return urlsplit(url).scheme.casefold() == "https"


def _declares_http_timeout_policy(node: MakeAstNode) -> bool:
    """Return if an HTTP node declares timeout or timeout-policy evidence."""
    for container_key in ("parameters", "mapper", "metadata"):
        container = _object_or_empty(node.raw_payload.get(container_key))
        if _json_has_evidence_key_token(
            container, tokens=HTTP_TIMEOUT_POLICY_KEYS
        ):
            return True
    return False


def _declares_http_retry_policy(node: MakeAstNode) -> bool:
    """Return whether an HTTP node declares retry or backoff policy evidence."""
    for container_key in ("parameters", "mapper", "metadata"):
        container = _object_or_empty(node.raw_payload.get(container_key))
        if _json_has_evidence_key_token(
            container, tokens=HTTP_RETRY_POLICY_KEYS
        ):
            return True
    return False


def _declares_tls_verification_disabled(node: MakeAstNode) -> bool:
    """Return whether an HTTP node disables TLS certificate verification."""
    for container_key in ("parameters", "mapper", "metadata"):
        container = _object_or_empty(node.raw_payload.get(container_key))
        if _json_has_tls_verification_disabled(container):
            return True
    return False


def _declares_http_dynamic_host_allowlist(node: MakeAstNode) -> bool:
    """Return whether an HTTP node declares dynamic-host allowlist evidence."""
    for container_key in ("parameters", "mapper", "metadata"):
        container = _object_or_empty(node.raw_payload.get(container_key))
        if _json_has_evidence_key_token(
            container, tokens=HTTP_DYNAMIC_HOST_ALLOWLIST_KEYS
        ):
            return True
    return False


def _requires_external_api_allowlist(
    node: MakeAstNode,
    *,
    scenario_metadata: JsonObject,
) -> bool:
    """Return whether production evidence requires an external API allowlist."""
    if _json_has_production_profile(scenario_metadata):
        return True
    for container_key in ("parameters", "mapper", "metadata"):
        container = _object_or_empty(node.raw_payload.get(container_key))
        if _json_has_production_profile(container):
            return True
    return False


def _declares_http_external_api_allowlist(
    node: MakeAstNode,
    *,
    scenario_metadata: JsonObject,
) -> bool:
    """Return if external API domain or vendor allowlist evidence exists."""
    if _json_has_evidence_key_token(
        scenario_metadata, tokens=HTTP_EXTERNAL_API_ALLOWLIST_KEYS
    ):
        return True
    for container_key in ("parameters", "mapper", "metadata"):
        container = _object_or_empty(node.raw_payload.get(container_key))
        if _json_has_evidence_key_token(
            container, tokens=HTTP_EXTERNAL_API_ALLOWLIST_KEYS
        ):
            return True
    return False


def _declares_http_api_version_evidence(
    node: MakeAstNode,
    url: str,
    *,
    scenario_metadata: JsonObject,
) -> bool:
    """Return whether the HTTP call shows local API version-pinning evidence."""
    if _url_has_api_version_evidence(url):
        return True
    if _json_has_evidence_key_token(
        scenario_metadata,
        tokens=HTTP_API_VERSION_EVIDENCE_KEYS,
    ):
        return True
    for container_key in ("parameters", "mapper", "metadata"):
        container = _object_or_empty(node.raw_payload.get(container_key))
        if _json_has_evidence_key_token(
            container, tokens=HTTP_API_VERSION_EVIDENCE_KEYS
        ):
            return True
        if _json_has_api_version_header_evidence(container):
            return True
    return False


def _declares_http_header_secret_masking(node: MakeAstNode) -> bool:
    """Return whether an HTTP node declares header secret-masking evidence."""
    for container_key in ("parameters", "mapper", "metadata"):
        container = _object_or_empty(node.raw_payload.get(container_key))
        if _json_has_evidence_key_token(
            container, tokens=HTTP_HEADER_SECRET_MASKING_KEYS
        ):
            return True
    return False


def _declares_http_proxy_header_trust_evidence(
    node: MakeAstNode,
    *,
    scenario_metadata: JsonObject,
) -> bool:
    """Return whether local config declares trusted proxy-header normalization.

    evidence.
    """
    if _json_has_evidence_key_token(
        scenario_metadata,
        tokens=HTTP_PROXY_HEADER_TRUST_EVIDENCE_KEYS,
    ):
        return True
    for container_key in ("parameters", "mapper", "metadata"):
        container = _object_or_empty(node.raw_payload.get(container_key))
        if _json_has_evidence_key_token(
            container,
            tokens=HTTP_PROXY_HEADER_TRUST_EVIDENCE_KEYS,
        ):
            return True
    return False


def _contains_url_credentials(url: str) -> bool:
    """Return whether the URL embeds credentials before the host."""
    parts = urlsplit(url)
    return parts.username is not None or parts.password is not None


def _contains_sensitive_query_parameter(url: str) -> bool:
    """Return whether the URL query uses credential-style parameter keys."""
    query = urlsplit(url).query
    if not query:
        return False
    return any(
        _sensitive_query_parameter_key(key)
        for key, _value in parse_qsl(query, keep_blank_values=True)
    )


def _static_target_looks_like_api(url: str) -> bool:
    """Return whether one static external URL names an API-shaped target."""
    parts = urlsplit(url)
    host_labels = tuple((parts.hostname or "").split("."))
    path_segments = tuple(
        module_token_semantic_key(segment)
        for segment in parts.path.split("/")
        if segment
    )
    return (
        any(_host_label_looks_like_api(label) for label in host_labels)
        or "api" in path_segments
        or any(segment.startswith("api") for segment in path_segments)
    )


def _host_label_looks_like_api(label: str) -> bool:
    """Return whether one host label visibly denotes an API endpoint."""
    normalized = module_token_semantic_key(label)
    return normalized == "api" or normalized.startswith("api")


def _url_has_api_version_evidence(url: str) -> bool:
    """Return whether URL path or query visibly pins an API version."""
    parts = urlsplit(url)
    if any(
        _path_segment_is_api_version(segment)
        for segment in parts.path.split("/")
    ):
        return True
    return any(
        module_token_semantic_key(key) in HTTP_API_VERSION_QUERY_KEYS
        and _truthy_json(value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
    )


def _path_segment_is_api_version(segment: str) -> bool:
    """Return whether one path segment is a visible API-version marker."""
    stripped = segment.strip()
    return bool(stripped and HTTP_API_VERSION_PATH_PATTERN.match(stripped))


def _contains_unencoded_dynamic_query_value(url: str) -> bool:
    """Return whether a URL query value maps dynamic data without encoding.

    evidence.
    """
    query = urlsplit(url).query
    if not query:
        return False
    return any(
        _query_value_needs_encoding(value) for value in _raw_query_values(query)
    )


def _contains_unencoded_dynamic_path_segment(url: str) -> bool:
    """Return whether a URL path segment maps dynamic data without encoding.

    evidence.
    """
    path = urlsplit(url).path
    if not path:
        return False
    return any(
        _path_segment_needs_encoding(segment) for segment in path.split("/")
    )


def _path_segment_needs_encoding(segment: str) -> bool:
    """Return whether one path segment contains an unencoded Make mapping."""
    return _contains_make_mapping(
        segment
    ) and not _value_has_url_encoding_evidence(segment)


def _raw_query_values(query: str) -> tuple[str, ...]:
    """Return raw query parameter values without URL-decoding them."""
    values: list[str] = []
    for part in query.split("&"):
        if not part:
            continue
        _key, separator, value = part.partition("=")
        if separator:
            values.append(value)
    return tuple(values)


def _query_value_needs_encoding(value: str) -> bool:
    """Return whether one query value contains an unencoded Make mapping."""
    return _contains_make_mapping(
        value
    ) and not _value_has_url_encoding_evidence(value)


def _value_has_url_encoding_evidence(value: str) -> bool:
    """Return whether one URL value visibly applies URL encoding."""
    normalized = module_token_semantic_key(value)
    return any(token in normalized for token in URL_VALUE_ENCODING_TOKENS)


def _targets_private_network(url: str) -> bool:
    """Return if a URL targets a private, local, or metadata network host."""
    parts = urlsplit(url)
    if parts.scheme.casefold() not in {"http", "https"}:
        return False
    host = parts.hostname
    if host is None or _contains_make_mapping(host):
        return False
    return _private_network_host(host)


def _targets_local_or_private_network(url: str) -> bool:
    """Return whether a URL targets a local hostname or private network host."""
    parts = urlsplit(url)
    if parts.scheme.casefold() not in {"http", "https"}:
        return False
    return _is_local_http_url(parts.hostname) or _targets_private_network(url)


def _private_network_host(host: str) -> bool:
    """Return if one host names private, local, or metadata infrastructure."""
    normalized = host.casefold().strip("[]").rstrip(".")
    key = module_token_semantic_key(normalized)
    if key in PRIVATE_NETWORK_HOST_NAMES or normalized.endswith(
        PRIVATE_NETWORK_HOST_SUFFIXES
    ):
        return True
    host_ips = host_ip_candidates(normalized)
    return any(_private_network_ip(ip) for ip in host_ips)


def _private_network_ip(ip: IPv4Address | IPv6Address) -> bool:
    """Return whether one parsed address belongs to a private network range."""
    return any(ip in network for network in PRIVATE_NETWORK_IP_RANGES)


def _contains_dynamic_url_host(url: str) -> bool:
    """Return if a URL lacks a static scheme and host while using mappings."""
    if not _contains_make_mapping(url):
        return False
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc or parts.hostname is None:
        return True
    scheme_and_authority = f"{parts.scheme}://{parts.netloc}"
    return _contains_make_mapping(scheme_and_authority)


def _sensitive_query_parameter_key(key: str) -> bool:
    """Return whether one query parameter key appears to carry credentials."""
    normalized = module_token_semantic_key(key)
    return normalized in SENSITIVE_QUERY_PARAMETER_KEYS


def _header_crlf_injection_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return header value paths that contain CRLF injection evidence."""
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in ("parameters", "mapper"):
        container = _object_or_empty(node.raw_payload.get(container_key))
        paths.extend(
            _json_header_crlf_paths(
                container,
                path=(*node.source_trace.path, container_key),
            )
        )
    return tuple(paths)


def _dynamic_header_mapping_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return header value paths that map dynamic values without sanitizer.

    evidence.
    """
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in ("parameters", "mapper"):
        container = _object_or_empty(node.raw_payload.get(container_key))
        paths.extend(
            _json_dynamic_header_mapping_paths(
                container,
                path=(*node.source_trace.path, container_key),
            )
        )
    return tuple(paths)


def _proxy_header_trust_missing_paths(
    node: MakeAstNode,
    *,
    scenario_metadata: JsonObject,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return proxy identity header paths mapped from inbound-like sources."""
    if _declares_http_proxy_header_trust_evidence(
        node,
        scenario_metadata=scenario_metadata,
    ):
        return ()
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in ("parameters", "mapper"):
        container = _object_or_empty(node.raw_payload.get(container_key))
        paths.extend(
            _json_proxy_header_mapping_paths(
                container,
                path=(*node.source_trace.path, container_key),
            )
        )
    return tuple(paths)


def _static_secret_literal_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return the computed result for the caller."""
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in ("parameters", "mapper"):
        container = _object_or_empty(node.raw_payload.get(container_key))
        paths.extend(
            _json_static_secret_literal_paths(
                container,
                path=(*node.source_trace.path, container_key),
            )
        )
    return tuple(paths)


def _secret_header_masking_missing_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return mapped secret-scoped header paths lacking masking evidence."""
    if _declares_http_header_secret_masking(node):
        return ()
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in ("parameters", "mapper"):
        container = _object_or_empty(node.raw_payload.get(container_key))
        paths.extend(
            _json_mapped_secret_header_paths(
                container,
                path=(*node.source_trace.path, container_key),
            )
        )
    return tuple(paths)


def _cookie_passthrough_header_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return Cookie header paths mapped from cookie-like source fields."""
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in ("parameters", "mapper"):
        container = _object_or_empty(node.raw_payload.get(container_key))
        paths.extend(
            _json_cookie_passthrough_header_paths(
                container,
                path=(*node.source_trace.path, container_key),
            )
        )
    return tuple(paths)


def _external_sensitive_mapping_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return outbound HTTP paths that map sensitive source fields."""
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in ("parameters", "mapper"):
        container = _object_or_empty(node.raw_payload.get(container_key))
        paths.extend(
            _json_sensitive_mapping_paths(
                container,
                path=(*node.source_trace.path, container_key),
            )
        )
    return tuple(paths)


def _dynamic_chat_webhook_destination_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return chat webhook destination paths mapped from non-config sources."""
    if not _chat_webhook_destination_app_node(node):
        return ()
    token_key = module_token_semantic_key(node.module_token)
    node_webhook_context = "webhook" in token_key
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in ("parameters", "mapper"):
        container = _object_or_empty(node.raw_payload.get(container_key))
        paths.extend(
            _json_dynamic_chat_webhook_destination_paths(
                container,
                path=(*node.source_trace.path, container_key),
                node_webhook_context=node_webhook_context,
            )
        )
    return tuple(paths)


def _json_dynamic_chat_webhook_destination_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
    node_webhook_context: bool,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return dynamic chat webhook destination mapping paths."""
    if isinstance(value, str):
        if (
            _path_is_chat_webhook_destination(
                path, node_webhook_context=node_webhook_context
            )
            and _contains_make_mapping(value)
            and not _maps_only_safe_destination_sources(value)
        ):
            return (path,)
        return ()
    if _is_json_object(value):
        object_paths: list[tuple[AstPathPart, ...]] = []
        for key, item in value.items():
            object_paths.extend(
                _json_dynamic_chat_webhook_destination_paths(
                    item,
                    path=(*path, key),
                    node_webhook_context=node_webhook_context,
                )
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_dynamic_chat_webhook_destination_paths(
                    item,
                    path=(*path, index),
                    node_webhook_context=node_webhook_context,
                )
            )
        return tuple(list_paths)
    return ()


def _json_header_crlf_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return JSON paths where header-scoped strings contain CRLF markers."""
    if isinstance(value, str):
        lowered = value.casefold()
        if _path_is_header_scoped(path) and any(
            marker in lowered for marker in CRLF_INJECTION_MARKERS
        ):
            return (path,)
        return ()
    if _is_json_object(value):
        object_paths: list[tuple[AstPathPart, ...]] = []
        for key, item in value.items():
            object_paths.extend(
                _json_header_crlf_paths(item, path=(*path, key))
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_header_crlf_paths(item, path=(*path, index))
            )
        return tuple(list_paths)
    return ()


def _json_dynamic_header_mapping_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return JSON paths where header-scoped strings contain unsanitized.

    mappings.
    """
    if isinstance(value, str):
        if (
            _path_is_header_scoped(path)
            and _contains_make_mapping(value)
            and not _has_header_sanitizer_evidence(value)
        ):
            return (path,)
        return ()
    if _is_json_object(value):
        object_paths: list[tuple[AstPathPart, ...]] = []
        for key, item in value.items():
            object_paths.extend(
                _json_dynamic_header_mapping_paths(item, path=(*path, key))
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_dynamic_header_mapping_paths(item, path=(*path, index))
            )
        return tuple(list_paths)
    return ()


def _json_proxy_header_mapping_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return paths where proxy identity headers map inbound-looking data."""
    if _is_json_object(value):
        object_paths: list[tuple[AstPathPart, ...]] = []
        header_name = _header_name(value)
        header_value = value.get("value")
        if (
            header_name is not None
            and _proxy_identity_header_name(header_name)
            and isinstance(header_value, str)
            and _maps_untrusted_proxy_header_source(header_value)
        ):
            object_paths.append((*path, "value"))
        for key, item in value.items():
            if (
                _proxy_identity_header_name(key)
                and isinstance(item, str)
                and _maps_untrusted_proxy_header_source(item)
            ):
                object_paths.append((*path, key))
            object_paths.extend(
                _json_proxy_header_mapping_paths(item, path=(*path, key))
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_proxy_header_mapping_paths(item, path=(*path, index))
            )
        return tuple(list_paths)
    return ()


def _json_static_secret_literal_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return JSON paths where secret-scoped static literals appear."""
    if isinstance(value, str):
        if _path_is_secret_scoped(path) and _static_secret_literal(value):
            return (path,)
        return ()
    if _is_json_object(value):
        object_paths = list(
            _header_object_static_secret_paths(value, path=path)
        )
        for key, item in value.items():
            object_paths.extend(
                _json_static_secret_literal_paths(item, path=(*path, key))
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_static_secret_literal_paths(item, path=(*path, index))
            )
        return tuple(list_paths)
    return ()


def _json_mapped_secret_header_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return JSON paths where secret-scoped headers map runtime values."""
    if _is_json_object(value):
        object_paths = list(
            _header_object_mapped_secret_paths(value, path=path)
        )
        for key, item in value.items():
            object_paths.extend(
                _json_mapped_secret_header_paths(item, path=(*path, key))
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_mapped_secret_header_paths(item, path=(*path, index))
            )
        return tuple(list_paths)
    return ()


def _json_cookie_passthrough_header_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return paths where outbound Cookie headers map cookie-like sources."""
    if isinstance(value, str):
        if _path_is_cookie_header_value(
            path
        ) and _maps_cookie_passthrough_source(value):
            return (path,)
        return ()
    if _is_json_object(value):
        object_paths = list(
            _header_object_cookie_passthrough_paths(value, path=path)
        )
        for key, item in value.items():
            object_paths.extend(
                _json_cookie_passthrough_header_paths(item, path=(*path, key))
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_cookie_passthrough_header_paths(item, path=(*path, index))
            )
        return tuple(list_paths)
    return ()


def _json_sensitive_mapping_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return JSON paths where outbound HTTP config maps sensitive fields."""
    if isinstance(value, str):
        if _path_is_outbound_http_mapping_surface(
            path
        ) and _maps_sensitive_field(value):
            return (path,)
        return ()
    if _is_json_object(value):
        object_paths: list[tuple[AstPathPart, ...]] = []
        for key, item in value.items():
            object_paths.extend(
                _json_sensitive_mapping_paths(item, path=(*path, key))
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_sensitive_mapping_paths(item, path=(*path, index))
            )
        return tuple(list_paths)
    return ()


def _header_object_static_secret_paths(
    value: JsonObject,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return header pair value paths with static secret-like literals."""
    header_name = _header_name(value)
    header_value = value.get("value")
    if (
        header_name is not None
        and _secret_token(header_name)
        and isinstance(header_value, str)
        and _static_secret_literal(header_value)
    ):
        return ((*path, "value"),)
    return ()


def _header_object_mapped_secret_paths(
    value: JsonObject,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return header pair value paths that map secret-scoped runtime values."""
    header_name = _header_name(value)
    header_value = value.get("value")
    if (
        header_name is not None
        and _secret_token(header_name)
        and isinstance(header_value, str)
        and _contains_make_mapping(header_value)
    ):
        return ((*path, "value"),)
    return ()


def _header_object_cookie_passthrough_paths(
    value: JsonObject,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return header pair paths where Cookie forwards cookie-like mappings."""
    header_name = _header_name(value)
    header_value = value.get("value")
    if (
        header_name is not None
        and _cookie_header_name(header_name)
        and isinstance(header_value, str)
        and _maps_cookie_passthrough_source(header_value)
    ):
        return ((*path, "value"),)
    return ()


def _path_is_header_scoped(path: tuple[AstPathPart, ...]) -> bool:
    """Return whether one AST path is inside a header configuration surface."""
    return any(
        isinstance(part, str)
        and module_token_semantic_key(part) in HEADER_PATH_TOKENS
        for part in path
    )


def _path_is_cookie_header_value(path: tuple[AstPathPart, ...]) -> bool:
    """Return whether one AST path looks like a direct Cookie header value."""
    normalized_parts = tuple(
        module_token_semantic_key(part)
        for part in path
        if isinstance(part, str)
    )
    return any(part in HEADER_PATH_TOKENS for part in normalized_parts) and any(
        part in COOKIE_HEADER_NAMES for part in normalized_parts
    )


def _path_is_secret_scoped(path: tuple[AstPathPart, ...]) -> bool:
    """Return whether one AST path is inside a secret-like configuration key."""
    return any(isinstance(part, str) and _secret_token(part) for part in path)


def _path_is_outbound_http_mapping_surface(
    path: tuple[AstPathPart, ...],
) -> bool:
    """Return whether one AST path can carry outbound HTTP request data."""
    return any(
        isinstance(part, str)
        and module_token_semantic_key(part) in HTTP_OUTBOUND_MAPPING_PATH_TOKENS
        for part in path
    )


def _path_is_chat_webhook_destination(
    path: tuple[AstPathPart, ...],
    *,
    node_webhook_context: bool,
) -> bool:
    """Return whether one path configures a chat webhook destination."""
    normalized_parts = tuple(
        module_token_semantic_key(part)
        for part in path
        if isinstance(part, str)
    )
    if any(
        part in CHAT_WEBHOOK_DESTINATION_TOKENS for part in normalized_parts
    ):
        return True
    return node_webhook_context and any(
        part in CHAT_WEBHOOK_URL_FIELD_TOKENS for part in normalized_parts
    )


def _has_header_sanitizer_evidence(value: str) -> bool:
    """Return whether a mapped header value visibly calls a sanitizer helper."""
    normalized = module_token_semantic_key(value)
    return any(token in normalized for token in HEADER_SANITIZER_TOKENS)


def _proxy_identity_header_name(value: str) -> bool:
    """Return if one header name carries client/proxy identity semantics."""
    return module_token_semantic_key(value) in PROXY_IDENTITY_HEADER_NAMES


def _cookie_header_name(value: str) -> bool:
    """Return whether one header name configures an outbound Cookie header."""
    return module_token_semantic_key(value) in COOKIE_HEADER_NAMES


def _secret_token(value: str) -> bool:
    """Return whether one key or label denotes a secret-bearing field."""
    return module_token_semantic_key(value) in SECRET_FIELD_TOKENS


def _static_secret_literal(value: str) -> bool:
    """Return whether a string is static secret-like configuration evidence."""
    stripped = value.strip()
    if _safe_secret_placeholder(stripped):
        return False
    return (
        _strong_secret_literal(stripped)
        or len(stripped) >= MIN_STATIC_LITERAL_LENGTH
    )


def _strong_secret_literal(value: str) -> bool:
    """Return whether a string matches a strong secret literal pattern."""
    return any(pattern.search(value) for pattern in SECRET_VALUE_PATTERNS)


def _safe_secret_placeholder(value: str) -> bool:
    """Return if a secret-scoped value is a mapping or obvious placeholder."""
    if "{{" in value or "}}" in value:
        return True
    normalized = module_token_semantic_key(value)
    return normalized in SAFE_SECRET_PLACEHOLDER_TOKENS or any(
        placeholder in normalized
        for placeholder in SAFE_SECRET_PLACEHOLDER_TOKENS
    )


def _maps_sensitive_field(value: str) -> bool:
    """Return if text contains a Make mapping for a sensitive source field."""
    return any(
        _expression_references_sensitive_field(expression)
        for expression in _mapping_expression_bodies_or_raw(value)
    )


def _maps_untrusted_proxy_header_source(value: str) -> bool:
    """Return if a mapped proxy header value references inbound-like data."""
    return any(
        _expression_references_untrusted_proxy_source(expression)
        for expression in _mapping_expression_bodies_or_raw(value)
    )


def _maps_cookie_passthrough_source(value: str) -> bool:
    """Return if a mapped header value references cookie-like source fields."""
    return any(
        _expression_references_cookie_source(expression)
        for expression in _mapping_expression_bodies_or_raw(value)
    )


def _maps_only_safe_destination_sources(value: str) -> bool:
    """Return if all mappings visibly come from config or connection sources."""
    try:
        templates = tuple(iter_make_expression_templates(value))
    except MakeExpressionTemplateParseError:
        return False
    if not templates:
        return False
    return all(
        _expression_references_safe_destination_source(template.body)
        for template in templates
    )


def _mapping_expression_bodies_or_raw(value: str) -> tuple[str, ...]:
    """Return parsed mapping bodies, or malformed body evidence for broken.

    delimiters.
    """
    if not _contains_make_mapping(value):
        return ()
    try:
        return tuple(
            template.body for template in iter_make_expression_templates(value)
        )
    except MakeExpressionTemplateParseError:
        return _malformed_mapping_body_candidates(value)


def _malformed_mapping_body_candidates(value: str) -> tuple[str, ...]:
    """Return conservative body candidates from malformed Make mapping text."""
    open_index = value.find("{{")
    if open_index >= 0:
        tail = value[open_index + 2 :]
        close_index = tail.find("}}")
        candidate = tail[:close_index] if close_index >= 0 else tail
        stripped = candidate.strip()
        return (stripped,) if stripped else (value,)
    close_index = value.find("}}")
    if close_index >= 0:
        candidate = value[:close_index].strip()
        return (candidate,) if candidate else (value,)
    return (value,)


def _expression_references_safe_destination_source(expression: str) -> bool:
    """Return whether a destination mapping references config or connection.

    sources.
    """
    tokens = _expression_field_tokens(expression)
    return any(token in SAFE_MAPPING_SOURCE_TOKENS for token in tokens)


def _expression_references_untrusted_proxy_source(expression: str) -> bool:
    """Return whether one mapping expression references inbound proxy-header.

    evidence.
    """
    tokens = _expression_field_tokens(expression)
    if any(token in SAFE_MAPPING_SOURCE_TOKENS for token in tokens):
        return False
    return any(
        token in PROXY_HEADER_UNTRUSTED_SOURCE_TOKENS for token in tokens
    ) or any(token in PROXY_IDENTITY_HEADER_NAMES for token in tokens)


def _expression_references_cookie_source(expression: str) -> bool:
    """Return if one mapping expression references cookie-like source fields."""
    tokens = _expression_field_tokens(expression)
    if any(token in SAFE_MAPPING_SOURCE_TOKENS for token in tokens):
        return False
    return any(token in COOKIE_PASSTHROUGH_SOURCE_TOKENS for token in tokens)


def _expression_references_sensitive_field(expression: str) -> bool:
    """Return if a mapping expression body references sensitive field names."""
    tokens = _expression_field_tokens(expression)
    if any(token in SAFE_MAPPING_SOURCE_TOKENS for token in tokens):
        return False
    return any(token in SENSITIVE_MAPPING_TOKENS for token in tokens)


def _chat_webhook_destination_app_node(node: MakeAstNode) -> bool:
    """Return whether one node belongs to a Slack or Discord app surface."""
    token_key = module_token_semantic_key(node.module_token)
    return any(token in token_key for token in CHAT_WEBHOOK_APP_TOKENS)


def _expression_field_tokens(expression: str) -> tuple[str, ...]:
    """Return the computed result for the caller."""
    return tuple(
        module_token_semantic_key(match.group(0))
        for match in re.finditer(r"[A-Za-z][A-Za-z0-9_]*", expression)
    )


def _contains_make_mapping(value: str) -> bool:
    """Return whether text contains Make expression mapping delimiters."""
    return any(marker in value for marker in MAKE_MAPPING_MARKERS)


def _header_name(value: JsonObject) -> str | None:
    """Return a header object name when present."""
    for key in ("name", "key", "header"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _object_or_empty(value: object) -> JsonObject:
    """Return a JSON object value or an empty object for mapping inspection."""
    return value if _is_json_object(value) else {}


def _json_has_evidence_key_token(
    value: object,
    *,
    tokens: tuple[str, ...],
) -> bool:
    """Return if JSON-like data contains a token-bearing key with evidence."""
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
            if _json_has_evidence_key_token(item, tokens=tokens):
                return True
    if isinstance(value, list):
        return any(
            _json_has_evidence_key_token(item, tokens=tokens)
            for item in cast("list[object]", value)
        )
    return False


def _json_has_api_version_header_evidence(value: object) -> bool:
    """Return whether header-like JSON declares version pinning."""
    if _is_json_object(value):
        header_name = _header_name(value)
        if header_name is not None and _header_name_has_api_version_evidence(
            header_name,
            value.get("value"),
        ):
            return True
        return any(
            _json_has_api_version_header_evidence(item)
            for item in value.values()
        )
    if isinstance(value, list):
        return any(
            _json_has_api_version_header_evidence(item)
            for item in cast("list[object]", value)
        )
    return False


def _header_name_has_api_version_evidence(name: str, value: object) -> bool:
    """Return whether one HTTP header pair carries API version evidence."""
    normalized_name = module_token_semantic_key(name)
    if normalized_name not in HTTP_API_VERSION_HEADER_NAMES:
        return False
    if normalized_name == "accept":
        return isinstance(value, str) and _accept_header_has_api_version(value)
    return _has_evidence_value(value)


def _accept_header_has_api_version(value: str) -> bool:
    """Return whether an Accept header visibly uses vendor versioning."""
    normalized = module_token_semantic_key(value)
    return "version" in normalized or bool(
        re.search(
            r"(?:^|[^A-Za-z0-9])v\d+(?:[^A-Za-z0-9]|$)", value, re.IGNORECASE
        )
    )


def _json_has_production_profile(value: object) -> bool:
    """Return whether JSON-like metadata declares a production profile."""
    if _is_json_object(value):
        for key, item in value.items():
            normalized_key = module_token_semantic_key(key)
            if (
                normalized_key in PRODUCTION_PROFILE_KEYS
                and _json_text_has_token(
                    item,
                    tokens=PRODUCTION_PROFILE_TOKENS,
                )
            ):
                return True
            if _json_has_production_profile(item):
                return True
    if isinstance(value, list):
        return any(
            _json_has_production_profile(item)
            for item in cast("list[object]", value)
        )
    return False


def _json_has_tls_verification_disabled(value: object) -> bool:
    """Return whether JSON-like data explicitly disables TLS verification."""
    false_keys = tuple(
        module_token_semantic_key(token)
        for token in HTTP_TLS_VERIFICATION_FALSE_KEYS
    )
    true_disable_keys = tuple(
        module_token_semantic_key(token)
        for token in HTTP_TLS_VERIFICATION_TRUE_DISABLE_KEYS
    )
    if _is_json_object(value):
        for key, item in value.items():
            normalized_key = module_token_semantic_key(key)
            if normalized_key in false_keys and _disabled_json(item):
                return True
            if normalized_key in true_disable_keys and _enabled_json(item):
                return True
            if _json_has_tls_verification_disabled(item):
                return True
    if isinstance(value, list):
        return any(
            _json_has_tls_verification_disabled(item)
            for item in cast("list[object]", value)
        )
    return False


def _json_text_has_token(value: object, *, tokens: tuple[str, ...]) -> bool:
    """Return whether JSON-like scalar text contains one normalized token."""
    normalized_tokens = tuple(
        module_token_semantic_key(token) for token in tokens
    )
    if isinstance(value, str):
        normalized_value = module_token_semantic_key(value)
        return any(token in normalized_value for token in normalized_tokens)
    if isinstance(value, int | float | bool) or value is None:
        return False
    if _is_json_object(value):
        return any(
            _json_text_has_token(item, tokens=tokens) for item in value.values()
        )
    if isinstance(value, list):
        return any(
            _json_text_has_token(item, tokens=tokens)
            for item in cast("list[object]", value)
        )
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


def _disabled_json(value: object) -> bool:
    """Return whether a JSON value explicitly disables a safety control."""
    if isinstance(value, bool):
        return not value
    if isinstance(value, int | float):
        return value == 0
    if isinstance(value, str):
        return module_token_semantic_key(value) in {
            "0 ",
            "disable ",
            "disabled ",
            "false ",
            "insecure ",
            "no ",
            "none ",
            "off ",
            "skip",
        }
    return False


def _enabled_json(value: object) -> bool:
    """Return whether a JSON value explicitly enables an unsafe skip control."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        return module_token_semantic_key(value) in {
            "1 ",
            "enable ",
            "enabled ",
            "on ",
            "true ",
            "yes",
        }
    return False


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    """Return whether a value is a string-keyed JSON object."""
    if not isinstance(value, dict):
        return False
    raw = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in raw)
