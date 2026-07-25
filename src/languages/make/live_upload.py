# ruff: noqa: DOC201, DOC501, E501, PLR0913, PLR0914, S310
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001041#repo.make-scraper.raw-spec-refresh-policy
# - 001055#repo.mcp.required-tool-surface
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

# PLR0914, TRY003, T201

"""One-command Make live resource upload for Pancakes packages.

Boundary contract:
- Owns: reading Pancakes local Make live-resource packages and applying them
through typed Make
  API calls in dependency order.
- Must not: persist API tokens, print secrets, create browser sessions, activate
scenarios, or run
  provider modules.
- Allows: dry-run validation, injected fake clients for tests, and runtime-only
API token input.
- Split when: a hosted web uploader owns its own request/session layer.
- Merge when: another module uploads the same Pancakes live-resource package
contract.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, Self, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from languages.make.guided_deployment import (
    guided_make_deployment_policy_as_dict,
)
from languages.make.notes import (
    MAKE_NOTE_COLOR_PALETTE,
    MAKE_NOTE_DEFAULT_COLOR,
)
from languages.make.public_safe_artifacts import (
    MakePublicSafeArtifactError,
    assert_make_public_safe_artifact,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from types import TracebackType

type JsonObject = dict[str, object]

DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_ZONE = "us2"
HTTPS_PREFIX = "https://"
SECRET_LIKE_PATTERN = re.compile(
    r"\bBearer\s+\S{8,}|\bsk_(?:test|live|proj)_[A-Za-z0-9_=-]{6,}|\bxox[baprs]-[A-Za-z0-9-]{16,}|\bhooks\.make\.com/[A-Za-z0-9_-]{12,}",
    re.IGNORECASE,
)


class LiveUploadError(RuntimeError):
    """Raised when a live upload package or response violates the contract."""


class MakeLiveClient(Protocol):
    """Minimal Make API transport required by the live upload runner."""

    def request_json(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, object] | None = None,
        body: JsonObject | None = None,
    ) -> JsonObject:
        """Return the JSON object response for one Make API request."""
        ...


class HttpResponseLike(Protocol):
    """Response protocol returned by urllib for JSON Make API calls."""

    def __enter__(self) -> Self:
        """Return the context-managed response."""
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        """Close the context-managed response."""
        ...

    def read(self) -> bytes:
        """Return response bytes."""
        ...


class MakeLiveApiClient:
    """Runtime-token Make API client used by the one-command uploader."""

    def __init__(
        self,
        *,
        api_token: str,
        zone: str = DEFAULT_ZONE,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize the Make API client."""
        self._api_token = api_token.strip()
        self._zone = zone.strip().lower() or DEFAULT_ZONE
        self._timeout_seconds = timeout_seconds
        if not self._api_token:
            msg = "MAKE_API_TOKEN is required for --apply."
            raise LiveUploadError(msg)

    @staticmethod
    def format_http_error(
        *,
        status_code: int,
        method: str,
        path: str,
        response_body: bytes,
    ) -> LiveUploadError:
        """Return a redacted actionable error for a failed Make API response."""
        detail = _safe_http_error_detail(response_body)
        suffix = f" ({detail})" if detail else ""
        return LiveUploadError(
            f"Make API failed for {method.upper()} {path} with status "
            f"{status_code}{suffix}."
        )

    def request_json(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, object] | None = None,
        body: JsonObject | None = None,
    ) -> JsonObject:
        """Send a JSON request to the Make API.

        Returns:
            The decoded JSON object response.
        """
        request = Request(
            self._url(path=path, query=query),
            data=_body_bytes(body),
            headers=self._headers(include_json=body is not None),
            method=method.upper(),
        )
        try:
            with cast(
                "HttpResponseLike",
                urlopen(request, timeout=self._timeout_seconds),
            ) as response:
                response_text = response.read().decode("utf-8")
                payload = cast("object", json.loads(response_text))
        except HTTPError as exc:
            raise _http_error(exc, method=method.upper(), path=path) from exc
        except URLError as exc:
            message = f"Make API transport failed for {method.upper()} {path}."
            raise LiveUploadError(message) from exc
        if not isinstance(payload, dict):
            msg = (
                f"Make API returned non-object JSON for {method.upper()} "
                f"{path}."
            )
            raise LiveUploadError(msg)
        return cast("JsonObject", payload)

    def _headers(self, *, include_json: bool) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Token {self._api_token}",
            "User-Agent": "Pancakes-LiveUpload/1.0",
        }
        if include_json:
            headers["Content-Type"] = "application/json"
        return headers

    def _url(self, *, path: str, query: Mapping[str, object] | None) -> str:
        host = (
            self._zone
            if self._zone.endswith(".make.com")
            else f"{self._zone}.make.com"
        )
        normalized_path = path if path.startswith("/") else f"/{path}"
        url = f"https://{host}/api/v2{normalized_path}"
        if not url.startswith(HTTPS_PREFIX):
            msg = "Make API URL must use HTTPS."
            raise LiveUploadError(msg)
        if not query:
            return url
        encoded = urlencode(
            {key: _query_value(value) for key, value in query.items()}
        )
        return f"{url}?{encoded}"


