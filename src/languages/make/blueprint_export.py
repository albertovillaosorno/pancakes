# Repository header: begin
# Provenance source mode: source_refs
# - 001060#repo.architecture.ports-adapters.boundary-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Render Pancakes AST drafts into Make-native blueprint JSON.

Boundary contract:
- Owns: Make-specific blueprint export shape, module token translation, version
injection,
  designer metadata, and zero-trace privacy checks.
- Must not: define generic AST semantics, call live Make services, persist
artifacts, or claim
  compatibility with non-Make providers.
- Allows: deterministic offline rendering from validated Pancakes AST data and
catalog evidence.
- Split when: another source language gains its own exporter under
`src/languages/**`.
- Merge when: another Make exporter duplicates this exact import-shape contract.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, cast

from blueprints.ast.phase_gates import (
    PHASE_RENDER,
    BlueprintPhaseDiagnostic,
    BlueprintPhaseGateError,
    BlueprintPhaseGateReport,
    phase_gate_from_validation_report,
)
from blueprints.ast.resolution import RESOLVED_STATUS, resolve_ast_modules
from blueprints.ast.traversal import iter_ast_nodes
from blueprints.validation.generation_gate import guard_blueprint_for_render

from languages.make.builtins import (
    make_builtin_module_ids_for_tokens,
    with_make_builtin_modules,
)
from languages.make.evidence import (
    make_evidence_entry,
    make_internal_evidence_ledger,
)
from languages.make.layout import plan_make_blueprint_layout
from languages.make.module_manifests import (
    make_module_manifest_connection_families,
    make_module_manifest_fixed_version,
    make_module_manifest_policy_required_keys,
    make_module_projector_kind,
    make_module_projector_manifest_for_native_token,
)
from languages.make.notes import (
    MAKE_NOTE_COLOR_PALETTE,
    MAKE_NOTE_DEFAULT_COLOR,
)
from languages.make.parameter_aliases import (
    make_connection_parameter_aliases_for_field,
    make_connection_parameter_target_for_field,
)

if TYPE_CHECKING:
    from blueprints.ast.layout_planner import BlueprintNodeLayout
    from blueprints.ast.models import (
        JsonObject,
        MakeAstFilter,
        MakeAstNode,
        MakeAstRoot,
        MakeAstRoute,
    )
    from blueprints.ast.resolution import MakeAstModuleResolution
    from blueprints.validation.models import (
        BlueprintGenerationBlocker,
        BlueprintGenerationGateReport,
    )
    from catalog.knowledge import KnowledgeStoreQuery
    from catalog.models import CatalogField, CatalogModule, CatalogSnapshot

type MakeBlueprintRenderMode = Literal["importable", "draft"]
type MakeBlueprintPlaceholderMode = Literal["runtime", "mock_import_values"]

DIRECT_ERROR_KEY_ORDER: Final[tuple[str, ...]] = ("onerror", "on_error")
DIRECT_ERROR_KEYS: Final[frozenset[str]] = frozenset(DIRECT_ERROR_KEY_ORDER)
MAKE_BLUEPRINT_PLACEHOLDER_MODES: Final[frozenset[str]] = frozenset(
    (
        "runtime ",
        "mock_import_values",
    )
)
MAKE_NATIVE_NODE_METADATA_KEYS: Final[tuple[str, ...]] = (
    "designer ",
    "restore ",
    "parameters ",
    "expect ",
    "interface ",
    "advanced",
)
MAKE_NATIVE_ROOT_METADATA_KEYS: Final[tuple[str, ...]] = (
    "instant ",
    "version ",
    "scenario ",
    "designer ",
    "zone ",
    "notes",
)
DEFAULT_MAKE_ROOT_METADATA_VERSION: Final = 1
DEFAULT_MAKE_MODULE_VERSION: Final = 1
PANCAKES_PRIVATE_METADATA_KEYS: Final[frozenset[str]] = frozenset(
    (
        "access_token ",
        "accesstoken ",
        "api_key ",
        "apikey ",
        "audit_posture ",
        "authorization ",
        "backpressure ",
        "client_handoff ",
        "client_secret ",
        "credential ",
        "delivery_mode ",
        "error_handling ",
        "idempotency_key ",
        "password ",
        "payload_budget ",
        "placeholder_registry ",
        "raw_spec ",
        "rollback_posture ",
        "runtime_connection ",
        "runtime_placeholders ",
        "scenario_tests ",
        "secret ",
        "token ",
        "transaction ",
        "webhook",
    )
)
PANCAKES_PRIVATE_KEY_PREFIXES: Final[tuple[str, ...]] = (
    "pancakes ",
    "sre_",
    "x-pancakes",
)
PASS_THROUGH_STRIPPED_METADATA_KEYS: Final[frozenset[str]] = frozenset(
    (
        "audit_posture ",
        "backpressure ",
        "client_handoff ",
        "delivery_mode ",
        "error_handling ",
        "idempotency_key ",
        "payload_budget ",
        "placeholder_registry ",
        "raw_spec ",
        "rollback_posture ",
        "runtime_connection ",
        "runtime_placeholders ",
        "scenario_tests ",
        "transaction ",
        "webhook",
    )
)
PANCAKES_PRIVATE_TEXT_PATTERNS: Final[tuple[str, ...]] = (
    "api key ",
    "apikey ",
    "access token ",
    "accesstoken ",
    "blueprints.ast ",
    "credential value ",
    "draft_id ",
    "languages/make ",
    "local-only ",
    "local draft ",
    "pancakes ",
    "project_id ",
    "runtime placeholder ",
    "schoenwald ",
    "secret ",
    "source_draft",
    "/mnt/",
)
PANCAKES_PRIVATE_TEXT_REGEXES: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\b[a-z]:\\", re.IGNORECASE),
)
RUNTIME_PLACEHOLDER_PATTERN: Final = re.compile(
    r"\{\{runtime\.([A-Za-z0-9_.-]+)}}"
)
FLOW_CONTROL_PROJECTOR_KINDS: Final[frozenset[str]] = frozenset(
    (
        "basic_repeater ",
        "function_increment ",
        "function_sleep ",
        "get_variable ",
        "set_variable",
    )
)


class _RenderContext(NamedTuple):
    """Context shared by Make blueprint export helpers."""

    mode: MakeBlueprintRenderMode
    modules_by_id: dict[str, CatalogModule]
    resolutions_by_source_path: dict[
        tuple[object, ...], MakeAstModuleResolution
    ]
    layouts_by_source_path: dict[tuple[object, ...], BlueprintNodeLayout]


class MakeBlueprintRenderReport(NamedTuple):
    """Rendered Make blueprint payload plus validation gate evidence."""

    mode: MakeBlueprintRenderMode
    payload: JsonObject
    gate: BlueprintGenerationGateReport
    phase_gates: tuple[BlueprintPhaseGateReport, ...] = ()
    pass_through_unknown_modules: tuple[JsonObject, ...] = ()
    internal_evidence_ledger: JsonObject | None = None

    @property
    def importable(self) -> bool:
        """Return whether the payload is safe to import into Make."""
        return self.mode == "importable" and self.gate.can_render


class MakeBlueprintRenderError(BlueprintPhaseGateError):
    """Raised when importable Make rendering is blocked by validation."""

    def __init__(
        self,
        blockers: tuple[BlueprintGenerationBlocker, ...],
        *,
        diagnostics: tuple[BlueprintPhaseDiagnostic, ...],
    ) -> None:
        """Store generation blockers with the render error."""
        super().__init__(phase=PHASE_RENDER, diagnostics=diagnostics)
        self.blockers = blockers


