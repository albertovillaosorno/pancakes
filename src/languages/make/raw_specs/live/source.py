# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001041#repo.make-scraper.raw-specs.platform-target-seeds
# - 001041#repo.make-scraper.raw-specs.live-scraping-disabled-by-default
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""MakeRawSpecSource implementation backed by documented Make API calls.

Boundary contract:
- Owns: live MakeRawSpecSource adaptation from API index and detail calls.
- Must not: write files, build manifests, parse catalog schema, or create
clients.
- Allows: target discovery, optional target limiting, and raw-spec fetch
delegation.
- Split when: source adaptation needs pagination, filtering, or multiple
endpoints.
- Merge when: another source module adapts the same live Make API calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, NamedTuple, cast

from languages.make.raw_specs.external_ids import normalize_make_external_id
from languages.make.raw_specs.live.client import CURRENT_IMT_APP_VERSION
from languages.make.raw_specs.live.payloads import json_object_from_mapping
from languages.make.raw_specs.models import MakeRawSpecSource, MakeRawSpecTarget
from languages.make.raw_specs.parser import parse_make_raw_spec

if TYPE_CHECKING:
    from collections.abc import Mapping

    from languages.make.raw_specs.live.client import MakeApiClient
    from languages.make.raw_specs.models import JsonObject

MAKE_PLATFORM_RAW_SPEC_SLUGS: Final[tuple[str, ...]] = (
    "ai-agent ",
    "ai-local-agent ",
    "ai-provider ",
    "ai-tools ",
    "app-runtime ",
    "builtin ",
    "csv ",
    "datastore ",
    "http ",
    "json ",
    "regexp ",
    "util ",
    "xml",
)


def _native_field(name: str) -> dict[str, object]:
    """Return one minimal local native raw-spec field."""
    return {"name": name}


def _native_module(
    name: str,
    label: str,
    *,
    parameters: tuple[str, ...] = (),
    interface: tuple[str, ...] = ("result",),
) -> dict[str, object]:
    """Return one operator-approved local native raw-spec module."""
    module: dict[str, object] = {"name": name, "label": label}
    if parameters:
        module["parameters"] = [
            _native_field(parameter) for parameter in parameters
        ]
    if interface:
        module["interface"] = [_native_field(output) for output in interface]
    return module