def dry_run_project_upload(
    *,
    project_folder: Path,
    team_id: int,
    organization_id: int,
    connection_bindings: Mapping[str, object] | None = None,
    runtime_values: Mapping[str, object] | None = None,
) -> JsonObject:
    """Validate one live upload package without a token or network call."""
    bundle = load_live_upload_bundle(project_folder=project_folder)
    return prepare_live_upload(
        bundle=bundle,
        team_id=team_id,
        organization_id=organization_id,
        apply=False,
        connection_bindings=connection_bindings or {},
        runtime_values=runtime_values or {},
    )


def apply_project_upload(
    *,
    project_folder: Path,
    team_id: int,
    organization_id: int,
    client: MakeLiveClient,
    connection_bindings: Mapping[str, object] | None = None,
    runtime_values: Mapping[str, object] | None = None,
    cleanup_on_failure: bool = True,
) -> JsonObject:
    """Apply one live upload package through an injected Make client."""
    bundle = load_live_upload_bundle(project_folder=project_folder)
    return prepare_live_upload(
        bundle=bundle,
        team_id=team_id,
        organization_id=organization_id,
        apply=True,
        client=client,
        connection_bindings=connection_bindings or {},
        runtime_values=runtime_values or {},
        cleanup_on_failure=cleanup_on_failure,
    )


def load_live_upload_bundle(*, project_folder: Path) -> JsonObject:
    """Load the package and first-class live resource artifacts for one project.  # noqa: DOC201, DOC501.

    folder.

    Returns:
        The computed value.

    Raises:
        LiveUploadError: If the operation cannot complete.
    """
    artifacts = project_folder / "artifacts"
    package_path = artifacts / "make-import-package.json"
    live_path = artifacts / "make-live"
    package = _read_json_object(package_path)
    live_bundle: JsonObject = {
        "package_path": str(package_path),
        "live_path": str(live_path),
        "package": package,
        "datastructure": _read_json_object(live_path / "datastructure.json"),
        "datastore": _read_json_object(live_path / "datastore.json"),
        "webhook": _read_json_object(live_path / "webhook.json"),
        "connections": _read_json_object(live_path / "connections.json"),
        "runtime_values": _read_json_object(live_path / "runtime-values.json"),
        "upload_plan": _read_json_object(live_path / "upload-plan.json"),
    }
    _reject_secret_like_payload(live_bundle, label=str(live_path))
    blueprint = package.get("blueprint_artifact_json")
    if not isinstance(blueprint, dict):
        msg = "make-import-package.json is missing blueprint_artifact_json."
        raise LiveUploadError(msg)
    scenario = cast("Mapping[str, object]", blueprint).get("scenario")
    if not isinstance(scenario, dict):
        msg = "blueprint_artifact_json.scenario must be a JSON object."
        raise LiveUploadError(msg)
    _assert_public_safe_live_upload_bundle(live_bundle)
    return live_bundle