class MakeBlueprintPrivateMetadataLeakError(ValueError):
    """Raised when an importable Make payload still contains Pancakes-private.

    keys.
    """

    def __init__(self, paths: tuple[str, ...]) -> None:
        """Store private leak paths with the render error."""
        preview = ", ".join(paths[:5])
        message = (
            f"Importable Make blueprint leaked Pancakes-private metadata:"
            f"{preview}"
        )
        super().__init__(message)
        self.paths = paths


def render_make_blueprint_payload(
    *,
    root: MakeAstRoot,
    catalog: CatalogSnapshot,
    mode: MakeBlueprintRenderMode = "importable",
    placeholder_mode: MakeBlueprintPlaceholderMode = "runtime",
    knowledge: KnowledgeStoreQuery | None = None,
) -> MakeBlueprintRenderReport:
    """Render a Pancakes AST root to Make blueprint JSON.

    Returns:
        The rendered Make blueprint payload.

    Raises:
        MakeBlueprintRenderError: If strict Make rendering is blocked.
        ValueError: If a value violates the expected contract.
    """
    if mode not in {"importable", "draft"}:
        message = f"Unsupported Make blueprint render mode: {mode!r}"
        raise ValueError(message)
    if placeholder_mode not in MAKE_BLUEPRINT_PLACEHOLDER_MODES:
        message = (
            f"Unsupported Make blueprint placeholder mode: {placeholder_mode!r}"
        )
        raise ValueError(message)
    catalog = with_make_builtin_modules(
        catalog,
        module_ids=_make_builtin_module_ids_for_root(root),
    )
    gate = guard_blueprint_for_render(
        root=root, catalog=catalog, knowledge=knowledge
    )
    render_phase_gate = phase_gate_from_validation_report(
        phase=PHASE_RENDER,
        report=gate.validation_report,
    )
    if mode == "importable" and not gate.can_render:
        raise MakeBlueprintRenderError(
            gate.blockers,
            diagnostics=render_phase_gate.diagnostics,
        )
    context = _build_render_context(root=root, catalog=catalog, mode=mode)
    payload = _copy_json_object(root.raw_payload)
    payload["name"] = root.scenario.name
    payload["flow"] = [
        _render_node(node, context=context) for node in root.flow
    ]
    payload["metadata"] = _render_root_metadata(root=root, context=context)
    if mode == "importable" and placeholder_mode == "mock_import_values":
        payload = _mock_runtime_placeholders_for_import_preview(payload)
    if mode == "importable":
        _assert_no_private_metadata_leak(payload)
    return MakeBlueprintRenderReport(
        mode=mode,
        payload=payload,
        gate=gate,
        phase_gates=(render_phase_gate,),
        pass_through_unknown_modules=_pass_through_unknown_modules(
            root=root,
            context=context,
        ),
        internal_evidence_ledger=_make_export_internal_evidence_ledger(
            root=root,
            context=context,
            gate=gate,
            phase_gate=render_phase_gate,
        ),
    )


def render_make_blueprint_json_text(
    *,
    root: MakeAstRoot,
    catalog: CatalogSnapshot,
    mode: MakeBlueprintRenderMode = "importable",
    placeholder_mode: MakeBlueprintPlaceholderMode = "runtime",
    knowledge: KnowledgeStoreQuery | None = None,
) -> str:
    """Render a Pancakes AST root to deterministic Make blueprint JSON text.

    Returns:
        The deterministic JSON text rendered from the Make blueprint payload.
    """
    result = render_make_blueprint_payload(
        root=root,
        catalog=catalog,
        mode=mode,
        placeholder_mode=placeholder_mode,
        knowledge=knowledge,
    )
    return json.dumps(result.payload, indent=2, sort_keys=True)


def _build_render_context(
    *,
    root: MakeAstRoot,
    catalog: CatalogSnapshot,
    mode: MakeBlueprintRenderMode,
) -> _RenderContext:
    """Return Make export context for draft or importable output."""
    if mode == "draft":
        return _RenderContext(
            mode=mode,
            modules_by_id={},
            resolutions_by_source_path={},
            layouts_by_source_path={},
        )
    nodes = tuple(iter_ast_nodes(root))
    catalog = with_make_builtin_modules(
        catalog,
        module_ids=_make_builtin_module_ids_for_nodes(nodes),
    )
    resolution_report = resolve_ast_modules(root=root, catalog=catalog)
    layout_plan = plan_make_blueprint_layout(root)
    return _RenderContext(
        mode=mode,
        modules_by_id=_catalog_modules_by_id(catalog),
        resolutions_by_source_path={
            node.source_trace.path: resolution
            for node, resolution in zip(
                (node for node in nodes if node.module_token),
                resolution_report.resolutions,
                strict=True,
            )
        },
        layouts_by_source_path={
            layout.source_path: layout for layout in layout_plan.layouts
        },
    )


def _catalog_modules_by_id(
    catalog: CatalogSnapshot,
) -> dict[str, CatalogModule]:
    """Return catalog modules keyed by stable catalog module ID."""
    return {
        module.module_id: module
        for app in catalog.apps
        for version in app.versions
        for module in version.modules
    }


def _make_builtin_module_ids_for_root(root: MakeAstRoot) -> tuple[str, ...]:
    """Return Make built-in module IDs referenced by one AST root."""
    return _make_builtin_module_ids_for_nodes(tuple(iter_ast_nodes(root)))