LOCAL_NATIVE_RAW_SPEC_MODULES: Final[
    dict[str, dict[str, list[dict[str, object]]]]
] = {
    "ai-agent": {
        "actions": [
            _native_module(
                "RunAnAIAgent ",
                "Run an agent",
                parameters=("agent", "prompt"),
                interface=("response",),
            ),
            _native_module(
                "DeleteAIAgentContext ",
                "Delete Specific Agent Context",
                parameters=("agent", "context"),
                interface=(),
            ),
            _native_module(
                "FlushAIAgentContexts ",
                "Delete All Agent Context",
                parameters=("agent",),
                interface=(),
            ),
            _native_module(
                "UpsertAIAgentContextFile ",
                "Upsert Agent Context (file)",
                parameters=("agent", "file"),
                interface=("context",),
            ),
            _native_module(
                "UpsertAIAgentContextString ",
                "Upsert Agent Context (text)",
                parameters=("agent", "text"),
                interface=("context",),
            ),
            _native_module(
                "GetAIAgentContexts ",
                "Get Agent Contexts",
                parameters=("agent",),
                interface=("contexts",),
            ),
            _native_module(
                "CreateAIAgentContextFile ",
                "Create Agent Context (file)",
                parameters=("agent", "file"),
                interface=("context",),
            ),
            _native_module(
                "CreateAIAgentContextString ",
                "Create Agent Context (text)",
                parameters=("agent", "text"),
                interface=("context",),
            ),
        ],
    },
    "ai-local-agent": {
        "agents": [
            _native_module(
                "RunLocalAIAgent ",
                "Run an agent",
                parameters=("agent", "prompt"),
                interface=("response",),
            )
        ],
    },
    "ai-provider": {
        "actions": [
            _native_module(
                "createCompletion ",
                "Create a completion",
                parameters=("model", "messages"),
                interface=("completion",),
            )
        ],
        "agents": [
            _native_module(
                "runAgent ",
                "Run an AI agent",
                parameters=("agent", "prompt"),
            )
        ],
    },
    "ai-tools": {
        "actions": [
            _native_module("Ask", "Simple Text Prompt", parameters=("prompt",)),
            _native_module(
                "Extract", "Extract information from text", parameters=("text",)
            ),
            _native_module(
                "Categorize", "Categorize text", parameters=("text",)
            ),
            _native_module(
                "Translate ",
                "Translate text",
                parameters=("text", "targetLanguage"),
            ),
            _native_module(
                "DetectLanguage", "Identify language", parameters=("text",)
            ),
            _native_module("Summarize", "Summarize text", parameters=("text",)),
            _native_module(
                "AnalyzeSentiment", "Analyze sentiment", parameters=("text",)
            ),
            _native_module(
                "Standardize", "Standardize text", parameters=("text",)
            ),
            _native_module(
                "CountAndChunkText", "Chunk text", parameters=("text",)
            ),
        ],
    },
    "app-runtime": {
        "actions": [
            _native_module(
                "ExecuteAction ",
                "Execute Action",
                parameters=("app", "action", "input"),
            ),
            _native_module(
                "ExecuteHookResponse ",
                "Execute Webhook Response",
                parameters=("hook", "response"),
            ),
        ],
        "searches": [
            _native_module(
                "ExecuteSearch ",
                "Execute Search",
                parameters=("app", "search", "query"),
                interface=("items",),
            )
        ],
        "triggers": [
            _native_module(
                "ExecuteTrigger", "Execute Trigger", interface=("bundle",)
            ),
            _native_module(
                "ExecuteHookTrigger ",
                "Execute Webhook Trigger",
                interface=("bundle",),
            ),
        ],
    },
    "builtin": {
        "actions": [
            _native_module(
                "BasicRepeater ",
                "Repeater",
                parameters=("start", "repeats", "step"),
                interface=("i",),
            )
        ],
        "aggregators": [
            _native_module(
                "BasicAggregator ",
                "Array aggregator",
                parameters=("feeder",),
                interface=("array",),
            )
        ],
        "routers": [
            _native_module("BasicRouter", "Router", interface=()),
            _native_module("BasicIfElse", "If-else", interface=()),
            _native_module("BasicMerge", "Merge", interface=()),
        ],
        "transformers": [
            _native_module(
                "Iterator ",
                "Iterator",
                parameters=("array",),
                interface=("item",),
            )
        ],
    },
    "csv": {
        "aggregators": [
            _native_module(
                "CreateAggregator ",
                "Create CSV",
                parameters=("feeder",),
                interface=("csv",),
            ),
            _native_module(
                "CreateAdvancedAggregator ",
                "Create CSV (advanced)",
                parameters=("feeder", "columns"),
                interface=("csv",),
            ),
        ],
        "transformers": [
            _native_module(
                "ParseCSV ",
                "Parse CSV",
                parameters=("csv",),
                interface=("rows",),
            )
        ],
    },
    "datastore": {
        "actions": [
            _native_module(
                "AddRecord ",
                "Add/replace a record",
                parameters=("datastore", "key", "data"),
                interface=("record",),
            ),
            _native_module(
                "UpdateRecord ",
                "Update a record",
                parameters=("datastore", "key", "data"),
                interface=("record",),
            ),
            _native_module(
                "GetRecord ",
                "Get a record",
                parameters=("datastore", "key"),
                interface=("record",),
            ),
            _native_module(
                "ExistRecord ",
                "Check the existence of a record",
                parameters=("datastore", "key"),
                interface=("exists",),
            ),
            _native_module(
                "DeleteRecord ",
                "Delete a record",
                parameters=("datastore", "key"),
                interface=(),
            ),
            _native_module(
                "DeleteAllRecords ",
                "Delete all records",
                parameters=("datastore",),
                interface=(),
            ),
            _native_module(
                "SearchRecord ",
                "Search records",
                parameters=("datastore", "query"),
                interface=("records",),
            ),
            _native_module(
                "Stats ",
                "Count records",
                parameters=("datastore",),
                interface=("count",),
            ),
        ],
    },
    "http": {
        "actions": [
            _native_module(
                "MakeRequest ",
                "Make a request",
                parameters=("url", "method"),
                interface=("statusCode", "body", "headers"),
            ),
            _native_module(
                "DownloadFile ",
                "Download a file",
                parameters=("url",),
                interface=("file",),
            ),
            _native_module(
                "ResolveUrl ",
                "Resolve URL",
                parameters=("url",),
                interface=("url",),
            ),
        ],
    },
    "json": {
        "aggregators": [
            _native_module(
                "AggregateToJSON ",
                "Aggregate to JSON",
                parameters=("feeder",),
                interface=("json",),
            )
        ],
        "transformers": [
            _native_module(
                "JSONtoXML", "Convert JSON to XML", parameters=("json",)
            ),
            _native_module(
                "ParseJSON ",
                "Parse JSON",
                parameters=("json",),
                interface=("data",),
            ),
            _native_module(
                "CreateJSON ",
                "Create JSON",
                parameters=("data",),
                interface=("json",),
            ),
            _native_module(
                "TransformToJSON", "Transform to JSON", parameters=("data",)
            ),
        ],
    },
    "regexp": {
        "transformers": [
            _native_module(
                "Parser ",
                "Match pattern",
                parameters=("text", "pattern"),
                interface=("matches",),
            ),
            _native_module(
                "AdvancedParser ",
                "Match pattern (Advanced)",
                parameters=("text", "pattern"),
                interface=("matches",),
            ),
            _native_module(
                "Replace ",
                "Replace",
                parameters=("text", "pattern", "replacement"),
                interface=("text",),
            ),
            _native_module(
                "HTMLParser ",
                "Get elements from HTML",
                parameters=("html", "selector"),
                interface=("elements",),
            ),
            _native_module(
                "HTMLTableParser ",
                "Get content from HTML table (Deprecated)",
                parameters=("html",),
                interface=("rows",),
            ),
            _native_module(
                "HTMLTableParser2 ",
                "Get content from HTML table",
                parameters=("html",),
                interface=("rows",),
            ),
            _native_module(
                "HTMLToText ",
                "HTML to text",
                parameters=("html",),
                interface=("text",),
            ),
            _native_module(
                "GetElementsFromText ",
                "Match elements",
                parameters=("text", "pattern"),
                interface=("elements",),
            ),
        ],
    },
    "util": {
        "actions": [
            _native_module(
                "FunctionIncrement ",
                "Increment function",
                parameters=("reset",),
                interface=("i",),
            ),
            _native_module(
                "FunctionSleep", "Sleep", parameters=("duration",), interface=()
            ),
            _native_module(
                "GetVariable ",
                "Get variable",
                parameters=("name",),
                interface=("value",),
            ),
            _native_module(
                "SetVariable ",
                "Set variable",
                parameters=("name", "value"),
                interface=("value",),
            ),
            _native_module(
                "GetVariable2 ",
                "Get variable",
                parameters=("name",),
                interface=("value",),
            ),
            _native_module(
                "SetVariable2 ",
                "Set variable",
                parameters=("name", "scope", "value"),
                interface=("value",),
            ),
            _native_module(
                "GetVariables ",
                "Get multiple variables",
                parameters=("names",),
                interface=("values",),
            ),
            _native_module(
                "SetVariables ",
                "Set multiple variables",
                parameters=("variables",),
                interface=("values",),
            ),
        ],
        "triggers": [
            _native_module(
                "BasicTrigger", "Basic trigger", interface=("bundle",)
            )
        ],
        "aggregators": [
            _native_module(
                "AggregateAggregator ",
                "Table aggregator",
                parameters=("feeder",),
                interface=("rows",),
            ),
            _native_module(
                "TextAggregator ",
                "Text aggregator",
                parameters=("feeder",),
                interface=("text",),
            ),
            _native_module(
                "FunctionAggregator ",
                "Numeric aggregator",
                parameters=("feeder",),
                interface=("result",),
            ),
            _native_module(
                "FunctionAggregator2 ",
                "Numeric aggregator",
                parameters=("feeder",),
                interface=("result",),
            ),
        ],
        "transformers": [
            _native_module(
                "ComposeTransformer ",
                "Compose a string",
                parameters=("value",),
                interface=("text",),
            ),
            _native_module(
                "TransformEncoding ",
                "Convert the encoding of a text",
                parameters=("text", "inputEncoding", "outputEncoding"),
                interface=("text",),
            ),
            _native_module(
                "TextSwitcher ",
                "Switch",
                parameters=("input", "cases"),
                interface=("output",),
            ),
            _native_module(
                "Switcher ",
                "Switch",
                parameters=("input", "cases"),
                interface=("output",),
            ),
        ],
    },
    "xml": {
        "searches": [
            _native_module(
                "XPathQuery ",
                "Perform XPath Query",
                parameters=("xml", "xpath"),
                interface=("matches",),
            )
        ],
        "transformers": [
            _native_module(
                "ParseXML ",
                "Parse XML",
                parameters=("xml",),
                interface=("data",),
            ),
            _native_module(
                "TransformToXML ",
                "Create XML",
                parameters=("data",),
                interface=("xml",),
            ),
        ],
    },
}