def prepare_live_upload(
    *,
    bundle: Mapping[str, object],
    team_id: int,
    organization_id: int,
    apply: bool,
    client: MakeLiveClient | None = None,
    connection_bindings: Mapping[str, object],
    runtime_values: Mapping[str, object],
    cleanup_on_failure: bool = True,
) -> JsonObject:
    """Validate and optionally apply the package."""
    _require_positive_int(team_id, label="team_id")
    _require_positive_int(organization_id, label="organization_id")
    package = _json_mapping(bundle["package"], label="package")
    blueprint = _json_mapping(
        package["blueprint_artifact_json"], label="blueprint_artifact_json"
    )
    scenario = _json_mapping(
        blueprint["scenario"], label="blueprint_artifact_json.scenario"
    )
    data_structures = _resource_rows(bundle, "datastructure")
    data_stores = _resource_rows(bundle, "datastore")
    webhooks = _resource_rows(bundle, "webhook")
    scenario_notes = _scenario_note_payloads(scenario)
    connection_requirements = _resource_rows(bundle, "connections")
    runtime_requirements = _resource_rows(bundle, "runtime_values")
    missing_connections = _missing_bindings(
        connection_requirements, connection_bindings
    )
    missing_runtime_values = _missing_bindings(
        runtime_requirements, runtime_values
    )
    dry_run_payload = _dry_run_payload(
        apply=apply,
        team_id=team_id,
        organization_id=organization_id,
        data_structures=data_structures,
        data_stores=data_stores,
        webhooks=webhooks,
        scenario_notes=scenario_notes,
        connection_requirements=connection_requirements,
        runtime_requirements=runtime_requirements,
        missing_connections=missing_connections,
        missing_runtime_values=missing_runtime_values,
    )
    if not apply:
        return dry_run_payload
    if client is None:
        msg = "client is required when apply=true."
        raise LiveUploadError(msg)
    if missing_connections or missing_runtime_values:
        payload = dict(dry_run_payload)
        payload["status"] = "blocked_missing_client_bindings"
        payload["writes_performed"] = False
        payload["provider_api_call"] = False
        payload["live_make_called"] = False
        return payload
    created: dict[str, list[int]] = {
        "data_structures": [],
        "data_stores": [],
        "webhooks": [],
        "scenarios": [],
    }
    resource_bindings: dict[str, object] = {}
    try:
        _create_data_structures(
            client=client,
            team_id=team_id,
            resources=data_structures,
            created=created,
            resource_bindings=resource_bindings,
        )
        _create_data_stores(
            client=client,
            team_id=team_id,
            resources=data_stores,
            created=created,
            resource_bindings=resource_bindings,
        )
        _create_webhooks(
            client=client,
            team_id=team_id,
            resources=webhooks,
            created=created,
            resource_bindings=resource_bindings,
        )
        bound_scenario = _bind_blueprint(
            scenario=scenario,
            resource_bindings=resource_bindings,
            connection_requirements=connection_requirements,
            connection_bindings=connection_bindings,
            runtime_values=runtime_values,
        )
        response = client.request_json(
            "POST",
            "/scenarios",
            body={
                "teamId": team_id,
                "name": str(
                    bound_scenario.get("name")
                    or package.get("project_id")
                    or "Imported Make scenario"
                ),
                "blueprint": json.dumps(
                    bound_scenario, ensure_ascii=True, sort_keys=True
                ),
                "scheduling": json.dumps(
                    {"type": "on-demand"}, ensure_ascii=True
                ),
            },
        )
        scenario_id = _extract_int(response, ("scenario.id", "id"))
        created["scenarios"].append(scenario_id)
        notes_status = _create_scenario_notes(
            client=client,
            scenario_id=scenario_id,
            team_id=team_id,
            organization_id=organization_id,
            scenario=bound_scenario,
            notes=scenario_notes,
        )
        export_status = _export_compare_status(
            client=client,
            scenario_id=scenario_id,
            local_scenario=bound_scenario,
        )
    except Exception:
        if cleanup_on_failure:
            _rollback_created(client=client, created=created)
        raise
    return {
        "status": "live_upload_applied",
        "team_id": team_id,
        "organization_id": organization_id,
        "writes_performed": True,
        "provider_api_call": True,
        "live_make_called": True,
        "credential_value_transfer": False,
        "secret_output": False,
        "scenario_activation_called": False,
        "scenario_run_once_called": False,
        "created_counts": {key: len(values) for key, values in created.items()},
        "created_ids": created,
        "scenario_notes_status": notes_status["status"],
        "scenario_notes_created_count": notes_status["created_count"],
        "export_compare_status": export_status,
        "dynamic_api_key_policy": _dynamic_api_key_policy(),
        "redaction_status": "passed",
    }


def _dry_run_payload(
    *,
    apply: bool,
    team_id: int,
    organization_id: int,
    data_structures: tuple[JsonObject, ...],
    data_stores: tuple[JsonObject, ...],
    webhooks: tuple[JsonObject, ...],
    scenario_notes: tuple[JsonObject, ...],
    connection_requirements: tuple[JsonObject, ...],
    runtime_requirements: tuple[JsonObject, ...],
    missing_connections: tuple[str, ...],
    missing_runtime_values: tuple[str, ...],
) -> JsonObject:
    blocked = bool(missing_connections or missing_runtime_values)
    return {
        "status": "blocked_missing_client_bindings"
        if blocked
        else "dry_run_ready",
        "apply": apply,
        "team_id": team_id,
        "organization_id": organization_id,
        "writes_performed": False,
        "provider_api_call": False,
        "live_make_called": False,
        "credential_value_transfer": False,
        "secret_output": False,
        "would_create": {
            "data_structures": len(data_structures),
            "data_stores": len(data_stores),
            "webhooks": len(webhooks),
            "scenario_notes": len(scenario_notes),
            "scenarios": 1,
        },
        "client_supplied_connection_count": len(connection_requirements),
        "client_supplied_runtime_value_count": len(runtime_requirements),
        "missing_connection_bindings": missing_connections,
        "missing_runtime_values": missing_runtime_values,
        "dependency_order": (
            "create_data_structures",
            "create_data_stores_with_created_data_structure_ids",
            "create_webhooks",
            "bind_created_resource_ids_into_blueprint",
            "create_inactive_on_demand_scenario",
            "create_scenario_notes_via_notes_batch_api",
        ),
        "guided_make_deployment_policy": (
            guided_make_deployment_policy_as_dict()
        ),
        "dynamic_api_key_policy": _dynamic_api_key_policy(),
        "manual_make_ui_required_for_resources": False,
        "webhook_create_prompt_allowed": False,
    }