def _make_builtin_module_ids_for_nodes(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[str, ...]:
    """Return Make built-in module IDs referenced by AST nodes."""
    return make_builtin_module_ids_for_tokens(
        tuple(node.module_token for node in nodes)
    )


def _pass_through_unknown_modules(
    *,
    root: MakeAstRoot,
    context: _RenderContext,
) -> tuple[JsonObject, ...]:
    """Return resolved modules preserved without a Make-native projector.

    manifest.
    """
    modules: list[JsonObject] = []
    for node in iter_ast_nodes(root):
        module = _resolved_catalog_module(node=node, context=context)
        if module is None:
            continue
        native_token = f"{module.app_slug}:{module.internal_name}"
        if (
            make_module_projector_manifest_for_native_token(native_token)
            is not None
        ):
            continue
        modules.append(
            {
                "node_id": _json_node_id(node.node_id),
                "module": native_token,
                "version": _render_module_version(
                    node=node,
                    module=module,
                    native_token=native_token,
                    manifest=None,
                ),
                "preservation_status": "unsupported_but_preserved ",
                "native_parity_category": "pass_through_unknown_module",
            }
        )
    return tuple(modules)


def _make_export_internal_evidence_ledger(
    *,
    root: MakeAstRoot,
    context: _RenderContext,
    gate: BlueprintGenerationGateReport,
    phase_gate: BlueprintPhaseGateReport,
) -> JsonObject:
    """Return private evidence rows for Make export judgments."""
    entries: list[JsonObject] = [
        make_evidence_entry(
            evidence_type="zero_trace_rule",
            judgment="make_blueprint_export_zero_trace_gate",
            source_id="languages.make.blueprint_export",
            rule_id="make.zero_trace.private_metadata_and_trace_text",
            confidence="hard_gate",
            detail={
                "importable": gate.can_render,
                "render_phase": phase_gate.phase,
                "render_phase_passed": phase_gate.passed,
            },
        )
    ]
    for node in iter_ast_nodes(root):
        module = _resolved_catalog_module(node=node, context=context)
        if module is None:
            continue
        native_token = f"{module.app_slug}:{module.internal_name}"
        catalog_module_id = node.raw_spec_binding.catalog_module_id
        if catalog_module_id is not None:
            entries.append(
                make_evidence_entry(
                    evidence_type="raw_spec_record",
                    judgment="module_resolution",
                    source_id=catalog_module_id,
                    module=native_token,
                    confidence="catalog_bound",
                )
            )
        manifest = make_module_projector_manifest_for_native_token(native_token)
        if manifest is None:
            entries.append(
                make_evidence_entry(
                    evidence_type="pass_through_unknown_module",
                    judgment="preserve_without_native_parity_claim",
                    source_id=native_token,
                    module=native_token,
                    category="pass_through_unknown_module",
                    confidence="unsupported_but_resolved",
                )
            )
            continue
        entries.extend(
            _manifest_evidence_entries(manifest=manifest, module=native_token)
        )
    return make_internal_evidence_ledger(tuple(entries))


def _manifest_evidence_entries(
    *, manifest: JsonObject, module: str
) -> tuple[JsonObject, ...]:
    """Return private evidence rows derived from one Make projector manifest."""
    entries = [
        make_evidence_entry(
            evidence_type="module_projector_manifest",
            judgment="make_native_module_projection",
            source_id=str(manifest.get("native_token") or module),
            module=module,
            confidence=_manifest_confidence(manifest),
            detail={
                "projector_kind": _manifest_projector_kind(manifest),
                "fixture_count": len(_manifest_fixtures(manifest)),
                "last_evidence_source": _manifest_optional_text(
                    manifest.get("last_evidence_source"),
                )
                or "local_manifest",
            },
        ),
        make_evidence_entry(
            evidence_type="parity_confidence",
            judgment="make_native_module_projection_confidence",
            source_id=str(manifest.get("native_token") or module),
            module=module,
            confidence=_manifest_confidence(manifest),
        ),
    ]
    fixture_count = len(_manifest_fixtures(manifest))
    if fixture_count:
        entries.append(
            make_evidence_entry(
                evidence_type="fixture_family",
                judgment="make_native_shape_evidence",
                source_id=str(manifest.get("native_token") or module),
                module=module,
                confidence=_manifest_confidence(manifest),
                detail={"fixture_count": fixture_count},
            )
        )
    return tuple(entries)


def _manifest_confidence(manifest: JsonObject) -> str:
    """Return manifest confidence as a safe internal evidence value."""
    return _manifest_optional_text(manifest.get("confidence")) or "unknown"


def _manifest_projector_kind(manifest: JsonObject) -> str:
    """Return manifest projector kind as a safe internal evidence value."""
    projector = manifest.get("projector")
    if not isinstance(projector, dict):
        return "unknown"
    kind = cast("dict[object, object]", projector).get("kind")
    return _manifest_optional_text(kind) or "unknown"


def _manifest_fixtures(manifest: JsonObject) -> tuple[str, ...]:
    """Return fixture references declared by one private manifest."""
    fixtures = manifest.get("fixtures")
    if not isinstance(fixtures, list):
        return ()
    return tuple(
        str(item)
        for item in cast("list[object]", fixtures)
        if isinstance(item, str)
    )


def _manifest_optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _render_root_metadata(
    *,
    root: MakeAstRoot,
    context: _RenderContext,
) -> JsonObject:
    """Render Make-native root metadata for the selected output mode.

    Returns:
        The Make-native root metadata payload.

    Raises:
        MakeBlueprintPrivateMetadataLeakError: If raw notes contain private
        trace evidence.
    """
    if context.mode == "draft":
        return _copy_json_object(root.scenario.metadata)
    metadata = _make_metadata_subset(
        metadata=root.scenario.metadata,
        allowed_keys=MAKE_NATIVE_ROOT_METADATA_KEYS,
    )
    metadata["version"] = _positive_int_or_default(
        metadata.get("version"),
        default=DEFAULT_MAKE_ROOT_METADATA_VERSION,
    )
    scenario = metadata.get("scenario")
    if not isinstance(scenario, dict):
        scenario = {}
    typed_scenario = cast("JsonObject", scenario)
    metadata["scenario"] = {"slots": typed_scenario.get("slots")}
    typed_designer: JsonObject = {}
    _ = typed_designer.setdefault("orphans", [])
    metadata["designer"] = typed_designer
    note_leak_paths = _root_note_private_leak_paths(metadata.get("notes"))
    if note_leak_paths:
        raise MakeBlueprintPrivateMetadataLeakError(note_leak_paths)
    metadata["notes"] = _render_safe_root_notes(metadata.get("notes"))
    if "instant" not in metadata and _root_has_instant_trigger(root):
        metadata["instant"] = True
    return metadata


def _root_note_private_leak_paths(raw_notes: object) -> tuple[str, ...]:
    """Return raw Make note paths that contain private/local trace evidence."""
    if not isinstance(raw_notes, list):
        return ()
    leak_paths: list[str] = []
    for index, raw_note in enumerate(cast("list[object]", raw_notes)):
        _collect_private_key_leaks(
            value=raw_note,
            path=f"$.metadata.notes[{index}]",
            leak_paths=leak_paths,
        )
    return tuple(leak_paths)


def _render_safe_root_notes(raw_notes: object) -> list[object]:
    """Return Make-safe notes with private metadata and unsafe text removed."""
    if not isinstance(raw_notes, list):
        return []
    notes: list[object] = []
    for raw_note in cast("list[object]", raw_notes):
        if not isinstance(raw_note, dict):
            continue
        note = cast("JsonObject", raw_note)
        content = note.get("content")
        if not isinstance(content, str) or _text_has_private_trace(content):
            continue
        rendered: JsonObject = {
            "content": content,
            "isFilterNote": bool(note.get("isFilterNote")),
            "metadata": {"color": _safe_note_color(note.get("metadata"))},
        }
        module_ids = note.get("moduleIds")
        safe_module_ids = _safe_note_module_ids(module_ids)
        if safe_module_ids:
            rendered["moduleIds"] = list(safe_module_ids)
        notes.append(rendered)
    return notes


def _safe_note_color(raw_metadata: object) -> str:
    if not isinstance(raw_metadata, dict):
        return MAKE_NOTE_DEFAULT_COLOR
    color = cast("JsonObject", raw_metadata).get("color")
    if not isinstance(color, str):
        return MAKE_NOTE_DEFAULT_COLOR
    normalized = color.strip().upper()
    return (
        normalized
        if normalized in MAKE_NOTE_COLOR_PALETTE
        else MAKE_NOTE_DEFAULT_COLOR
    )


def _safe_note_module_ids(raw_module_ids: object) -> tuple[int, ...]:
    """Return Make-native numeric note anchors from draft note ids."""
    if not isinstance(raw_module_ids, list):
        return ()
    module_ids: list[int] = []
    for raw_module_id in cast("list[object]", raw_module_ids):
        if isinstance(raw_module_id, bool):
            continue
        if isinstance(raw_module_id, int):
            if raw_module_id > 0:
                module_ids.append(raw_module_id)
            continue
        if isinstance(raw_module_id, str):
            normalized = raw_module_id.strip()
            if normalized.isdecimal():
                module_id = int(normalized)
                if module_id > 0:
                    module_ids.append(module_id)
    return tuple(module_ids)


def _root_has_instant_trigger(root: MakeAstRoot) -> bool:
    """Return if the root starts from a Make instant webhook-like trigger."""
    for node in root.flow:
        if node.module_token.casefold().startswith(("gateway:", "webhook:")):
            return True
    return False


def _render_node(node: MakeAstNode, *, context: _RenderContext) -> JsonObject:
    """Render one Make AST node.

    Returns:
        The Make-native node payload.
    """
    payload = _copy_json_object(node.raw_payload)
    payload["id"] = _json_node_id(node.node_id)
    _render_module_binding(payload=payload, node=node, context=context)
    if node.routes:
        payload["routes"] = [
            _render_route(route, context=context) for route in node.routes
        ]
    if node.branches:
        payload["branches"] = [
            _render_route(route, context=context) for route in node.branches
        ]
    if node.tools:
        payload["tools"] = [
            _render_route(route, context=context) for route in node.tools
        ]
    _render_error_handlers(payload=payload, node=node, context=context)
    return payload


def _render_module_binding(
    *,
    payload: JsonObject,
    node: MakeAstNode,
    context: _RenderContext,
) -> None:
    """Render the Make module token and module version."""
    if context.mode == "draft":
        payload["module"] = node.module_token
        return
    module = _resolved_catalog_module(node=node, context=context)
    if module is None:
        payload["module"] = node.module_token
        return
    native_token = f"{module.app_slug}:{module.internal_name}"
    manifest = make_module_projector_manifest_for_native_token(native_token)
    payload["module"] = native_token
    payload["version"] = _render_module_version(
        node=node,
        module=module,
        native_token=native_token,
        manifest=manifest,
    )
    if manifest is None:
        payload["metadata"] = _render_pass_through_node_metadata(
            payload=payload,
            node=node,
            context=context,
        )
        return
    _render_native_parameters(payload=payload, module=module)
    payload["metadata"] = _render_node_metadata(
        payload=payload,
        node=node,
        module=module,
        context=context,
    )
    _project_make_native_node(
        payload=payload,
        node=node,
        module=module,
        native_token=native_token,
        manifest=manifest,
    )


def _project_make_native_node(
    *,
    payload: JsonObject,
    node: MakeAstNode,
    module: CatalogModule,
    native_token: str,
    manifest: JsonObject | None,
) -> None:
    """Apply Make module-specific import-shape projections."""
    if manifest is None:
        return
    projector_kind = make_module_projector_kind(manifest)
    if projector_kind == "gateway_custom_webhook":
        _project_gateway_custom_webhook(
            payload=payload, node=node, manifest=manifest
        )
    elif projector_kind in FLOW_CONTROL_PROJECTOR_KINDS:
        _project_flow_control_node(
            projector_kind=projector_kind, payload=payload
        )
    elif projector_kind == "array_aggregator":
        _project_array_aggregator(payload=payload)
    elif projector_kind == "text_aggregator":
        _project_text_aggregator(payload=payload)
    elif projector_kind == "datastore_add_record":
        _project_datastore_add_record(
            payload=payload, node=node, manifest=manifest
        )
    elif projector_kind == "slack_create_message":
        _project_slack_create_message(
            payload=payload, module=module, manifest=manifest
        )
    _ = native_token


def _render_pass_through_node_metadata(
    *,
    payload: JsonObject,
    node: MakeAstNode,
    context: _RenderContext,
) -> JsonObject:
    """Return metadata for a resolved module without a Make-native projector.

    Pass-through modules preserve safe Make-native payload shape and receive
    only designer
    coordinates. Private or secret-like material is still rejected by the final
    zero-trace gate.
    """
    raw_metadata = payload.get("metadata")
    metadata = (
        _pass_through_safe_metadata(cast("JsonObject", raw_metadata))
        if isinstance(raw_metadata, dict)
        else {}
    )
    designer = metadata.get("designer")
    if not isinstance(designer, dict):
        designer = {}
    typed_designer = cast("JsonObject", designer)
    layout = context.layouts_by_source_path.get(node.source_trace.path)
    if layout is not None:
        _ = typed_designer.setdefault("x", layout.x)
        _ = typed_designer.setdefault("y", layout.y)
    else:
        _ = typed_designer.setdefault("x", 0)
        _ = typed_designer.setdefault("y", 0)
    metadata["designer"] = typed_designer
    return metadata


def _pass_through_safe_metadata(metadata: JsonObject) -> JsonObject:
    """Return pass-through metadata without source-only DSL containers."""
    safe: JsonObject = {}
    for key, value in metadata.items():
        if _is_pass_through_stripped_metadata_key(key):
            continue
        safe[key] = _pass_through_safe_metadata_value(value)
    return safe


def _pass_through_safe_metadata_value(value: object) -> object:
    """Return one metadata value with nested private keys removed."""
    if isinstance(value, dict):
        return _pass_through_safe_metadata(cast("JsonObject", value))
    if isinstance(value, list):
        return [
            _pass_through_safe_metadata_value(item)
            for item in cast("list[object]", value)
        ]
    return _copy_json_value(value)


def _is_pass_through_stripped_metadata_key(key: object) -> bool:
    """Return if pass-through should omit a known source-only metadata key."""
    return (
        isinstance(key, str)
        and key.casefold() in PASS_THROUGH_STRIPPED_METADATA_KEYS
    )


def _project_flow_control_node(
    *, projector_kind: str, payload: JsonObject
) -> None:
    if projector_kind == "basic_repeater":
        _project_basic_repeater(payload=payload)
    elif projector_kind == "function_sleep":
        _project_function_sleep(payload=payload)
    elif projector_kind == "set_variable":
        _project_set_variable(payload=payload)
    elif projector_kind == "get_variable":
        _project_get_variable(payload=payload)
    elif projector_kind == "function_increment":
        _project_function_increment(payload=payload)


def _project_gateway_custom_webhook(
    *,
    payload: JsonObject,
    node: MakeAstNode,
    manifest: JsonObject,
) -> None:
    """Render webhook trigger output evidence as Make interface metadata."""
    metadata = _ensure_json_object(payload, "metadata")
    mapper = payload.get("mapper")
    if isinstance(mapper, dict) and "interface" not in metadata:
        metadata["interface"] = [
            _make_text_schema_field(name=key)
            for key in sorted(cast("JsonObject", mapper))
            if _is_make_identifier(key)
        ]
    payload["mapper"] = {}
    parameters = _ensure_json_object(payload, "parameters")
    _ = parameters.setdefault("maxResults", 1)
    metadata["advanced"] = True
    restore = _ensure_json_object(metadata, "restore")
    restore_parameters = _ensure_json_object(restore, "parameters")
    if "hook" in parameters:
        restore_parameters["hook"] = {
            "label": "Webhook",
            "data": {"editable": "true"},
        }
    _ = (node, manifest)


def _project_datastore_add_record(
    *,
    payload: JsonObject,
    node: MakeAstNode,
    manifest: JsonObject,
) -> None:
    """Render Data Store add-record payloads with Make-native mapper shape."""
    source_mapper = payload.get("mapper")
    mapper = (
        cast("JsonObject", source_mapper)
        if isinstance(source_mapper, dict)
        else {}
    )
    key_value = mapper.get("key", mapper.get("request_id", "{{1.request_id}}"))
    explicit_data = mapper.get("data")
    data: JsonObject = {}
    if isinstance(explicit_data, dict):
        for key, value in cast("dict[object, object]", explicit_data).items():
            data[str(key)] = _copy_json_value(value)
    data = {
        **data,
        **{
            key: _copy_json_value(value)
            for key, value in mapper.items()
            if key not in {"data", "key", "overwrite", "request_id"}
        },
    }
    payload["mapper"] = {
        "key": _copy_json_value(key_value),
        "overwrite": _copy_json_value(mapper.get("overwrite", False)),
        "data": data,
    }
    metadata = _ensure_json_object(payload, "metadata")
    metadata["expect"] = _datastore_expect_schema(data=data, manifest=manifest)
    restore = _ensure_json_object(metadata, "restore")
    restore["parameters"] = {"datastore": {"label": "Data store"}}
    restore["expect"] = {"overwrite": {"mode": "chose"}}
    if "interface" not in metadata:
        metadata["interface"] = [
            _make_text_schema_field(name="key", path=("key",))
        ]
    _ = node


def _project_array_aggregator(*, payload: JsonObject) -> None:
    """Render Array Aggregator metadata without inventing runtime resource.

    values.
    """
    source_mapper = payload.get("mapper")
    mapper = (
        cast("JsonObject", source_mapper)
        if isinstance(source_mapper, dict)
        else {}
    )
    payload["mapper"] = mapper
    metadata = _ensure_json_object(payload, "metadata")
    if mapper and "expect" not in metadata:
        metadata["expect"] = [
            _make_text_schema_field(name=key)
            for key in sorted(mapper)
            if _is_make_identifier(key)
        ]
    if "interface" not in metadata:
        metadata["interface"] = [
            {"label": "Array", "name": "array", "spec": [], "type": "array"}
        ]
    parameters = payload.get("parameters")
    if isinstance(parameters, dict):
        _restore_aggregator_source(
            metadata=metadata, parameters=cast("JsonObject", parameters)
        )


def _project_basic_repeater(*, payload: JsonObject) -> None:
    """Render Repeater schema in Make-native shape."""
    _ = _ensure_json_object(payload, "mapper")
    metadata = _ensure_json_object(payload, "metadata")
    metadata["expect"] = [
        _repeater_field_schema(name) for name in ("start", "repeats", "step")
    ]
    if "interface" not in metadata:
        metadata["interface"] = [{"name": "i", "type": "number"}]


def _project_function_sleep(*, payload: JsonObject) -> None:
    """Render Sleep delay schema in Make-native shape."""
    _ = _ensure_json_object(payload, "mapper")
    metadata = _ensure_json_object(payload, "metadata")
    metadata["expect"] = [_duration_field_schema()]
    _ = metadata.setdefault("restore", {})


def _project_set_variable(*, payload: JsonObject) -> None:
    """Render Set variable schema and value output in Make-native shape."""
    source_mapper = payload.get("mapper")
    mapper = (
        cast("JsonObject", source_mapper)
        if isinstance(source_mapper, dict)
        else {}
    )
    payload["mapper"] = mapper
    metadata = _ensure_json_object(payload, "metadata")
    metadata["expect"] = _variable_assignment_expect_schema()
    if "interface" not in metadata:
        variable_name = mapper.get("name")
        label = (
            variable_name
            if isinstance(variable_name, str) and variable_name
            else "Value"
        )
        metadata["interface"] = [
            {"label": label, "name": "value", "type": "any"}
        ]
    restore = _ensure_json_object(metadata, "restore")
    restore_expect = _ensure_json_object(restore, "expect")
    restore_expect["scope"] = {
        "label": _variable_scope_label(mapper.get("scope"))
    }


def _project_get_variable(*, payload: JsonObject) -> None:
    """Render Get variable schema and value output in Make-native shape."""
    _ = _ensure_json_object(payload, "mapper")
    metadata = _ensure_json_object(payload, "metadata")
    metadata["expect"] = [_variable_name_field_schema()]
    if "interface" not in metadata:
        metadata["interface"] = [
            {"label": "Value", "name": "value", "type": "any"}
        ]


def _project_function_increment(*, payload: JsonObject) -> None:
    """Render Increment function schema and counter output in Make-native.

    shape.
    """
    _ = _ensure_json_object(payload, "mapper")
    parameters = _ensure_json_object(payload, "parameters")
    metadata = _ensure_json_object(payload, "metadata")
    metadata["parameters"] = [_reset_parameter_schema()]
    if "interface" not in metadata:
        metadata["interface"] = [{"label": "i", "name": "i", "type": "number"}]
    restore = _ensure_json_object(metadata, "restore")
    restore["reset"] = {"label": _reset_label(parameters.get("reset"))}


def _project_text_aggregator(*, payload: JsonObject) -> None:
    """Render Text Aggregator mapper and UI schema in Make-native shape."""
    source_mapper = payload.get("mapper")
    mapper = (
        cast("JsonObject", source_mapper)
        if isinstance(source_mapper, dict)
        else {}
    )
    payload["mapper"] = mapper
    parameters = _ensure_json_object(payload, "parameters")
    _ = parameters.setdefault("rowSeparator", "")
    metadata = _ensure_json_object(payload, "metadata")
    if "expect" not in metadata:
        metadata["expect"] = [
            {
                "label": "Text",
                "multiline": True,
                "name": "value ",
                "type": "text",
            }
        ]
    if "parameters" not in metadata:
        metadata["parameters"] = [_row_separator_parameter_schema()]
    if "interface" not in metadata:
        metadata["interface"] = [
            {"help": "Text", "name": "text", "type": "text"}
        ]
    _restore_aggregator_source(metadata=metadata, parameters=parameters)
    restore = _ensure_json_object(metadata, "restore")
    if "rowSeparator" in parameters:
        restore["rowSeparator"] = {
            "label": _row_separator_label(parameters.get("rowSeparator")),
        }


def _restore_aggregator_source(
    *, metadata: JsonObject, parameters: JsonObject
) -> None:
    if "feeder" not in parameters:
        return
    restore = _ensure_json_object(metadata, "restore")
    source = {"label": "Source module"}
    if "target" in parameters:
        extra = _ensure_json_object(restore, "extra")
        extra["feeder"] = source
        extra["target"] = {"label": "Target"}
        return
    restore["feeder"] = source


def _row_separator_parameter_schema() -> JsonObject:
    return {
        "label": "Row separator ",
        "name": "rowSeparator ",
        "type": "select",
        "validate": {"enum": ["\n", "\t", "other"]},
    }


def _row_separator_label(value: object) -> str:
    if value == "\n":
        return "New row"
    if value == "\t":
        return "Tab"
    if isinstance(value, str) and value:
        return "Other"
    return ""


def _repeater_field_schema(name: str) -> JsonObject:
    schema_by_name: dict[str, JsonObject] = {
        "start": {
            "default": 1,
            "label": "Initial value ",
            "name": "start",
            "required": True,
            "type": "number",
        },
        "repeats": {
            "default": 3,
            "label": "Repeats ",
            "name": "repeats",
            "required": True,
            "type": "number",
            "validate": {"max": 10000, "min": 0},
        },
        "step": {
            "advanced": True,
            "default": 1,
            "label": "Step ",
            "name": "step",
            "required": True,
            "type": "number",
        },
    }
    return schema_by_name[name]


def _duration_field_schema() -> JsonObject:
    return {
        "help": (
            "The number of seconds for which the scenario execution "
            "will be suspended."
        ),
        "label": "Delay ",
        "name": "duration",
        "required": True,
        "type": "uinteger",
        "validate": {"max": 300, "min": 1},
    }


def _variable_assignment_expect_schema() -> list[object]:
    return [
        _variable_name_field_schema(),
        {
            "advanced": True,
            "default": "roundtrip ",
            "label": "Variable lifetime ",
            "name": "scope",
            "required": True,
            "type": "select",
            "validate": {"enum": ["roundtrip", "execution"]},
        },
        {"label": "Variable value", "name": "value", "type": "any"},
    ]


def _variable_name_field_schema() -> JsonObject:
    return {
        "label": "Variable name ",
        "name": "name",
        "required": True,
        "type": "text",
    }


def _variable_scope_label(value: object) -> str:
    if value == "execution":
        return "One execution"
    return "One cycle"


def _reset_parameter_schema() -> JsonObject:
    return {
        "label": "Reset a value ",
        "name": "reset",
        "required": True,
        "type": "select",
        "validate": {"enum": ["run", "execution", "scenario"]},
    }


def _reset_label(value: object) -> str:
    labels = {
        "run": "After one cycle ",
        "execution": "After one scenario run ",
        "scenario": "Never",
    }
    return labels.get(value, "Never") if isinstance(value, str) else "Never"


def _project_slack_create_message(
    *,
    payload: JsonObject,
    module: CatalogModule,
    manifest: JsonObject,
) -> None:
    """Render Slack CreateMessage inputs closer to Make-native mapper shape."""
    parameters = payload.get("parameters")
    if not isinstance(parameters, dict):
        return
    typed_parameters = cast("JsonObject", parameters)
    mapper = payload.get("mapper")
    typed_mapper = (
        cast("JsonObject", mapper) if isinstance(mapper, dict) else {}
    )
    for key in tuple(typed_parameters):
        if key == "__IMTCONN__":
            continue
        _ = typed_mapper.setdefault(
            key, _copy_json_value(typed_parameters[key])
        )
        _ = typed_parameters.pop(key, None)
    if typed_mapper:
        payload["mapper"] = typed_mapper
    payload["parameters"] = typed_parameters
    metadata = _ensure_json_object(payload, "metadata")
    restore = _ensure_json_object(metadata, "restore")
    restore_parameters = _ensure_json_object(restore, "parameters")
    if "__IMTCONN__" in typed_parameters:
        metadata_parameters = _ensure_json_object(metadata, "parameters")
        connection_family = _slack_connection_family(
            module=module, manifest=manifest
        )
        metadata_parameters["__IMTCONN__"] = {
            "label": "Slack connection",
            "type": connection_family,
        }
        restore_parameters["__IMTCONN__"] = {
            "label": "Slack connection",
            "data": {"connection": connection_family, "scoped": "true"},
        }


def _datastore_expect_schema(
    *, data: JsonObject, manifest: JsonObject
) -> list[object]:
    field_order = make_module_manifest_policy_required_keys(
        manifest, "metadata_expect_policy"
    )
    if not field_order:
        field_order = ("key", "overwrite", "data")
    data_spec = [
        _make_text_schema_field(name=key)
        for key in sorted(data)
        if _is_make_identifier(key)
    ]
    schema_by_key: JsonObject = {
        "key": {"name": "key", "type": "text", "label": "Key"},
        "overwrite": {
            "name": "overwrite ",
            "type": "boolean ",
            "label": "Overwrite an existing record",
            "required": True,
        },
        "data": {
            "name": "data ",
            "type": "collection ",
            "label": "Record",
            "spec": data_spec,
        },
    }
    return [
        _copy_json_value(schema_by_key[key])
        for key in field_order
        if key in schema_by_key
    ]


def _make_text_schema_field(
    *,
    name: str,
    path: tuple[str, ...] | None = None,
) -> JsonObject:
    if path is not None:
        return {
            "label": _humanize_identifier(name),
            "path": list(path),
            "type": "text",
        }
    return {"name": name, "type": "text", "label": _humanize_identifier(name)}


def _humanize_identifier(value: str) -> str:
    return value.replace("_", " ").strip().capitalize() or value


def _is_make_identifier(value: object) -> bool:
    return isinstance(value, str) and bool(
        re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value)
    )