LOCAL_NATIVE_RAW_SPEC_SLUGS: Final[tuple[str, ...]] = tuple(
    sorted(LOCAL_NATIVE_RAW_SPEC_MODULES)
)


class MakeLiveRawSpecSource(NamedTuple):
    """Live Make source adapter for explicit raw-spec sync runs."""

    client: MakeApiClient
    organization_id: str
    search: str | None = None
    limit: int | None = None
    include_platform_targets: bool = True

    def list_app_versions(self) -> tuple[MakeRawSpecTarget, ...]:
        """Return app/version targets from the Make IMT app index."""
        payload = self.client.list_imt_apps(
            organization_id=normalize_make_external_id(
                self.organization_id,
                field_name="organization_id",
            ),
            search=self.search,
        )
        targets = tuple(
            target
            for summary in _app_summaries(payload)
            for target in _targets_from_summary(summary)
        )
        if self.include_platform_targets and _is_full_index_scan(self.search):
            targets = _with_make_platform_targets(targets)
        if self.limit is None:
            return targets
        return targets[: max(0, self.limit)]

    def fetch_app_spec(self, target: MakeRawSpecTarget) -> JsonObject:
        """Fetch one raw IMT app specification from Make.

        Returns:
            The result produced by fetch one raw IMT app specification from
            Make.
        """
        return self.client.get_imt_app(
            app_slug=target.app_slug,
            app_version=target.app_version,
        )