def _create_data_structures(
    *,
    client: MakeLiveClient,
    team_id: int,
    resources: tuple[JsonObject, ...],
    created: dict[str, list[int]],
    resource_bindings: dict[str, object],
) -> None:
    for resource in resources:
        response = client.request_json(
            "POST",
            "/data-structures",
            body={
                "teamId": team_id,
                "name": str(resource["name"]),
                "strict": bool(resource["strict"]),
                "spec": resource["spec"],
            },
        )
        structure_id = _extract_int(response, ("id", "dataStructure.id"))
        created["data_structures"].append(structure_id)
        resource_bindings[f"datastructure:{resource['resource_key']}"] = (
            structure_id
        )


def _create_data_stores(
    *,
    client: MakeLiveClient,
    team_id: int,
    resources: tuple[JsonObject, ...],
    created: dict[str, list[int]],
    resource_bindings: dict[str, object],
) -> None:
    for resource in resources:
        structure_ref = str(resource["datastructure_ref"])
        structure_id = _int_binding(
            resource_bindings,
            key=f"datastructure:{structure_ref}",
        )
        response = client.request_json(
            "POST",
            "/data-stores",
            body={
                "teamId": team_id,
                "name": str(resource["name"]),
                "datastructureId": structure_id,
                "maxSizeMB": _positive_int_value(
                    resource["maxSizeMB"], label="maxSizeMB"
                ),
            },
        )
        store_id = _extract_int(response, ("id", "dataStore.id"))
        created["data_stores"].append(store_id)
        resource_bindings[str(resource["bind_placeholder"])] = store_id


def _create_webhooks(
    *,
    client: MakeLiveClient,
    team_id: int,
    resources: tuple[JsonObject, ...],
    created: dict[str, list[int]],
    resource_bindings: dict[str, object],
) -> None:
    for resource in resources:
        response = client.request_json(
            "POST",
            "/hooks",
            body={
                "teamId": team_id,
                "name": str(resource["name"]),
                "typeName": str(resource["typeName"]),
                "data": _json_mapping(resource["data"], label="webhook.data"),
            },
        )
        hook_id = _extract_int(response, ("id", "hook.id"))
        created["webhooks"].append(hook_id)
        resource_bindings[str(resource["bind_placeholder"])] = hook_id


def _bind_blueprint(
    *,
    scenario: Mapping[str, object],
    resource_bindings: Mapping[str, object],
    connection_requirements: tuple[JsonObject, ...],
    connection_bindings: Mapping[str, object],
    runtime_values: Mapping[str, object],
) -> JsonObject:
    replacements: dict[str, object] = {}
    replacements.update(resource_bindings)
    replacements.update(_expanded_runtime_bindings(runtime_values))
    bound = cast(
        "JsonObject",
        _replace_exact_strings(deepcopy(dict(scenario)), replacements),
    )
    _apply_connection_path_bindings(
        bound,
        requirements=connection_requirements,
        connection_bindings=connection_bindings,
    )
    unresolved = tuple(sorted(_unresolved_runtime_placeholders(bound)))
    if unresolved:
        msg = f"Unresolved runtime placeholders remain: {', '.join(unresolved)}"
        raise LiveUploadError(msg)
    return bound


def _apply_connection_path_bindings(
    scenario: JsonObject,
    *,
    requirements: tuple[JsonObject, ...],
    connection_bindings: Mapping[str, object],
) -> None:
    expanded = _expanded_runtime_bindings(connection_bindings)
    for requirement in requirements:
        source = str(requirement.get("source") or "")
        binding = expanded.get(source) or expanded.get(source.strip("{} "))
        if binding is None:
            continue
        paths = requirement.get("example_field_paths")
        if isinstance(paths, list | tuple) and paths:
            for field_path in cast("Sequence[object]", paths):
                _set_blueprint_path(scenario, str(field_path), binding)
        elif source:
            _replace_connection_source_fallback(scenario, source, binding)


def _replace_connection_source_fallback(
    scenario: JsonObject,
    source: str,
    binding: object,
) -> None:
    replaced = _replace_exact_strings(
        scenario, {source: binding, source.strip("{} "): binding}
    )
    scenario.clear()
    scenario.update(cast("JsonObject", replaced))