def _slack_connection_family(
    *, module: CatalogModule, manifest: JsonObject
) -> str:
    manifest_families = make_module_manifest_connection_families(manifest)
    if manifest_families:
        return manifest_families[0]
    for field in module.parameters:
        raw_type = str(
            field.raw_schema.get("type", "") or field.field_type or ""
        )
        if raw_type.startswith("account:"):
            return raw_type.removeprefix("account:").split(",", 1)[0]
    return "slack2"


def _resolved_catalog_module(
    *,
    node: MakeAstNode,
    context: _RenderContext,
) -> CatalogModule | None:
    """Return the resolved catalog module for one AST node, if available."""
    resolution = context.resolutions_by_source_path.get(node.source_trace.path)
    if (
        resolution is None
        or resolution.status != RESOLVED_STATUS
        or resolution.catalog_module_id is None
    ):
        return None
    return context.modules_by_id.get(resolution.catalog_module_id)


def _render_module_version(
    *,
    node: MakeAstNode,
    module: CatalogModule,
    native_token: str,
    manifest: JsonObject | None,
) -> int:
    """Return the Make-native module version for one importable node."""
    if manifest is not None:
        manifest_version = make_module_manifest_fixed_version(manifest)
        if manifest_version is not None:
            return manifest_version
    raw_version = node.raw_payload.get("version")
    if node.module_token == native_token:
        raw_version_value = _positive_int(raw_version)
        if raw_version_value is not None:
            return raw_version_value
    return _catalog_major_version(module.app_version)