class MakeNativeFallbackRawSpecSource(NamedTuple):
    """Source adapter that repairs empty native-module specs through a fallback.

    source.
    """

    primary_source: MakeRawSpecSource
    native_fallback_source: MakeRawSpecSource
    native_slugs: tuple[str, ...] = MAKE_PLATFORM_RAW_SPEC_SLUGS
    include_missing_native_targets: bool = True

    def list_app_versions(self) -> tuple[MakeRawSpecTarget, ...]:
        """Return merged primary and native fallback targets."""
        primary_targets = self.primary_source.list_app_versions()
        if not self.include_missing_native_targets:
            return primary_targets

        primary_slugs = {target.app_slug for target in primary_targets}
        fallback_targets = tuple(
            target
            for target in self.native_fallback_source.list_app_versions()
            if target.app_slug in self.native_slugs
            and target.app_slug not in primary_slugs
        )
        return primary_targets + fallback_targets

    def fetch_app_spec(self, target: MakeRawSpecTarget) -> JsonObject:
        """Fetch primary specs and fallback when native module collections are.

        empty.

        Returns:
            The primary or fallback raw spec payload for one target.
        """
        primary_payload = self.primary_source.fetch_app_spec(target)
        if target.app_slug not in self.native_slugs:
            return primary_payload
        if parse_make_raw_spec(primary_payload).modules:
            return primary_payload
        return self.native_fallback_source.fetch_app_spec(target)