def _set_blueprint_path(root: JsonObject, path: str, value: object) -> None:
    parts = _blueprint_path_parts(path)
    if not parts or parts[0] != "flow":
        msg = f"Unsupported blueprint binding path: {path}"
        raise LiveUploadError(msg)
    target: object = root
    for part in parts[:-1]:
        target = _path_child(target, part=part, full_path=path)
    final = parts[-1]
    if not isinstance(target, dict):
        msg = f"Blueprint binding path does not target an object: {path}"
        raise LiveUploadError(msg)
    cast("dict[str, object]", target)[final] = value


def _blueprint_path_parts(path: str) -> tuple[str, ...]:
    parts: list[str] = []
    for segment in path.split("."):
        if "[" not in segment:
            parts.append(segment)
            continue
        name, rest = segment.split("[", maxsplit=1)
        parts.append(name)
        index_text = rest.rstrip("]")
        if not index_text.isdecimal():
            msg = f"Unsupported blueprint array path segment: {segment}"
            raise LiveUploadError(msg)
        parts.append(index_text)
    return tuple(parts)


def _path_child(target: object, *, part: str, full_path: str) -> object:
    if isinstance(target, list):
        if not part.isdecimal():
            msg = f"Expected array index in blueprint path: {full_path}"
            raise LiveUploadError(msg)
        index = int(part)
        try:
            return cast("list[object]", target)[index]
        except IndexError as exc:
            msg_0 = f"Blueprint path index is out of range: {full_path}"
            raise LiveUploadError(msg_0) from exc
    if isinstance(target, dict):
        mapping = cast("Mapping[str, object]", target)
        if part not in mapping:
            msg = f"Blueprint path is missing segment {part}: {full_path}"
            raise LiveUploadError(msg)
        return mapping[part]
    msg = f"Blueprint path cannot descend into scalar: {full_path}"
    raise LiveUploadError(msg)


def _expanded_runtime_bindings(
    values: Mapping[str, object],
) -> dict[str, object]:
    bindings: dict[str, object] = {}
    for key, value in values.items():
        key_text = str(key)
        bindings[key_text] = value
        if not key_text.startswith("{{"):
            bindings[f"{{{{{key_text}}}}}"] = value
    return bindings


def _replace_exact_strings(
    value: object, replacements: Mapping[str, object]
) -> object:
    if isinstance(value, str):
        return replacements.get(value, value)
    if isinstance(value, dict):
        return {
            str(key): _replace_exact_strings(child, replacements)
            for key, child in cast("Mapping[object, object]", value).items()
        }
    if isinstance(value, list):
        return [
            _replace_exact_strings(child, replacements)
            for child in cast("list[object]", value)
        ]
    return value


def _unresolved_runtime_placeholders(value: object) -> set[str]:
    if isinstance(value, str):
        return set(re.findall(r"\{\{\s*runtime\.[^}]+\}\}", value))
    if isinstance(value, dict):
        result: set[str] = set()
        for child in cast("Mapping[object, object]", value).values():
            result.update(_unresolved_runtime_placeholders(child))
        return result
    if isinstance(value, list):
        result = set()
        for child in cast("list[object]", value):
            result.update(_unresolved_runtime_placeholders(child))
        return result
    return set()


def _scenario_note_payloads(
    scenario: Mapping[str, object],
) -> tuple[JsonObject, ...]:
    metadata = scenario.get("metadata")
    if not isinstance(metadata, dict):
        return ()
    source = cast("Mapping[str, object]", metadata)
    designer = source.get("designer")
    raw_containers: list[object] = [source.get("notes")]
    if isinstance(designer, dict):
        raw_containers.append(
            cast("Mapping[str, object]", designer).get("notes")
        )
    payloads: list[JsonObject] = []
    seen: set[str] = set()
    note_index = 0
    for raw_notes in raw_containers:
        if not isinstance(raw_notes, list | tuple):
            continue
        for note in cast("Sequence[object]", raw_notes):
            if not isinstance(note, dict):
                continue
            payload = _scenario_note_payload(
                note=cast("Mapping[str, object]", note),
                index=note_index,
            )
            note_index += 1
            fingerprint = json.dumps(
                payload, sort_keys=True, separators=(",", ":")
            )
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            payloads.append(payload)
    return tuple(payloads)


def _scenario_note_payload(
    *, note: Mapping[str, object], index: int
) -> JsonObject:
    content = _note_content(note=note, index=index)
    return {
        "content": content,
        "isFilterNote": note.get("isFilterNote") is True,
        "metadata": {"color": _note_color(note)},
        "moduleIds": list(_note_module_ids(note=note, index=index)),
    }