def _render_native_parameters(
    *,
    payload: JsonObject,
    module: CatalogModule,
) -> None:
    """Render Make-native parameter aliases for a resolved module."""
    raw_parameters = payload.get("parameters")
    if not isinstance(raw_parameters, dict):
        return
    parameters = cast("JsonObject", raw_parameters)
    for field in module.parameters:
        target = make_connection_parameter_target_for_field(field)
        if target is None or _json_path_has_value(parameters, (target,)):
            continue
        alias_value = _first_connection_alias_value(parameters, field=field)
        if alias_value is not None:
            parameters[target] = _copy_json_value(alias_value)
    _drop_non_native_connection_aliases(parameters=parameters, module=module)
    payload["parameters"] = parameters


def _first_connection_alias_value(
    parameters: JsonObject,
    *,
    field: CatalogField,
) -> object | None:
    """Return the first mapped legacy connection alias value for one field."""
    for alias in make_connection_parameter_aliases_for_field(field):
        if _json_path_has_value(parameters, (alias,)):
            return parameters[alias]
    return None


def _drop_non_native_connection_aliases(
    *,
    parameters: JsonObject,
    module: CatalogModule,
) -> None:
    """Drop stale connection aliases when a native Make target replaced them."""
    native_targets = {
        target
        for field in module.parameters
        if (target := make_connection_parameter_target_for_field(field))
        is not None
    }
    if not native_targets:
        return
    native_parameter_keys = {
        field.path[0] for field in module.parameters if len(field.path) == 1
    }
    for field in module.parameters:
        target = make_connection_parameter_target_for_field(field)
        if target is None:
            continue
        for alias in make_connection_parameter_aliases_for_field(field):
            if alias != target and alias not in native_parameter_keys:
                _ = parameters.pop(alias, None)