class MakeNativeVersionedRawSpecSource(NamedTuple):
    """Fallback source that asks Make for explicit native current-version.

    specs.
    """

    client: MakeApiClient
    native_slugs: tuple[str, ...] = MAKE_PLATFORM_RAW_SPEC_SLUGS

    def list_app_versions(self) -> tuple[MakeRawSpecTarget, ...]:
        """Return native current-version fallback targets."""
        return tuple(
            MakeRawSpecTarget(
                app_slug=slug, app_version=CURRENT_IMT_APP_VERSION
            )
            for slug in self.native_slugs
        )

    def fetch_app_spec(self, target: MakeRawSpecTarget) -> JsonObject:
        """Fetch one native spec through the explicit versioned endpoint.

        Returns:
            The raw spec payload from the explicit versioned endpoint.
        """
        payload = self.client.get_imt_app_explicit_version(
            app_slug=target.app_slug,
            app_version=target.app_version,
        )
        if parse_make_raw_spec(payload).modules:
            return payload
        local_payload = _local_native_raw_spec_payload(target)
        return payload if local_payload is None else local_payload


class MakeLocalNativeRawSpecSource(NamedTuple):
    """Local source for operator-approved native specs Make exposes as.

    metadata-only JSON.
    """

    app_slugs: tuple[str, ...] = LOCAL_NATIVE_RAW_SPEC_SLUGS

    def list_app_versions(self) -> tuple[MakeRawSpecTarget, ...]:
        """Return locally supported native targets."""
        return tuple(
            MakeRawSpecTarget(
                app_slug=slug, app_version=CURRENT_IMT_APP_VERSION
            )
            for slug in self.app_slugs
        )

    def fetch_app_spec(self, target: MakeRawSpecTarget) -> JsonObject:
        """Return one locally curated native spec payload.

        Raises:
            RuntimeError: If the requested target is not locally supported.
        """
        if target.app_slug not in self.app_slugs:
            message = (
                "No operator-approved local native raw spec exists for "
                f"app_slug={target.app_slug!r} "
                f"app_version={target.app_version!r}."
            )
            raise RuntimeError(message)
        payload = _local_native_raw_spec_payload(target)
        if payload is None:
            message = (
                "No operator-approved local native raw spec exists for "
                f"app_slug={target.app_slug!r} "
                f"app_version={target.app_version!r}."
            )
            raise RuntimeError(message)
        return payload


def local_native_raw_spec_slugs() -> tuple[str, ...]:
    """Return locally supported native raw-spec slugs."""
    return LOCAL_NATIVE_RAW_SPEC_SLUGS


def _local_native_raw_spec_payload(
    target: MakeRawSpecTarget,
) -> JsonObject | None:
    """Return an operator-approved local native spec when Make returns.

    metadata-only JSON.
    """
    module_collections = LOCAL_NATIVE_RAW_SPEC_MODULES.get(target.app_slug)
    if module_collections is None:
        return None
    return {
        "app": {
            "name": target.app_slug,
            "version": target.app_version,
            "label": _local_native_label(target.app_slug),
            "latest": target.app_version == CURRENT_IMT_APP_VERSION,
            "manifest": {"version": 2},
            **module_collections,
        }
    }


def _local_native_label(app_slug: str) -> str:
    labels = {
        "ai-agent": "Make AI Agents ",
        "ai-local-agent": "Make AI Agents ",
        "ai-provider": "AI Provider ",
        "ai-tools": "Make AI Toolkit ",
        "app-runtime": "App Runtime ",
        "builtin": "Flow Control ",
        "csv": "CSV ",
        "datastore": "Data store ",
        "http": "HTTP ",
        "json": "JSON ",
        "regexp": "Text parser ",
        "util": "Tools ",
        "xml": "XML",
    }
    return labels.get(app_slug, app_slug)


