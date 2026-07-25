# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001044#repo.make-ast.contract-policy
# - 001061#repo.delivery.assisted-stack-selection-auditable
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Compile explicit catalog-backed module plans into AST roots.

Boundary contract:
- Owns: compiling explicit module-id plans into auditable AST roots.
- Must not: infer module plans, render blueprint JSON, or write artifacts.
- Allows: request normalization, assembly composition, and origin reports.
- Split when: planning, policy normalization, or output modes need ownership.
- Merge when: another compiler returns the same compiled blueprint contract.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Final, NamedTuple, cast

from blueprints.ast.assembler import (
    BlueprintAssemblySpec,
    BlueprintNodeAssemblySpec,
    assemble_blueprint_from_catalog,
)
from blueprints.ast.phase_gates import (
    PHASE_COMPILE,
    BlueprintPhaseGateReport,
    phase_gate_from_validation_report,
)
from blueprints.validation.handoff_policy import (
    normalize_legacy_policy,
    normalize_quality_profile,
)
from blueprints.validation.validator import validate_blueprint

if TYPE_CHECKING:
    from collections.abc import Mapping

    from catalog.models import CatalogField, CatalogModule, CatalogSnapshot

    from blueprints.ast.models import JsonObject, MakeAstRoot


EMPTY_COMPILE_MAPPING: Final = cast(
    "Mapping[str, object]", MappingProxyType({})
)


class BlueprintCompileRequest(NamedTuple):
    """Explicit catalog-backed blueprint compile request."""

    name: str
    goal: str
    module_ids: tuple[str, ...]
    output_mode: str = "import_safe_functional"
    quality_profile: str = "client_ready"
    legacy_policy: str = "forbid_on_new"
    metadata: Mapping[str, object] = EMPTY_COMPILE_MAPPING


class CompiledBlueprint(NamedTuple):
    """Compiled AST root plus auditable origin metadata."""

    root: MakeAstRoot
    origin_report: Mapping[str, object]
    phase_gates: tuple[BlueprintPhaseGateReport, ...] = ()


def compile_blueprint_from_module_ids(
    *,
    request: BlueprintCompileRequest,
    catalog: CatalogSnapshot,
) -> CompiledBlueprint:
    """Compile an explicit module-id sequence into a parsed AST root.

    Returns:
        The result produced by compiling an explicit module-id sequence into
        a parsed AST root.

    Raises:
        ValueError: If an input value violates the documented contract.
    """
    if not request.module_ids:
        message = (
            "Blueprint compilation requires at least one catalog module ID."
        )
        raise ValueError(message)
    quality_profile = normalize_quality_profile(request.quality_profile)
    legacy_policy = normalize_legacy_policy(request.legacy_policy)
    assembly = BlueprintAssemblySpec(
        name=request.name,
        nodes=tuple(
            BlueprintNodeAssemblySpec(module_id=module_id)
            for module_id in request.module_ids
        ),
        metadata=_metadata(request, quality_profile, legacy_policy),
    )
    root = assemble_blueprint_from_catalog(spec=assembly, catalog=catalog)
    compile_phase_gate = phase_gate_from_validation_report(
        phase=PHASE_COMPILE,
        report=validate_blueprint(root=root, catalog=catalog),
    )
    modules = _requested_modules(catalog=catalog, module_ids=request.module_ids)
    return CompiledBlueprint(
        root=root,
        phase_gates=(compile_phase_gate,),
        origin_report={
            "catalog_fingerprint": catalog.fingerprint,
            "requested_module_ids": request.module_ids,
            "phase_gates": (compile_phase_gate,),
            "module_runtime_requirements": tuple(
                _module_runtime_requirement(module) for module in modules
            ),
            "quality_profile": quality_profile,
            "legacy_policy": legacy_policy,
            "goal": request.goal,
            "output_mode": request.output_mode,
        },
    )


def _requested_modules(
    *,
    catalog: CatalogSnapshot,
    module_ids: tuple[str, ...],
) -> tuple[CatalogModule, ...]:
    """Return requested modules in compile-request order."""
    modules: list[CatalogModule] = []
    for requested_module_id in module_ids:
        for app in catalog.apps:
            for version in app.versions:
                for module in version.modules:
                    if module.module_id == requested_module_id:
                        modules.append(module)
                        break
                else:
                    continue
                break
            else:
                continue
            break
    return tuple(modules)