def _catalog_major_version(version: str) -> int:
    """Return the major version implied by a Make catalog app version string."""
    match = re.match(r"\D*(\d+)", version)
    if match is None:
        return DEFAULT_MAKE_MODULE_VERSION
    return _positive_int_or_default(
        match.group(1), default=DEFAULT_MAKE_MODULE_VERSION
    )


def _render_node_metadata(
    *,
    payload: JsonObject,
    node: MakeAstNode,
    module: CatalogModule,
    context: _RenderContext,
) -> JsonObject:
    """Render Make-native node metadata without Pancakes-private fields.

    Returns:
        The Make-native node metadata payload.
    """
    raw_metadata = payload.get("metadata")
    metadata = (
        _make_metadata_subset(
            metadata=cast("JsonObject", raw_metadata),
            allowed_keys=MAKE_NATIVE_NODE_METADATA_KEYS,
        )
        if isinstance(raw_metadata, dict)
        else {}
    )
    _fill_catalog_schema_metadata(metadata=metadata, module=module)
    designer = metadata.get("designer")
    if not isinstance(designer, dict):
        designer = {}
    typed_designer = cast("JsonObject", designer)
    layout = context.layouts_by_source_path.get(node.source_trace.path)
    if layout is not None:
        _ = typed_designer.setdefault("x", layout.x)
        _ = typed_designer.setdefault("y", layout.y)
    else:
        _ = typed_designer.setdefault("x", 0)
        _ = typed_designer.setdefault("y", 0)
    metadata["designer"] = typed_designer
    return metadata