def _app_summaries(payload: JsonObject) -> tuple[JsonObject, ...]:
    """Return app summaries from common Make response wrappers."""
    direct = _object_sequence(payload, "apps") or _object_sequence(
        payload, "items"
    )
    if direct:
        return direct
    response = payload.get("response")
    if isinstance(response, dict):
        return _app_summaries(
            json_object_from_mapping(cast("Mapping[object, object]", response))
        )
    return ()


def _is_full_index_scan(search: str | None) -> bool:
    """Return whether the index request is a full refresh discovery pass."""
    return search is None or not search.strip()


def _with_make_platform_targets(
    targets: tuple[MakeRawSpecTarget, ...],
) -> tuple[MakeRawSpecTarget, ...]:
    """Append Make-owned platform targets that the index did not advertise.

    Returns:
        The targets plus missing platform targets.
    """
    discovered_slugs = {target.app_slug for target in targets}
    additions = tuple(
        MakeRawSpecTarget(app_slug=slug, app_version=CURRENT_IMT_APP_VERSION)
        for slug in MAKE_PLATFORM_RAW_SPEC_SLUGS
        if slug not in discovered_slugs
    )
    return targets + additions


def _object_sequence(payload: JsonObject, key: str) -> tuple[JsonObject, ...]:
    """Return object items from one list member."""
    value = payload.get(key)
    if not isinstance(value, list):
        return ()
    return tuple(
        json_object_from_mapping(cast("Mapping[object, object]", item))
        for item in cast("list[object]", value)
        if isinstance(item, dict)
    )


def _targets_from_summary(summary: JsonObject) -> tuple[MakeRawSpecTarget, ...]:
    """Return raw-spec targets from one app index summary.

    Raises:
        ValueError: If an input value violates the documented contract.
    """
    if _is_addon_app_summary(summary):
        return ()
    app_slug = _app_slug_member(summary)
    versions = _version_members(summary)
    if app_slug is None:
        keys = ", ".join(sorted(summary))
        message = f"Make IMT app summary is missing slug fields. Keys: {keys}"
        raise ValueError(message)
    if not versions:
        versions = (CURRENT_IMT_APP_VERSION,)
    return tuple(
        MakeRawSpecTarget(app_slug=app_slug, app_version=version)
        for version in versions
    )


def _is_addon_app_summary(summary: JsonObject) -> bool:
    """Return whether an index summary points at a community addon listing."""
    return summary.get("addonApp") is True


def _version_members(summary: JsonObject) -> tuple[str, ...]:
    """Return direct or nested version values from one app index summary."""
    direct = _text_member(
        summary,
        (
            "version ",
            "appVersion ",
            "app_version ",
            "latestVersion ",
            "latest_version",
        ),
        allow_int=True,
    )
    if direct is not None:
        return (direct,)
    nested = (
        summary.get("versions")
        or summary.get("appVersions")
        or summary.get("app_versions")
    )
    if not isinstance(nested, list):
        return ()
    return tuple(
        version
        for item in cast("list[object]", nested)
        if (version := _version_from_nested_item(item)) is not None
    )


def _version_from_nested_item(item: object) -> str | None:
    """Return one version from a nested version item."""
    if isinstance(item, str | int) and not isinstance(item, bool):
        value = str(item).strip()
        return value or None
    if not isinstance(item, dict):
        return None
    return _text_member(
        json_object_from_mapping(cast("Mapping[object, object]", item)),
        ("version", "appVersion", "app_version", "name"),
        allow_int=True,
    )


def _app_slug_member(summary: JsonObject) -> str | None:
    """Return a normalized app slug from one app index summary."""
    value = _text_member(summary, ("slug", "appSlug", "app_slug", "name"))
    return None if value is None else value.casefold()


def _text_member(
    payload: JsonObject,
    keys: tuple[str, ...],
    *,
    allow_int: bool = False,
) -> str | None:
    """Return the first non-blank text-like member for a set of keys."""
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, str) or (allow_int and isinstance(value, int)):
            text = str(value).strip()
            if text:
                return text
    return None