def _note_content(*, note: Mapping[str, object], index: int) -> str:
    content = note.get("content")
    if isinstance(content, str) and content.strip():
        return content
    msg = f"Scenario note {index + 1} is missing non-empty content."
    raise LiveUploadError(msg)


def _note_color(note: Mapping[str, object]) -> str:
    metadata = note.get("metadata")
    if isinstance(metadata, dict):
        color = cast("Mapping[str, object]", metadata).get("color")
        if (
            isinstance(color, str)
            and color.strip().upper() in MAKE_NOTE_COLOR_PALETTE
        ):
            return color.strip().upper()
    color = note.get("color")
    if (
        isinstance(color, str)
        and color.strip().upper() in MAKE_NOTE_COLOR_PALETTE
    ):
        return color.strip().upper()
    return MAKE_NOTE_DEFAULT_COLOR


def _note_module_ids(
    *, note: Mapping[str, object], index: int
) -> tuple[int, ...]:
    module_ids = note.get("moduleIds")
    if not isinstance(module_ids, list | tuple) or not module_ids:
        msg = f"Scenario note {index + 1} must include moduleIds."
        raise LiveUploadError(msg)
    normalized: list[int] = []
    for raw_id in cast("Sequence[object]", module_ids):
        module_id = _optional_positive_int(raw_id)
        if module_id is None:
            msg = f"Scenario note {index + 1} has a non-positive moduleId."
            raise LiveUploadError(msg)
        if module_id not in normalized:
            normalized.append(module_id)
    return tuple(normalized)


def _create_scenario_notes(
    *,
    client: MakeLiveClient,
    scenario_id: int,
    team_id: int,
    organization_id: int,
    scenario: Mapping[str, object],
    notes: tuple[JsonObject, ...],
) -> JsonObject:
    if not notes:
        return {"status": "no_notes", "created_count": 0}
    module_ids = _scenario_module_ids(scenario)
    for index, note in enumerate(notes):
        missing = tuple(
            module_id
            for module_id in cast("Sequence[object]", note["moduleIds"])
            if _optional_positive_int(module_id) not in module_ids
        )
        if missing:
            message = f"Scenario note {index + 1} references absent modules."
            raise LiveUploadError(message)
    _ = client.request_json(
        "POST",
        f"/scenarios/{scenario_id}/notes/batch",
        query={"organizationId": organization_id, "teamId": team_id},
        body={
            "delete": [],
            "update": [],
            "create": [dict(note) for note in notes],
        },
    )
    return {"status": "created", "created_count": len(notes)}


def _scenario_module_ids(scenario: Mapping[str, object]) -> frozenset[int]:
    module_ids: set[int] = set()
    _collect_scenario_module_ids(scenario.get("flow"), module_ids=module_ids)
    return frozenset(module_ids)


def _collect_scenario_module_ids(
    value: object, *, module_ids: set[int]
) -> None:
    if not isinstance(value, list | tuple):
        return
    for raw_node in cast("Sequence[object]", value):
        if not isinstance(raw_node, dict):
            continue
        node = cast("Mapping[str, object]", raw_node)
        module_id = _optional_positive_int(node.get("id"))
        if module_id is not None:
            module_ids.add(module_id)
        routes = node.get("routes")
        if isinstance(routes, list | tuple):
            for raw_route in cast("Sequence[object]", routes):
                if isinstance(raw_route, dict):
                    _collect_scenario_module_ids(
                        cast("Mapping[str, object]", raw_route).get("flow"),
                        module_ids=module_ids,
                    )
        _collect_scenario_module_ids(node.get("flow"), module_ids=module_ids)
        _collect_scenario_module_ids(node.get("onerror"), module_ids=module_ids)


def _optional_positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.isdecimal() and int(value) > 0:
        return int(value)
    return None


def _export_compare_status(
    *,
    client: MakeLiveClient,
    scenario_id: int,
    local_scenario: Mapping[str, object],
) -> str:
    response = client.request_json(
        "GET",
        f"/scenarios/{scenario_id}/blueprint",
        query={"draft": False},
    )
    response_payload = response.get("response")
    exported = (
        cast("Mapping[str, object]", response_payload).get("blueprint")
        if isinstance(response_payload, dict)
        else response.get("blueprint")
    )
    if not isinstance(exported, dict):
        return "export_unavailable"
    local_flow = local_scenario.get("flow")
    exported_flow = cast("Mapping[str, object]", exported).get("flow")
    if isinstance(local_flow, list) and isinstance(exported_flow, list):
        local_modules = cast("list[object]", local_flow)
        exported_modules = cast("list[object]", exported_flow)
        return (
            "passed"
            if len(local_modules) == len(exported_modules)
            else "module_count_mismatch"
        )
    return "export_shape_unexpected"


