# Repository header: begin
# Provenance source mode: source_refs
# - 001060#repo.architecture.ports-adapters.boundary-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Public-safe Make JSON artifact boundary.

Boundary contract:
- Owns: final JSON artifact safety checks for Make-importable blueprints,
customer blueprint
  files, and Make live-resource manifests.
- Must not: call Make.com, inspect credentials, write files, or decide customer
package business
  policy.
- Allows: deterministic allowlist checks, private-trace detection, and sanitized
public copies.
- Split when: non-Make providers need their own artifact contract under
`languages/**`.
- Merge when: another Make module duplicates this exact public-artifact guard.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, cast

from languages.make.blueprint_export import (
    MAKE_NATIVE_NODE_METADATA_KEYS,
    MAKE_NATIVE_ROOT_METADATA_KEYS,
    PANCAKES_PRIVATE_KEY_PREFIXES,
    PANCAKES_PRIVATE_METADATA_KEYS,
    PANCAKES_PRIVATE_TEXT_PATTERNS,
    PANCAKES_PRIVATE_TEXT_REGEXES,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

type JsonObject = dict[str, object]
type MakePublicSafeArtifactKind = Literal[
    "make_blueprint_projection ",
    "make_blueprint_json ",
    "make_live_resource_manifest",
]

PUBLIC_SAFE_MAKE_ARTIFACT_SCHEMA_VERSION: Final = 1
MAKE_PUBLIC_SAFE_BLUEPRINT_ROOT_FIELDS: Final[tuple[str, ...]] = (
    "datastores ",
    "dataStores ",
    "dataStructures ",
    "flow ",
    "layout ",
    "metadata ",
    "name ",
    "sample_payloads ",
    "schedule ",
    "scheduling ",
    "webhooks ",
    "zone",
)
MAKE_PUBLIC_SAFE_BLUEPRINT_MODULE_FIELDS: Final[tuple[str, ...]] = (
    "expect ",
    "filter ",
    "flow ",
    "id ",
    "mapper ",
    "metadata ",
    "module ",
    "name ",
    "on_error ",
    "onerror ",
    "parameters ",
    "restore ",
    "routes ",
    "version",
)
MAKE_PUBLIC_SAFE_BLUEPRINT_ROUTE_FIELDS: Final[tuple[str, ...]] = (
    "directive ",
    "filter ",
    "flow ",
    "label ",
    "metadata ",
    "name",
)
MAKE_PUBLIC_SAFE_BLUEPRINT_FILTER_FIELDS: Final[tuple[str, ...]] = (
    "a ",
    "b ",
    "condition ",
    "conditions ",
    "expression ",
    "metadata ",
    "name ",
    "o",
)
MAKE_PUBLIC_SAFE_BLUEPRINT_METADATA_FIELDS: Final[tuple[str, ...]] = tuple(
    sorted(
        {
            *MAKE_NATIVE_ROOT_METADATA_KEYS,
            *MAKE_NATIVE_NODE_METADATA_KEYS,
            "color ",
            "content ",
            "isFilterNote ",
            "label ",
            "message ",
            "messages ",
            "moduleIds ",
            "notes ",
            "type ",
            "vendorSafe ",
            "x ",
            "y",
        }
    )
)
MAKE_PUBLIC_SAFE_LIVE_RESOURCE_TOP_LEVEL_FIELDS: Final[tuple[str, ...]] = (
    "artifact_kind ",
    "resources",
)
MAKE_PUBLIC_SAFE_LIVE_UPLOAD_PLAN_FIELDS: Final[tuple[str, ...]] = (
    "artifact_kind ",
    "client_connection_requirement_count ",
    "client_runtime_value_requirement_count ",
    "data_store_count ",
    "data_structure_count ",
    "dependency_order ",
    "manual_resource_creation_required ",
    "resource_creation_order ",
    "resource_creation_order_human ",
    "run_once_allowed ",
    "scenario_activation_allowed ",
    "status ",
    "webhook_count ",
    "webhook_create_prompt_allowed",
)
MAKE_PUBLIC_SAFE_LIVE_RESOURCE_FIELDS: Final[dict[str, tuple[str, ...]]] = {
    "make_live_data_structures": (
        "bind_ref ",
        "name ",
        "required_field ",
        "resource_key ",
        "schema_status ",
        "spec ",
        "strict",
    ),
    "make_live_data_stores": (
        "bind_placeholder ",
        "datastructure_ref ",
        "maxSizeMB ",
        "name ",
        "resource_key",
    ),
    "make_live_webhooks": (
        "bind_placeholder ",
        "data ",
        "name ",
        "resource_key ",
        "typeName",
    ),
    "client_app_connection_requirements": (
        "provider ",
        "source",
    ),
    "client_runtime_value_requirements": (
        "provider ",
        "source",
    ),
}
ACCEPTED_RUNTIME_PLACEHOLDER_SHAPES: Final[tuple[str, ...]] = (
    "{{runtime.<provider>.<name>}}",
    "__IMTCONN__",
    "{{<module-number>.<field>}}",
)
PRIVATE_IMPLEMENTATION_TEXT_PATTERNS: Final[tuple[str, ...]] = (
    *PANCAKES_PRIVATE_TEXT_PATTERNS,
    ".env ",
    "full_output_truncation_avoidance ",
    "graph_internals ",
    "internal_prompts ",
    "languages.make ",
    "linter_rules ",
    "local_ast_json ",
    "local_project_scenario ",
    "mcp.project ",
    "one_command_upload_entrypoint ",
    "pancakes_live_upload ",
    "project.make ",
    "raw_validation_report ",
    "repos/",
    "scoring_logic",
)
PRIVATE_IMPLEMENTATION_TEXT_REGEXES: Final[tuple[re.Pattern[str], ...]] = (
    *PANCAKES_PRIVATE_TEXT_REGEXES,
    re.compile(r"\b[a-z]:[\\/]", re.IGNORECASE),
    re.compile(r"(^|[\\/])users[\\/][^\\/]+[\\/]", re.IGNORECASE),
    re.compile(r"(^|[\\/])home[\\/][^\\/]+[\\/]", re.IGNORECASE),
)
SECRET_LIKE_TEXT_PATTERN: Final = re.compile(
    (
        r"\bBearer\s+\S{8,}"
        r"|\bToken\s+[A-Za-z0-9._=-]{8,}"
        r"|\bsk_(?:test|live|proj)_[A-Za-z0-9_=-]{6,}"
        r"|\bxox[baprs]-[A-Za-z0-9-]{16,}"
        r"|\bhooks\.make\.com/[A-Za-z0-9_-]{12,}"
        r"|\b(?:api[_ -]?key|password|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_=-]{8,}"
    ),
    re.IGNORECASE,
)
RUNTIME_PLACEHOLDER_TOKEN_PATTERN: Final = re.compile(
    r"\{\{\s*runtime\.[^}]+\}\}",
    re.IGNORECASE,
)
VALID_RUNTIME_PLACEHOLDER_PATTERN: Final = re.compile(
    r"\{\{\s*runtime\.[A-Za-z0-9_.-]+\s*}}",
    re.IGNORECASE,
)


class MakePublicSafeArtifactIssue(NamedTuple):
    """One public-safe artifact boundary issue."""

    code: str
    path: str
    message: str


class MakePublicSafeArtifactReport(NamedTuple):
    """Public-safe artifact boundary report."""

    schema_version: int
    artifact_kind: MakePublicSafeArtifactKind
    safe: bool
    issue_count: int
    issues: tuple[MakePublicSafeArtifactIssue, ...]
    make_owned_root_fields: tuple[str, ...]
    make_owned_module_fields: tuple[str, ...]
    accepted_runtime_placeholder_shapes: tuple[str, ...]


class _MappingShapeRule(NamedTuple):
    allowed_keys: tuple[str, ...]
    code: str
    message: str
    allow_provider_extensions: bool


class MakePublicSafeArtifactError(ValueError):
    """Raised when a Make artifact is not safe for customer or Make JSON.

    surfaces.
    """

    def __init__(self, report: MakePublicSafeArtifactReport) -> None:
        """Store the failing public-safe report."""
        preview = ", ".join(
            f"{issue.path}:{issue.code}" for issue in report.issues[:5]
        )
        super().__init__(
            f"Make public-safe artifact boundary failed: {preview}"
        )
        self.report = report


def make_public_safe_blueprint_json(
    payload: Mapping[str, object],
) -> JsonObject:
    """Return the Make-importable blueprint JSON that can be written for.

    customers.
    """
    scenario = _blueprint_scenario(payload)
    public_payload = _json_object_copy(scenario)
    assert_make_public_safe_artifact(
        public_payload,
        artifact_kind="make_blueprint_json",
    )
    return public_payload


def make_public_safe_live_resource_manifest(
    payload: Mapping[str, object],
) -> JsonObject:
    """Return a public-safe Make live-resource manifest JSON object.

    Raises:
        ValueError: If the live-resource artifact kind is unsupported or
        malformed.
    """
    artifact_kind = _required_text(
        payload.get("artifact_kind"), field="artifact_kind"
    )
    public_payload: JsonObject
    if artifact_kind == "make_live_upload_plan":
        public_payload = _subset_payload(
            payload,
            allowed_keys=MAKE_PUBLIC_SAFE_LIVE_UPLOAD_PLAN_FIELDS,
        )
    else:
        allowed_resource_keys = MAKE_PUBLIC_SAFE_LIVE_RESOURCE_FIELDS.get(
            artifact_kind
        )
        if allowed_resource_keys is None:
            message = (
                f"Unsupported Make live-resource artifact kind: {artifact_kind}"
            )
            raise ValueError(message)
        public_payload = {
            "artifact_kind": artifact_kind,
            "resources": tuple(
                _subset_payload(resource, allowed_keys=allowed_resource_keys)
                for resource in _resource_rows(payload)
            ),
        }
    assert_make_public_safe_artifact(
        public_payload,
        artifact_kind="make_live_resource_manifest",
    )
    return public_payload


def assert_make_public_safe_artifact(
    payload: Mapping[str, object],
    *,
    artifact_kind: MakePublicSafeArtifactKind,
) -> None:
    """Raise if a JSON artifact violates the public-safe Make boundary.

    Raises:
        MakePublicSafeArtifactError: If the artifact violates the public
        boundary.
    """
    report = validate_make_public_safe_artifact(
        payload, artifact_kind=artifact_kind
    )
    if not report.safe:
        raise MakePublicSafeArtifactError(report)


def validate_make_public_safe_artifact(
    payload: Mapping[str, object],
    *,
    artifact_kind: MakePublicSafeArtifactKind,
) -> MakePublicSafeArtifactReport:
    """Return a deterministic public-safe artifact boundary report."""
    inspected_payload = (
        _blueprint_scenario(payload)
        if artifact_kind in {"make_blueprint_projection", "make_blueprint_json"}
        else payload
    )
    issues: list[MakePublicSafeArtifactIssue] = []
    if artifact_kind in {"make_blueprint_projection", "make_blueprint_json"}:
        _collect_blueprint_shape_issues(inspected_payload, issues=issues)
    elif artifact_kind == "make_live_resource_manifest":
        _collect_live_manifest_shape_issues(inspected_payload, issues=issues)
    _collect_generic_safety_issues(inspected_payload, path="$", issues=issues)
    return MakePublicSafeArtifactReport(
        schema_version=PUBLIC_SAFE_MAKE_ARTIFACT_SCHEMA_VERSION,
        artifact_kind=artifact_kind,
        safe=not issues,
        issue_count=len(issues),
        issues=tuple(issues),
        make_owned_root_fields=MAKE_PUBLIC_SAFE_BLUEPRINT_ROOT_FIELDS,
        make_owned_module_fields=MAKE_PUBLIC_SAFE_BLUEPRINT_MODULE_FIELDS,
        accepted_runtime_placeholder_shapes=ACCEPTED_RUNTIME_PLACEHOLDER_SHAPES,
    )


def make_public_safe_artifact_report_payload(
    report: MakePublicSafeArtifactReport,
) -> JsonObject:
    """Return a JSON-compatible public-safe artifact report summary."""
    return {
        "schema_version": report.schema_version,
        "artifact_kind": report.artifact_kind,
        "safe": report.safe,
        "issue_count": report.issue_count,
        "issues": tuple(issue._asdict() for issue in report.issues),
        "make_owned_root_fields": report.make_owned_root_fields,
        "make_owned_module_fields": report.make_owned_module_fields,
        "accepted_runtime_placeholder_shapes": (
            report.accepted_runtime_placeholder_shapes
        ),
    }


def _blueprint_scenario(payload: Mapping[str, object]) -> Mapping[str, object]:
    scenario = payload.get("scenario")
    if (
        isinstance(scenario, dict)
        and payload.get("artifact_format") == "make_blueprint_json"
    ):
        return cast("Mapping[str, object]", scenario)
    return payload


def _collect_blueprint_shape_issues(
    payload: Mapping[str, object],
    *,
    issues: list[MakePublicSafeArtifactIssue],
) -> None:
    for key in payload:
        key_text = str(key)
        if key_text not in MAKE_PUBLIC_SAFE_BLUEPRINT_ROOT_FIELDS:
            issues.append(
                MakePublicSafeArtifactIssue(
                    code="make_blueprint.unexpected_root_field",
                    path=f"$.{key_text}",
                    message=(
                        "Make-importable blueprint roots may only contain "
                        "Make-owned fields."
                    ),
                )
            )
    _collect_blueprint_nested_shape_issues(payload, path="$", issues=issues)


def _collect_blueprint_nested_shape_issues(
    value: object,
    *,
    path: str,
    issues: list[MakePublicSafeArtifactIssue],
) -> None:
    if isinstance(value, dict):
        mapping = cast("Mapping[object, object]", value)
        _collect_blueprint_mapping_shape_issues(
            mapping, path=path, issues=issues
        )
        for key, child in mapping.items():
            _collect_blueprint_nested_shape_issues(
                child,
                path=f"{path}.{key}",
                issues=issues,
            )
        return
    if isinstance(value, list | tuple):
        for index, child in enumerate(cast("Sequence[object]", value)):
            _collect_blueprint_nested_shape_issues(
                child,
                path=f"{path}[{index}]",
                issues=issues,
            )


def _collect_blueprint_mapping_shape_issues(
    mapping: Mapping[object, object],
    *,
    path: str,
    issues: list[MakePublicSafeArtifactIssue],
) -> None:
    if _is_metadata_path(path):
        _collect_unexpected_mapping_keys(
            mapping,
            path=path,
            rule=_MappingShapeRule(
                allowed_keys=MAKE_PUBLIC_SAFE_BLUEPRINT_METADATA_FIELDS,
                code="make_blueprint.unexpected_metadata_field",
                message=(
                    "Blueprint metadata may only expose Make-native metadata."
                ),
                allow_provider_extensions=True,
            ),
            issues=issues,
        )
        return
    if _is_filter_path(path):
        _collect_unexpected_mapping_keys(
            mapping,
            path=path,
            rule=_MappingShapeRule(
                allowed_keys=MAKE_PUBLIC_SAFE_BLUEPRINT_FILTER_FIELDS,
                code="make_blueprint.unexpected_filter_field",
                message=(
                    "Blueprint filters may only expose Make-native filter "
                    "fields."
                ),
                allow_provider_extensions=False,
            ),
            issues=issues,
        )
        return
    if _looks_like_route(mapping):
        _collect_unexpected_mapping_keys(
            mapping,
            path=path,
            rule=_MappingShapeRule(
                allowed_keys=MAKE_PUBLIC_SAFE_BLUEPRINT_ROUTE_FIELDS,
                code="make_blueprint.unexpected_route_field",
                message=(
                    "Blueprint routes may only expose Make-native route fields."
                ),
                allow_provider_extensions=False,
            ),
            issues=issues,
        )


def _collect_unexpected_mapping_keys(
    mapping: Mapping[object, object],
    *,
    path: str,
    rule: _MappingShapeRule,
    issues: list[MakePublicSafeArtifactIssue],
) -> None:
    for key in mapping:
        key_text = str(key)
        if key_text in rule.allowed_keys:
            continue
        if rule.allow_provider_extensions and _is_provider_extension_key(
            key_text
        ):
            continue
        issues.append(
            MakePublicSafeArtifactIssue(
                code=rule.code,
                path=f"{path}.{key_text}",
                message=rule.message,
            )
        )


def _collect_live_manifest_shape_issues(
    payload: Mapping[str, object],
    *,
    issues: list[MakePublicSafeArtifactIssue],
) -> None:
    artifact_kind = payload.get("artifact_kind")
    allowed_top_level = (
        MAKE_PUBLIC_SAFE_LIVE_UPLOAD_PLAN_FIELDS
        if artifact_kind == "make_live_upload_plan"
        else MAKE_PUBLIC_SAFE_LIVE_RESOURCE_TOP_LEVEL_FIELDS
    )
    for key in payload:
        key_text = str(key)
        if key_text not in allowed_top_level:
            issues.append(
                MakePublicSafeArtifactIssue(
                    code="make_live_manifest.unexpected_root_field",
                    path=f"$.{key_text}",
                    message=(
                        "Live-resource manifests may only expose public Make "
                        "setup fields."
                    ),
                )
            )


def _collect_generic_safety_issues(
    value: object,
    *,
    path: str,
    issues: list[MakePublicSafeArtifactIssue],
) -> None:
    if isinstance(value, dict):
        for raw_key, child in cast("Mapping[object, object]", value).items():
            key = str(raw_key)
            child_path = f"{path}.{key}"
            if _is_private_key(key):
                issues.append(
                    MakePublicSafeArtifactIssue(
                        code="public_artifact.private_key",
                        path=child_path,
                        message=(
                            "Public Make JSON must not contain private "
                            "implementation keys."
                        ),
                    )
                )
            _collect_generic_safety_issues(
                child, path=child_path, issues=issues
            )
        return
    if isinstance(value, list | tuple):
        for index, child in enumerate(cast("Sequence[object]", value)):
            _collect_generic_safety_issues(
                child,
                path=f"{path}[{index}]",
                issues=issues,
            )
        return
    if isinstance(value, str):
        _collect_text_safety_issues(value, path=path, issues=issues)


def _collect_text_safety_issues(
    value: str,
    *,
    path: str,
    issues: list[MakePublicSafeArtifactIssue],
) -> None:
    if _text_has_private_trace(value):
        issues.append(
            MakePublicSafeArtifactIssue(
                code="public_artifact.private_trace_text",
                path=path,
                message=(
                    "Public Make JSON must not contain private implementation "
                    "text."
                ),
            )
        )
    if SECRET_LIKE_TEXT_PATTERN.search(value):
        issues.append(
            MakePublicSafeArtifactIssue(
                code="public_artifact.secret_like_text",
                path=path,
                message="Public Make JSON must not contain secret-like values.",
            )
        )
    if "{{" in value and "runtime" in value.casefold():
        runtime_matches = tuple(
            RUNTIME_PLACEHOLDER_TOKEN_PATTERN.finditer(value)
        )
        if not runtime_matches:
            issues.append(
                MakePublicSafeArtifactIssue(
                    code="public_artifact.invalid_runtime_placeholder",
                    path=path,
                    message=(
                        "Runtime placeholders must use"
                        "{{runtime.<provider>.<name>}}."
                    ),
                )
            )
            return
        issues.extend(
            MakePublicSafeArtifactIssue(
                code="public_artifact.invalid_runtime_placeholder",
                path=path,
                message=(
                    "Runtime placeholders must use"
                    "{{runtime.<provider>.<name>}}."
                ),
            )
            for match in runtime_matches
            if VALID_RUNTIME_PLACEHOLDER_PATTERN.fullmatch(match.group(0))
            is None
        )


def _is_private_key(key: str) -> bool:
    normalized = key.casefold()
    return (
        normalized in PANCAKES_PRIVATE_METADATA_KEYS
        or normalized.startswith(PANCAKES_PRIVATE_KEY_PREFIXES)
    )


def _text_has_private_trace(value: str) -> bool:
    normalized = value.casefold().replace("\\", "/")
    return any(
        pattern in normalized
        for pattern in PRIVATE_IMPLEMENTATION_TEXT_PATTERNS
    ) or any(
        pattern.search(value) is not None
        for pattern in PRIVATE_IMPLEMENTATION_TEXT_REGEXES
    )


def _looks_like_route(mapping: Mapping[object, object]) -> bool:
    return "flow" in mapping and "module" not in mapping and "id" not in mapping


def _is_metadata_path(path: str) -> bool:
    return path.endswith(".metadata")


def _is_filter_path(path: str) -> bool:
    return path.endswith(".filter")


def _is_provider_extension_key(key: str) -> bool:
    normalized = key.casefold()
    return normalized.startswith("vendor") or normalized.endswith("safe")


def _resource_rows(
    payload: Mapping[str, object],
) -> tuple[Mapping[str, object], ...]:
    resources = payload.get("resources")
    if not isinstance(resources, list | tuple):
        return ()
    typed_resources = cast("Sequence[object]", resources)
    return tuple(
        cast("Mapping[str, object]", resource)
        for resource in typed_resources
        if isinstance(resource, dict)
    )


def _subset_payload(
    payload: Mapping[str, object],
    *,
    allowed_keys: tuple[str, ...],
) -> JsonObject:
    return {
        key: _json_value_copy(payload[key])
        for key in allowed_keys
        if key in payload
    }


def _required_text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        message = f"{field} must be a non-empty string."
        raise ValueError(message)
    return value.strip()


def _json_object_copy(value: Mapping[str, object]) -> JsonObject:
    return cast("JsonObject", _json_value_copy(value))


def _json_value_copy(value: object) -> object:
    return cast("object", json.loads(json.dumps(value, sort_keys=True)))