def _fill_catalog_schema_metadata(
    *,
    metadata: JsonObject,
    module: CatalogModule,
) -> None:
    """Populate Make-native schema metadata from catalog fields when absent."""
    if "parameters" not in metadata and module.parameters:
        metadata["parameters"] = _catalog_field_schemas(module.parameters)
    if "expect" not in metadata and module.expect_schema:
        metadata["expect"] = _catalog_field_schemas(module.expect_schema)
    if "interface" not in metadata and module.interface_schema:
        metadata["interface"] = _catalog_field_schemas(module.interface_schema)


def _catalog_field_schemas(fields: tuple[CatalogField, ...]) -> list[object]:
    """Return deterministic raw field schemas for Make-native metadata."""
    return [_copy_json_object(field.raw_schema) for field in fields]


def _ensure_json_object(payload: JsonObject, key: str) -> JsonObject:
    value = payload.get(key)
    if isinstance(value, dict):
        return cast("JsonObject", value)
    created: JsonObject = {}
    payload[key] = created
    return created


def _make_metadata_subset(
    *,
    metadata: JsonObject,
    allowed_keys: tuple[str, ...],
) -> JsonObject:
    """Return the Make-native subset of a metadata object."""
    return {
        key: _copy_json_value(metadata[key])
        for key in allowed_keys
        if key in metadata
    }


def _assert_no_private_metadata_leak(payload: JsonObject) -> None:
    """Fail closed if an importable Make payload contains Pancakes-private keys.

    Raises:
        MakeBlueprintPrivateMetadataLeakError: If private keys remain in the
        payload.
    """
    leak_paths: list[str] = []
    _collect_private_key_leaks(value=payload, path="$", leak_paths=leak_paths)
    if leak_paths:
        raise MakeBlueprintPrivateMetadataLeakError(tuple(leak_paths))


def _mock_runtime_placeholders_for_import_preview(
    payload: JsonObject,
) -> JsonObject:
    """Return a Make import-preview payload with runtime aliases replaced by.

    mock values.
    """
    return cast("JsonObject", _mock_runtime_placeholder_value(payload))


def _mock_runtime_placeholder_value(value: object) -> object:
    """Return one JSON-compatible value with runtime placeholders replaced."""
    if isinstance(value, dict):
        return {
            str(key): _mock_runtime_placeholder_value(item)
            for key, item in cast("dict[object, object]", value).items()
        }
    if isinstance(value, list):
        return [
            _mock_runtime_placeholder_value(item)
            for item in cast("list[object]", value)
        ]
    if isinstance(value, str):
        return _mock_runtime_placeholder_text(value)
    return value


def _mock_runtime_placeholder_text(value: str) -> str:
    """Return text with runtime placeholders replaced by deterministic mock.

    labels.
    """
    match = RUNTIME_PLACEHOLDER_PATTERN.fullmatch(value.strip())
    if match is not None:
        return _mock_runtime_placeholder_replacement(match.group(1))
    return RUNTIME_PLACEHOLDER_PATTERN.sub(
        lambda match: _mock_runtime_placeholder_replacement(match.group(1)),
        value,
    )


def _mock_runtime_placeholder_replacement(alias: str) -> str:
    """Return the deterministic mock value for one runtime placeholder alias."""
    normalized = re.sub(r"[^A-Za-z0-9]+", "-", alias).strip("-").casefold()
    if not normalized:
        return "mock-runtime-value"
    return f"mock-{normalized}"


def _collect_private_key_leaks(
    *,
    value: object,
    path: str,
    leak_paths: list[str],
) -> None:
    """Collect paths to Pancakes-private keys in a rendered payload."""
    if isinstance(value, dict):
        typed_value = cast("JsonObject", value)
        for key, child_value in typed_value.items():
            child_path = f"{path}.{key}"
            if _is_private_pancakes_key(key):
                leak_paths.append(child_path)
            _collect_private_key_leaks(
                value=child_value,
                path=child_path,
                leak_paths=leak_paths,
            )
        return
    if isinstance(value, str) and _text_has_private_trace(value):
        leak_paths.append(path)
        return
    if isinstance(value, list):
        typed_list = cast("list[object]", value)
        for index, child_value in enumerate(typed_list):
            _collect_private_key_leaks(
                value=child_value,
                path=f"{path}[{index}]",
                leak_paths=leak_paths,
            )


def _is_private_pancakes_key(key: object) -> bool:
    """Return whether a JSON key belongs to Pancakes-private DSL evidence."""
    if not isinstance(key, str):
        return False
    normalized = key.casefold()
    return (
        normalized in PANCAKES_PRIVATE_METADATA_KEYS
        or normalized.startswith(PANCAKES_PRIVATE_KEY_PREFIXES)
    )


def _text_has_private_trace(value: str) -> bool:
    normalized = value.casefold()
    return any(
        pattern in normalized for pattern in PANCAKES_PRIVATE_TEXT_PATTERNS
    ) or any(
        pattern.search(value) is not None
        for pattern in PANCAKES_PRIVATE_TEXT_REGEXES
    )


def _render_route(
    route: MakeAstRoute, *, context: _RenderContext
) -> JsonObject:
    """Render one Make route-like wrapper.

    Returns:
        The Make-native route payload.
    """
    payload = _copy_json_object(route.raw_payload)
    rendered_flow = [_render_node(node, context=context) for node in route.flow]
    payload["flow"] = rendered_flow
    if route.filter is not None:
        rendered_filter = _render_filter(route.filter, context=context)
        if context.mode == "importable" and rendered_flow:
            rendered_flow[0]["filter"] = _merge_route_filter_into_node_filter(
                node_filter=rendered_flow[0].get("filter"),
                route_filter=rendered_filter,
            )
            _ = payload.pop("filter", None)
        else:
            payload["filter"] = rendered_filter
    return payload


def _render_filter(
    filter_value: MakeAstFilter, *, context: _RenderContext
) -> JsonObject:
    """Render one Make route filter.

    Returns:
        The Make-native filter payload.
    """
    payload = _copy_json_object(filter_value.raw_payload)
    if context.mode != "importable":
        return payload
    payload["name"] = filter_value.name
    typed_conditions = _make_native_filter_conditions(filter_value)
    if typed_conditions is not None:
        payload["conditions"] = typed_conditions
        _ = payload.pop("expression", None)
    return payload


def _merge_route_filter_into_node_filter(
    *,
    node_filter: object,
    route_filter: JsonObject,
) -> JsonObject:
    """Return one Make-native module filter that preserves route and node.

    conditions.
    """
    if not isinstance(node_filter, dict):
        return route_filter
    typed_node_filter = cast("JsonObject", node_filter)
    node_conditions = _make_condition_groups(
        typed_node_filter.get("conditions")
    )
    route_conditions = _make_condition_groups(route_filter.get("conditions"))
    if node_conditions is None:
        merged = _copy_json_object(typed_node_filter)
        if route_conditions is not None and "conditions" not in merged:
            merged["conditions"] = route_conditions
        merged["name"] = _merged_filter_name(
            node_name=typed_node_filter.get("name"),
            route_name=route_filter.get("name"),
        )
        return merged
    if route_conditions is None:
        merged = _copy_json_object(typed_node_filter)
        merged["name"] = _merged_filter_name(
            node_name=typed_node_filter.get("name"),
            route_name=route_filter.get("name"),
        )
        return merged
    merged = _copy_json_object(typed_node_filter)
    merged["conditions"] = [
        [*_copy_json_array(node_group), *_copy_json_array(route_group)]
        for node_group in node_conditions
        for route_group in route_conditions
    ]
    merged["name"] = _merged_filter_name(
        node_name=typed_node_filter.get("name"),
        route_name=route_filter.get("name"),
    )
    return merged


def _make_condition_groups(value: object) -> list[list[object]] | None:
    if not isinstance(value, list):
        return None
    groups: list[list[object]] = []
    for raw_group in cast("list[object]", value):
        if not isinstance(raw_group, list):
            return None
        groups.append(_copy_json_array(cast("list[object]", raw_group)))
    return groups