def _rollback_created(
    *, client: MakeLiveClient, created: Mapping[str, list[int]]
) -> None:
    scenarios = created.get("scenarios") or []
    webhooks = created.get("webhooks") or []
    data_stores = created.get("data_stores") or []
    data_structures = created.get("data_structures") or []
    for scenario_id in reversed(scenarios):
        _suppressing_live_error(client, "DELETE", f"/scenarios/{scenario_id}")
    for hook_id in reversed(webhooks):
        _suppressing_live_error(client, "DELETE", f"/hooks/{hook_id}")
    for store_id in reversed(data_stores):
        _suppressing_live_error(
            client,
            "DELETE",
            f"/data-stores/{store_id}",
            query={"confirmed": True},
        )
    for structure_id in reversed(data_structures):
        _suppressing_live_error(
            client,
            "DELETE",
            f"/data-structures/{structure_id}",
            query={"confirmed": True},
        )


def _suppressing_live_error(
    client: MakeLiveClient,
    method: str,
    path: str,
    *,
    query: Mapping[str, object] | None = None,
) -> None:
    try:
        _ = client.request_json(method, path, query=query)
    except LiveUploadError:
        return


def _resource_rows(
    bundle: Mapping[str, object], key: str
) -> tuple[JsonObject, ...]:
    section = _json_mapping(bundle[key], label=key)
    resources = section.get("resources")
    if not isinstance(resources, list | tuple):
        msg = f"{key}.resources must be an array."
        raise LiveUploadError(msg)
    rows = cast("Sequence[object]", resources)
    return tuple(_json_mapping(row, label=f"{key}.resources[]") for row in rows)


def _missing_bindings(
    requirements: tuple[JsonObject, ...],
    values: Mapping[str, object],
) -> tuple[str, ...]:
    missing: list[str] = []
    expanded = _expanded_runtime_bindings(values)
    for requirement in requirements:
        source = str(
            requirement.get("source")
            or requirement.get("bind_placeholder")
            or ""
        )
        if (
            source
            and source not in expanded
            and source.strip("{} ") not in expanded
        ):
            missing.append(source)
    return tuple(sorted(missing))


def _read_json_object(path: Path) -> JsonObject:
    if not path.exists():
        msg = f"Required live upload artifact is missing: {path}"
        raise LiveUploadError(msg)
    value = cast("object", json.loads(path.read_text(encoding="utf-8")))
    return _json_mapping(value, label=str(path))


def _assert_public_safe_live_upload_bundle(
    bundle: Mapping[str, object],
) -> None:
    package = _json_mapping(bundle["package"], label="package")
    blueprint = _json_mapping(
        package["blueprint_artifact_json"],
        label="blueprint_artifact_json",
    )
    scenario = _json_mapping(
        blueprint["scenario"], label="blueprint_artifact_json.scenario"
    )
    live_artifacts = (
        scenario,
        _json_mapping(bundle["datastructure"], label="datastructure"),
        _json_mapping(bundle["datastore"], label="datastore"),
        _json_mapping(bundle["webhook"], label="webhook"),
        _json_mapping(bundle["connections"], label="connections"),
        _json_mapping(bundle["runtime_values"], label="runtime_values"),
        _json_mapping(bundle["upload_plan"], label="upload_plan"),
    )
    try:
        assert_make_public_safe_artifact(
            scenario,
            artifact_kind="make_blueprint_json",
        )
        for artifact in live_artifacts[1:]:
            assert_make_public_safe_artifact(
                artifact,
                artifact_kind="make_live_resource_manifest",
            )
    except MakePublicSafeArtifactError as exc:
        raise LiveUploadError(str(exc)) from exc


def _json_mapping(value: object, *, label: str) -> JsonObject:
    if not isinstance(value, dict):
        msg = f"{label} must be a JSON object."
        raise LiveUploadError(msg)
    return cast("JsonObject", value)


def _extract_int(payload: Mapping[str, object], paths: tuple[str, ...]) -> int:
    for path in paths:
        value: object = payload
        for part in path.split("."):
            if not isinstance(value, dict) or part not in value:
                value = None
                break
            value = cast("Mapping[str, object]", value)[part]
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdecimal():
            return int(value)
    msg = f"Make API response did not include expected integer ID path: {paths}"
    raise LiveUploadError(msg)


def _int_binding(bindings: Mapping[str, object], *, key: str) -> int:
    value = bindings.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    msg = f"Missing integer binding: {key}"
    raise LiveUploadError(msg)


def _require_positive_int(value: int, *, label: str) -> None:
    if value <= 0:
        msg = f"{label} must be positive."
        raise LiveUploadError(msg)


def _positive_int_value(value: object, *, label: str) -> int:
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.isdecimal() and int(value) > 0:
        return int(value)
    msg = f"{label} must be a positive integer."
    raise LiveUploadError(msg)