def _module_runtime_requirement(module: CatalogModule) -> Mapping[str, object]:
    """Return offline availability and runtime setup notes for one module."""
    required_connections = _required_connection_fields(module)
    required_configuration = _required_configuration_fields(module)
    dynamic_configuration = bool(
        module.rpc_dependencies
        or any(
            field.rpc_dependencies
            for field in (*module.parameters, *module.expect_schema)
        )
    )
    if required_connections:
        runtime_status = "runtime_connection_required"
    elif required_configuration or dynamic_configuration:
        runtime_status = "runtime_configuration_required"
    else:
        runtime_status = "catalog_module_available"
    return {
        "module_id": module.module_id,
        "token": f"{module.app_slug}:{module.internal_name}",
        "display_name": module.display_name,
        "availability_status": "catalog_module_available",
        "runtime_status": runtime_status,
        "offline_status": (
            "usable_with_runtime_configuration_required"
            if runtime_status != "catalog_module_available"
            else "usable"
        ),
        "required_connections": tuple(
            _connection_label(field) for field in required_connections
        ),
        "required_configuration": tuple(
            ".".join(field.path) for field in required_configuration
        ),
        "dynamic_configuration": dynamic_configuration,
        "planning_notes": _runtime_planning_notes(
            module=module,
            required_connections=required_connections,
            required_configuration=required_configuration,
            dynamic_configuration=dynamic_configuration,
        ),
    }


def _required_connection_fields(
    module: CatalogModule,
) -> tuple[CatalogField, ...]:
    """Return required fields that represent live account connections."""
    return tuple(
        field
        for field in module.parameters
        if field.required and _field_requires_connection(field)
    )


def _required_configuration_fields(
    module: CatalogModule,
) -> tuple[CatalogField, ...]:
    """Return required runtime setup fields, excluding connection handles."""
    return tuple(
        field
        for field in module.parameters
        if field.required and not _field_requires_connection(field)
    )


def _field_requires_connection(field: CatalogField) -> bool:
    field_type = (field.field_type or "").casefold()
    path_text = ".".join(field.path).casefold()
    label_text = field.label.casefold()
    return (
        field_type.startswith("account:")
        or path_text in {"connection", "account"}
        or "connection" in path_text
        or "connection" in label_text
    )


def _connection_label(field: CatalogField) -> str:
    """Return client-safe connection wording for a required connection field."""
    field_type = field.field_type or ""
    if field_type.startswith("account:"):
        provider = (
            field_type.split(":", maxsplit=1)[1].replace("-", " ").strip()
        )
        if provider:
            return f"{provider.title()} connection"
    return "account connection"


def _runtime_planning_notes(
    *,
    module: CatalogModule,
    required_connections: tuple[CatalogField, ...],
    required_configuration: tuple[CatalogField, ...],
    dynamic_configuration: bool,
) -> tuple[str, ...]:
    notes: list[str] = []
    if required_connections:
        setup = _runtime_setup_label(
            required_configuration,
            dynamic_configuration=dynamic_configuration,
        )
        connection = _connection_label(required_connections[0])
        module_label = _client_module_label(module)
        notes.append(
            f"{module_label} requires {connection} and {setup} before live "
            "execution."
        )
    elif required_configuration or dynamic_configuration:
        setup = _runtime_setup_label(
            required_configuration,
            dynamic_configuration=dynamic_configuration,
        )
        module_label = _client_module_label(module)
        notes.append(
            " ".join(
                (
                    f"{module_label} is available in the local catalog.",
                    f"Live execution requires {setup}.",
                )
            )
        )
    else:
        notes.append(
            f"{_client_module_label(module)} is available in the local catalog."
        )
    return tuple(notes)


def _runtime_setup_label(
    required_configuration: tuple[CatalogField, ...],
    *,
    dynamic_configuration: bool,
) -> str:
    """Return concise runtime setup wording."""
    required_paths = {
        ".".join(field.path).casefold() for field in required_configuration
    }
    sheet_keys = {"spreadsheetId".casefold(), "sheetId".casefold()}
    if sheet_keys.intersection(required_paths):
        return "spreadsheet/sheet configuration"
    if dynamic_configuration:
        return "dynamic runtime configuration"
    return "required runtime configuration"


def _client_module_label(module: CatalogModule) -> str:
    """Return a compact client-visible module label."""
    app_label = module.app_slug.replace("-", " ").title()
    return f"{app_label} {module.display_name}"


def _metadata(
    request: BlueprintCompileRequest,
    quality_profile: str,
    legacy_policy: str,
) -> Mapping[str, object]:
    """Return compile metadata for AST assembly."""
    metadata = dict(request.metadata)
    raw_scenario = metadata.get("scenario")
    scenario: JsonObject = (
        dict(cast("Mapping[str, object]", raw_scenario))
        if isinstance(raw_scenario, dict)
        else {}
    )
    scenario.update(
        {
            "name": request.name,
            "goal": request.goal,
            "requested_mode": request.output_mode,
            "quality_profile": quality_profile,
            "legacy_policy": legacy_policy,
        }
    )
    metadata["scenario"] = scenario
    return metadata