def _merged_filter_name(*, node_name: object, route_name: object) -> str:
    node_text = node_name.strip() if isinstance(node_name, str) else ""
    route_text = route_name.strip() if isinstance(route_name, str) else ""
    if node_text and route_text and node_text != route_text:
        return f"{node_text} + {route_text}"
    return node_text or route_text


def _make_native_filter_conditions(
    filter_value: MakeAstFilter,
) -> list[object] | None:
    conditions = filter_value.raw_payload.get("conditions")
    if isinstance(conditions, list):
        return _copy_json_array(cast("list[object]", conditions))
    expression = _filter_expression(filter_value)
    if expression is None:
        raw_conditions = filter_value.conditions.get("conditions")
        if isinstance(raw_conditions, list):
            return _copy_json_array(cast("list[object]", raw_conditions))
        return None
    return _conditions_from_expression(expression)


def _filter_expression(filter_value: MakeAstFilter) -> str | None:
    raw_expression = filter_value.raw_payload.get("expression")
    if isinstance(raw_expression, str) and raw_expression.strip():
        return raw_expression.strip()
    raw_conditions = filter_value.raw_payload.get("conditions")
    if isinstance(raw_conditions, dict):
        expression = cast("JsonObject", raw_conditions).get("expression")
        if isinstance(expression, str) and expression.strip():
            return expression.strip()
    expression = filter_value.conditions.get("expression")
    if isinstance(expression, str) and expression.strip():
        return expression.strip()
    return None


def _conditions_from_expression(expression: str) -> list[object] | None:
    groups: list[object] = []
    unparsed_terms: list[str] = []
    for raw_group in re.split(r"\s+or\s+", expression, flags=re.IGNORECASE):
        group_conditions: list[object] = []
        for raw_term in re.split(r"\s+and\s+", raw_group, flags=re.IGNORECASE):
            condition = _condition_from_expression_term(raw_term.strip())
            if condition is not None:
                group_conditions.append(condition)
            else:
                unparsed_terms.append(raw_term.strip())
        if group_conditions:
            groups.append(group_conditions)
    if unparsed_terms or not groups:
        return None
    return groups


def _condition_from_expression_term(term: str) -> JsonObject | None:
    empty_match = re.fullmatch(
        r"empty\((\{\{.+?}})\)", term, flags=re.IGNORECASE
    )
    if empty_match is not None:
        return {"a": empty_match.group(1), "o": "notexist"}
    exists_match = re.fullmatch(
        r"not\s+empty\((\{\{.+?}})\)", term, flags=re.IGNORECASE
    )
    if exists_match is not None:
        return {"a": exists_match.group(1), "o": "exist"}
    numeric_match = re.fullmatch(
        r"(\{\{.+?}})\s*(>=|>|<=|<|=|==)\s*([0-9]+(?:\.[0-9]+)?)", term
    )
    if numeric_match is not None:
        operator = _make_numeric_operator(numeric_match.group(2))
        return {
            "a": numeric_match.group(1),
            "o": operator,
            "b": numeric_match.group(3),
        }
    text_match = re.fullmatch(
        r"(\{\{.+?}})\s*(=|==|!=)\s*(\"[^\"]*\"|'[^']*')", term
    )
    if text_match is not None:
        operator = (
            "text:notequal" if text_match.group(2) == "!=" else "text:equal"
        )
        return {
            "a": text_match.group(1),
            "o": operator,
            "b": text_match.group(3)[1:-1],
        }
    contains_match = re.fullmatch(
        r"contains\((\{\{.+?}}),\s*(\"[^\"]*\"|'[^']*')\)",
        term,
        flags=re.IGNORECASE,
    )
    if contains_match is not None:
        return {
            "a": contains_match.group(1),
            "o": "text:contains",
            "b": contains_match.group(2)[1:-1],
        }
    return None


def _make_numeric_operator(operator: str) -> str:
    return {
        ">": "number:greater",
        ">=": "number:greaterorequal",
        "<": "number:less",
        "<=": "number:lessorequal",
        "=": "number:equal",
        "==": "number:equal",
    }[operator]


def _render_error_handlers(
    *,
    payload: JsonObject,
    node: MakeAstNode,
    context: _RenderContext,
) -> None:
    """Render direct error handlers back to their original or default key."""
    if not node.error_handlers:
        return
    raw_error_keys = tuple(
        key for key in DIRECT_ERROR_KEY_ORDER if key in payload
    )
    for direct_error_key in DIRECT_ERROR_KEY_ORDER:
        _ = payload.pop(direct_error_key, None)
    key = _error_handler_key(node.error_handlers, raw_error_keys=raw_error_keys)
    rendered_handlers = [
        _render_node(handler, context=context)
        for handler in node.error_handlers
    ]
    if _should_render_single_error_handler_object(node.error_handlers):
        payload[key] = rendered_handlers[0]
        return
    payload[key] = rendered_handlers


def _error_handler_key(
    error_handlers: tuple[MakeAstNode, ...],
    *,
    raw_error_keys: tuple[str, ...],
) -> str:
    """Return the error-handler key to use for rendering."""
    if len(raw_error_keys) == 1:
        return raw_error_keys[0]
    if len(raw_error_keys) > 1:
        return raw_error_keys[0]
    container_kind = error_handlers[0].source_trace.container_kind
    return container_kind if container_kind in DIRECT_ERROR_KEYS else "onerror"


def _should_render_single_error_handler_object(
    error_handlers: tuple[MakeAstNode, ...],
) -> bool:
    """Return whether one direct handler was originally object-shaped."""
    if len(error_handlers) != 1:
        return False
    handler = error_handlers[0]
    container_kind = handler.source_trace.container_kind
    return container_kind in DIRECT_ERROR_KEYS and handler.source_trace.path[
        -1:
    ] == (container_kind,)


def _json_node_id(node_id: str) -> str | int:
    """Render numeric node IDs as numbers when possible.

    Returns:
        The Make-native node ID value.
    """
    if not node_id.isdecimal():
        return node_id
    numeric_id = int(node_id)
    return numeric_id if str(numeric_id) == node_id else node_id


def _positive_int_or_default(value: object, *, default: int) -> int:
    """Return a positive integer value or the provided default."""
    positive_value = _positive_int(value)
    return default if positive_value is None else positive_value


def _positive_int(value: object) -> int | None:
    """Return a positive integer from JSON-compatible values."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.isdecimal():
        numeric_value = int(value)
        if numeric_value > 0:
            return numeric_value
    return None


def _json_path_has_value(payload: JsonObject, path: tuple[str, ...]) -> bool:
    """Return whether a JSON object path exists and has a meaningful value."""
    current: object = payload
    for part in path:
        if not isinstance(current, dict):
            return False
        typed_current = cast("dict[object, object]", current)
        if part not in typed_current:
            return False
        current = typed_current[part]
    return _is_meaningful_json_value(current)


def _is_meaningful_json_value(value: object) -> bool:
    """Return whether one JSON value carries Make parameter evidence."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return bool(cast("JsonObject", value))
    if isinstance(value, list):
        return bool(cast("list[object]", value))
    return True


def _copy_json_value(value: object) -> object:
    """Return a deterministic deep copy of a JSON-compatible value."""
    return cast("object", json.loads(json.dumps(value, sort_keys=True)))


def _copy_json_array(value: list[object]) -> list[object]:
    """Return a deterministic deep copy of a JSON array."""
    return cast("list[object]", _copy_json_value(value))


def _copy_json_object(value: JsonObject) -> JsonObject:
    """Return a deterministic deep copy of a JSON object."""
    return cast("JsonObject", _copy_json_value(value))