def _reject_secret_like_payload(value: object, *, label: str) -> None:
    rendered = json.dumps(value, ensure_ascii=True, sort_keys=True)
    if SECRET_LIKE_PATTERN.search(rendered):
        msg = f"{label} contains secret-like material and cannot be uploaded."
        raise LiveUploadError(msg)


def _dynamic_api_key_policy() -> JsonObject:
    return {
        "api_key_source": "runtime_environment_or_stdin_only",
        "artifact_storage_allowed": False,
        "database_storage_allowed": False,
        "local_storage_allowed": False,
        "log_output_allowed": False,
        "recommended_env_var": "MAKE_API_TOKEN",
    }


def _body_bytes(body: JsonObject | None) -> bytes | None:
    if body is None:
        return None
    return json.dumps(body, ensure_ascii=True, sort_keys=True).encode("utf-8")


def _query_value(value: object) -> str:
    return str(value).lower() if isinstance(value, bool) else str(value)


def _http_error(exc: HTTPError, *, method: str, path: str) -> LiveUploadError:
    try:
        response_body = exc.read()
    finally:
        exc.close()
    return MakeLiveApiClient.format_http_error(
        status_code=exc.code,
        method=method,
        path=path,
        response_body=response_body,
    )


def _safe_http_error_detail(response_body: bytes) -> str:
    try:
        raw_payload = cast("object", json.loads(response_body.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ""
    if not isinstance(raw_payload, dict):
        return ""
    payload = cast("Mapping[str, object]", raw_payload)
    code = _safe_error_text(payload.get("code"), max_length=40)
    message = _safe_error_text(payload.get("message"), max_length=180)
    if code and message:
        return f"code {code}: {message}"
    if code:
        return f"code {code}"
    if message:
        return message
    return ""


def _safe_error_text(value: object, *, max_length: int) -> str:
    if not isinstance(value, str):
        return ""
    normalized = " ".join(value.strip().split())[:max_length]
    if not normalized or SECRET_LIKE_PATTERN.search(normalized):
        return ""
    return normalized


def _binding_arguments(values: Sequence[str]) -> JsonObject:
    bindings: JsonObject = {}
    for value in values:
        if "=" not in value:
            msg = "Binding arguments must use key=value syntax."
            raise LiveUploadError(msg)
        key, raw = value.split("=", maxsplit=1)
        key = key.strip()
        if not key:
            msg = "Binding keys cannot be empty."
            raise LiveUploadError(msg)
        bindings[key] = raw.strip()
    return bindings


def _runtime_token_from_environment(*, env_var: str, stdin_token: bool) -> str:
    if stdin_token:
        token = sys.stdin.read().strip()
        if token:
            return token
    return os.environ.get(env_var, "").strip()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Upload a Pancakes Make package to Make.com."
    )
    _ = parser.add_argument("--project-folder", required=True, type=Path)
    _ = parser.add_argument("--team-id", required=True, type=int)
    _ = parser.add_argument("--organization-id", required=True, type=int)
    _ = parser.add_argument(
        "--zone", default=os.environ.get("MAKE_ZONE", DEFAULT_ZONE)
    )
    _ = parser.add_argument("--apply", action="store_true")
    _ = parser.add_argument("--api-token-env", default="MAKE_API_TOKEN")
    _ = parser.add_argument("--api-token-stdin", action="store_true")
    _ = parser.add_argument("--connection", action="append", default=[])
    _ = parser.add_argument("--runtime-value", action="append", default=[])
    _ = parser.add_argument("--no-cleanup-on-failure", action="store_true")
    args = parser.parse_args(argv)

    apply_requested = bool(cast("object", args.apply))
    connection_bindings = _binding_arguments(
        cast("Sequence[str]", args.connection)
    )
    runtime_values = _binding_arguments(
        cast("Sequence[str]", args.runtime_value)
    )
    if not apply_requested:
        dry_run_project_upload(
            project_folder=cast("Path", args.project_folder),
            team_id=cast("int", args.team_id),
            organization_id=cast("int", args.organization_id),
            connection_bindings=connection_bindings,
            runtime_values=runtime_values,
        )
    else:
        token = _runtime_token_from_environment(
            env_var=cast("str", args.api_token_env),
            stdin_token=cast("bool", args.api_token_stdin),
        )
        client = MakeLiveApiClient(api_token=token, zone=cast("str", args.zone))
        apply_project_upload(
            project_folder=cast("Path", args.project_folder),
            team_id=cast("int", args.team_id),
            organization_id=cast("int", args.organization_id),
            client=client,
            connection_bindings=connection_bindings,
            runtime_values=runtime_values,
            cleanup_on_failure=not cast("bool", args.no_cleanup_on_failure),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
