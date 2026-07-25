# ruff: noqa: C901, PLR0912, PLR0913, PLR1702, S608, TRY004
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001055#repo.mcp.required-tool-surface
# - 001055#repo.mcp.no-obsolete-domain-tools
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

# TC003, TRY003, TRY004

"""Local project storage, path, and scenario primitive helpers for MCP project.

tools.
"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

from catalog import DEFAULT_KNOWLEDGE_DB_PATH

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, MutableMapping, Sequence

    from mcp.models import JsonObject


PROJECT_ROOT = Path("projects")

LOCAL_PROJECT_ARTIFACT_ROOT = Path("temp") / "pancakes" / "project-artifacts"

BLUEPRINT_IMPORT_EVIDENCE_FILE_NAME = "imported-make-blueprint.evidence.json"

SCENARIO_FILE_NAME = "scenario.json"

LOCAL_PROJECT_METADATA_TABLE = "local_project_metadata"

DEFAULT_LOCAL_PROJECT_WORKSPACE_KEY = "local-demo"

DEFAULT_LOCAL_PROJECT_SCENARIO_KEY = "0001"

LOCAL_PROJECT_FOLDER_POLICY = (
    "temp/pancakes/project-artifacts/"
    "<workspace-folder-key>/<scenario-or-product-key>-<project-slug>/"
)

LOCAL_PROJECT_METADATA_DDL = """
CREATE TABLE IF NOT EXISTS local_project_metadata (
  project_id TEXT PRIMARY KEY,
  project_kind TEXT NOT NULL,
  workspace_folder_key TEXT NOT NULL,
  scenario_or_product_key TEXT NOT NULL,
  project_slug TEXT NOT NULL,
  artifact_envelope_path TEXT NOT NULL UNIQUE,
  scenario_artifact_path TEXT NOT NULL UNIQUE,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  valid_to TEXT
)
"""

LOCAL_PROJECT_METADATA_INDEX_DDL = (
    """
    CREATE INDEX IF NOT EXISTS idx_local_project_metadata_current_kind
      ON local_project_metadata (valid_to, project_kind, project_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_local_project_metadata_current_envelope
      ON local_project_metadata (valid_to, artifact_envelope_path)
    """,
)


def _scenario_summary(scenario: Mapping[str, object]) -> JsonObject:
    """Return stable graph counts for one local Make scenario."""
    modules = tuple(_iter_modules(scenario))
    links = tuple(_derive_links(scenario))
    filter_count = sum(
        1
        for _module, _route_index, route in _iter_routes(scenario)
        if "filter" in route
    )
    error_handler_count = sum(
        len(_handlers_for_module(module)) for _path, module in modules
    )
    route_count = sum(
        1 for _module, _route_index, _route in _iter_routes(scenario)
    )
    return {
        "module_count": len(modules),
        "link_count": len(links),
        "link_count_semantics": "deduped_semantic_execution_links",
        "raw_route_and_flow_edge_count": _raw_route_and_flow_edge_count(
            scenario
        ),
        "route_count": route_count,
        "filter_count": filter_count,
        "error_handler_count": error_handler_count,
    }


def _scenario_path(*, repo_root: Path, project_id: str) -> Path:
    metadata_row = _local_project_metadata_row(
        repo_root=repo_root, project_id=project_id
    )
    if metadata_row is not None:
        return _local_project_metadata_path(
            repo_root=repo_root,
            path_text=str(metadata_row["scenario_artifact_path"]),
        )
    legacy_path = _legacy_scenario_path(
        repo_root=repo_root, project_id=project_id
    )
    if legacy_path.exists():
        return legacy_path
    discovered_path = _discover_legacy_scenario_path(
        repo_root=repo_root,
        project_id=project_id,
    )
    return discovered_path or legacy_path


def _legacy_scenario_path(*, repo_root: Path, project_id: str) -> Path:
    project_dir = repo_root / PROJECT_ROOT / project_id
    return _project_root_confined_path(
        repo_root=repo_root,
        path=project_dir / SCENARIO_FILE_NAME,
    )


def _discover_legacy_scenario_path(
    *, repo_root: Path, project_id: str
) -> Path | None:
    projects_root = repo_root / PROJECT_ROOT
    if not projects_root.exists():
        return None
    matches: list[Path] = []
    for scenario_path in sorted(projects_root.rglob(SCENARIO_FILE_NAME)):
        confined_path = _project_root_confined_path(
            repo_root=repo_root,
            path=scenario_path,
        )
        try:
            scenario: JsonObject | None = _read_json_object(confined_path)
        except (json.JSONDecodeError, OSError, ValueError):
            scenario = None
        if (
            _local_project_id_from_scenario(
                scenario=scenario,
                scenario_path=confined_path,
            )
            == project_id
        ):
            matches.append(confined_path)
    if len(matches) == 1:
        return matches[0]
    return None


def _project_root_confined_path(*, repo_root: Path, path: Path) -> Path:
    projects_root = (repo_root / PROJECT_ROOT).resolve()
    resolved = path.resolve()
    if resolved != projects_root and projects_root not in resolved.parents:
        msg = "Project path escaped the repository project root."
        raise ValueError(msg)
    return resolved


def _local_project_generated_state_root(repo_root: Path) -> Path:
    return (
        _operator_workspace_root(repo_root) / LOCAL_PROJECT_ARTIFACT_ROOT
    ).resolve()


def _operator_workspace_root(repo_root: Path) -> Path:
    resolved = repo_root.resolve()
    for candidate in resolved.parents:
        if candidate.name == "repos":
            return candidate.parent.resolve()
    return resolved


def _local_project_generated_state_confined_path(
    *, repo_root: Path, path: Path
) -> Path:
    artifact_root = _local_project_generated_state_root(repo_root)
    resolved = path.resolve()
    if resolved != artifact_root and artifact_root not in resolved.parents:
        msg = "Project artifact path escaped the generated state root."
        raise ValueError(msg)
    return resolved


def _local_project_metadata_path(*, repo_root: Path, path_text: str) -> Path:
    relative_path = Path(path_text)
    if relative_path.is_absolute():
        return _local_project_confined_absolute_path(
            repo_root=repo_root, path=relative_path
        )
    if _path_has_prefix(relative_path, PROJECT_ROOT):
        return _project_root_confined_path(
            repo_root=repo_root, path=repo_root / relative_path
        )
    if _path_has_prefix(relative_path, LOCAL_PROJECT_ARTIFACT_ROOT):
        workspace_path = _operator_workspace_root(repo_root) / relative_path
        return _local_project_generated_state_confined_path(
            repo_root=repo_root,
            path=workspace_path,
        )
    msg = "Project metadata path is not an approved local project storage path."
    raise ValueError(msg)


def _local_project_confined_absolute_path(
    *, repo_root: Path, path: Path
) -> Path:
    resolved = path.resolve()
    generated_root = _local_project_generated_state_root(repo_root)
    if resolved == generated_root or generated_root in resolved.parents:
        return _local_project_generated_state_confined_path(
            repo_root=repo_root, path=resolved
        )
    return _project_root_confined_path(repo_root=repo_root, path=resolved)


def _path_has_prefix(path: Path, prefix: Path) -> bool:
    path_text = path.as_posix().rstrip("/")
    prefix_text = prefix.as_posix().rstrip("/")
    return path_text == prefix_text or path_text.startswith(f"{prefix_text}/")


def _local_project_display_path(*, repo_root: Path, path: Path) -> str:
    with suppress(ValueError):
        return _relative_to_repo(repo_root, path)
    workspace_root = _operator_workspace_root(repo_root)
    try:
        return path.resolve().relative_to(workspace_root.resolve()).as_posix()
    except ValueError as exc:
        msg = "Project path escaped the approved local project roots."
        raise ValueError(msg) from exc


def _required_project_id(arguments: Mapping[str, object]) -> str:
    project_id = _optional_text(arguments.get("project_id"))
    if not project_id:
        msg = "project_id is required."
        raise ValueError(msg)
    if not all(char.isalnum() or char in {"-", "_"} for char in project_id):
        msg = "project_id must be a safe local identifier."
        raise ValueError(msg)
    return project_id


def _read_json_object(path: Path) -> JsonObject:
    value = cast("object", json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(value, dict):
        msg = f"Expected JSON object at {path}."
        raise ValueError(msg)
    return cast("JsonObject", value)


def _write_json_object(path: Path, value: JsonObject) -> None:
    _ = path.write_text(
        f"{json.dumps(value, indent=2, sort_keys=True)}\n", encoding="utf-8"
    )


def _json_object_argument(
    arguments: Mapping[str, object],
    name: str,
    *,
    fallback_name: str | None = None,
) -> JsonObject:
    value = arguments.get(name)
    if value is None and fallback_name is not None:
        value = arguments.get(fallback_name)
    if isinstance(value, str):
        value = cast("object", json.loads(value))
    if not isinstance(value, dict):
        msg = f"{name} must be a JSON object."
        raise ValueError(msg)
    return cast("JsonObject", _json_copy(cast("Mapping[str, object]", value)))


def _iter_modules(
    scenario: Mapping[str, object],
) -> Iterator[tuple[str, JsonObject]]:
    flow = _flow_from_mapping(scenario)
    yield from _iter_flow_modules(flow, "flow")


def _iter_flow_modules(
    flow: Sequence[object], path: str
) -> Iterator[tuple[str, JsonObject]]:
    for index, item in enumerate(flow):
        if not isinstance(item, dict):
            continue
        module = cast("JsonObject", item)
        module_path = f"{path}[{index}]"
        yield module_path, module
        for route_index, route in enumerate(_routes_for_module(module)):
            yield from _iter_flow_modules(
                _flow_from_mapping(route),
                f"{module_path}.routes[{route_index}].flow",
            )
        for handler_index, handler in enumerate(_handlers_for_module(module)):
            yield from _iter_flow_modules(
                _flow_from_mapping(handler),
                f"{module_path}.onerror[{handler_index}].flow",
            )


def _flow_from_mapping(mapping: Mapping[str, object]) -> list[object]:
    flow = mapping.get("flow")
    if isinstance(flow, list):
        return cast("list[object]", flow)
    return []


def _routes_for_module(module: MutableMapping[str, object]) -> list[JsonObject]:
    routes = module.get("routes")
    if not isinstance(routes, list):
        return []
    return [
        cast("JsonObject", route)
        for route in cast("list[object]", routes)
        if isinstance(route, dict)
    ]


def _handlers_for_module(
    module: MutableMapping[str, object],
) -> list[JsonObject]:
    handlers = module.get("onerror")
    if not isinstance(handlers, list):
        return []
    return [
        cast("JsonObject", handler)
        for handler in cast("list[object]", handlers)
        if isinstance(handler, dict)
    ]


def _iter_routes(
    scenario: Mapping[str, object],
) -> Iterator[tuple[JsonObject, int, JsonObject]]:
    for _path, module in _iter_modules(scenario):
        for route_index, route in enumerate(_routes_for_module(module)):
            yield module, route_index, route


def _node_id(module: Mapping[str, object]) -> str | None:
    value = module.get("id")
    if isinstance(value, int | str) and str(value):
        return str(value)
    return None


def _optional_node_id(value: object) -> str | None:
    if isinstance(value, int | str) and str(value):
        return str(value)
    return None


def _required_node_id(arguments: Mapping[str, object], name: str) -> str:
    node_id = _optional_node_id(arguments.get(name))
    if node_id is None:
        msg = f"{name} is required."
        raise ValueError(msg)
    return node_id


def _required_module(
    scenario: JsonObject, node_id: str
) -> tuple[str, JsonObject]:
    for path, module in _iter_modules(scenario):
        if _node_id(module) == node_id:
            return path, module
    msg = f"Unknown module id: {node_id}."
    raise ValueError(msg)


def _require_unique_node_id(
    scenario: Mapping[str, object], node_id: str
) -> None:
    for _path, module in _iter_modules(scenario):
        if _node_id(module) == node_id:
            msg = f"Duplicate module id: {node_id}."
            raise ValueError(msg)


def _target_flow(
    scenario: JsonObject, arguments: Mapping[str, object]
) -> list[object]:
    parent_id = _optional_node_id(arguments.get("parent_node_id"))
    if parent_id is None:
        return _flow_from_mapping(scenario)
    _path, parent = _required_module(scenario, parent_id)
    routes = _routes_for_module(parent)
    route_index = _nonnegative_int(
        arguments.get("route_index"), default=0, upper=10_000
    )
    if route_index >= len(routes):
        msg = "route_index is out of range."
        raise ValueError(msg)
    route = routes[route_index]
    flow = route.get("flow")
    if not isinstance(flow, list):
        new_flow: list[object] = []
        route["flow"] = new_flow
        return new_flow
    return cast("list[object]", flow)


def _flow_path(arguments: Mapping[str, object]) -> str:
    parent_id = _optional_node_id(arguments.get("parent_node_id"))
    if parent_id is None:
        return "flow"
    route_index = _nonnegative_int(
        arguments.get("route_index"), default=0, upper=10_000
    )
    return f"node:{parent_id}.routes[{route_index}].flow"


def _insert_position(value: object, item_count: int) -> int:
    if value is None:
        return item_count
    if isinstance(value, bool):
        msg = "position must be an integer."
        raise ValueError(msg)
    if isinstance(value, int):
        return max(0, min(value, item_count))
    if isinstance(value, str) and value.isdecimal():
        return max(0, min(int(value), item_count))
    msg = "position must be an integer."
    raise ValueError(msg)


def _remove_module(scenario: JsonObject, node_id: str) -> JsonObject:
    removed = _remove_from_flow(_flow_from_mapping(scenario), node_id)
    if removed is None:
        msg = f"Unknown module id: {node_id}."
        raise ValueError(msg)
    return _module_summary("removed", removed)


def _remove_from_flow(flow: list[object], node_id: str) -> JsonObject | None:
    for index, item in enumerate(tuple(flow)):
        if not isinstance(item, dict):
            continue
        module = cast("JsonObject", item)
        if _node_id(module) == node_id:
            return cast("JsonObject", flow.pop(index))
        for route in _routes_for_module(module):
            removed = _remove_from_flow(_flow_from_mapping(route), node_id)
            if removed is not None:
                return removed
        for handler in _handlers_for_module(module):
            removed = _remove_from_flow(_flow_from_mapping(handler), node_id)
            if removed is not None:
                return removed
    return None


def _derive_links(scenario: Mapping[str, object]) -> Iterator[JsonObject]:
    yield from _derive_flow_links(_flow_from_mapping(scenario), parent_id=None)


def _raw_route_and_flow_edge_count(scenario: Mapping[str, object]) -> int:
    """Return the computed result for the caller."""
    return sum(
        1
        for _edge in _derive_raw_route_and_flow_edges(
            _flow_from_mapping(scenario), parent_id=None
        )
    )


def _derive_raw_route_and_flow_edges(
    flow: Sequence[object],
    *,
    parent_id: str | None,
) -> Iterator[tuple[str, str]]:
    previous_id = parent_id
    for item in flow:
        if not isinstance(item, dict):
            continue
        module = cast("JsonObject", item)
        current_id = _node_id(module)
        if previous_id is not None and current_id is not None:
            yield previous_id, current_id
        for route in _routes_for_module(module):
            if current_id is not None:
                for child in _flow_from_mapping(route):
                    if isinstance(child, dict):
                        child_id = _node_id(cast("JsonObject", child))
                        if child_id is not None:
                            yield current_id, child_id
                            break
            yield from _derive_raw_route_and_flow_edges(
                _flow_from_mapping(route),
                parent_id=current_id,
            )
        for handler in _handlers_for_module(module):
            yield from _derive_raw_route_and_flow_edges(
                _flow_from_mapping(handler),
                parent_id=current_id,
            )
        previous_id = current_id


def _derive_flow_links(
    flow: Sequence[object], *, parent_id: str | None
) -> Iterator[JsonObject]:
    previous_id = parent_id
    for item in flow:
        if not isinstance(item, dict):
            continue
        module = cast("JsonObject", item)
        current_id = _node_id(module)
        if previous_id is not None and current_id is not None:
            yield {
                "source_node_id": previous_id,
                "target_node_id": current_id,
                "link_kind": "flow_link",
            }
        for route_index, route in enumerate(_routes_for_module(module)):
            if current_id is not None:
                for child in _flow_from_mapping(route):
                    if isinstance(child, dict):
                        child_id = _node_id(cast("JsonObject", child))
                        if child_id is not None:
                            yield {
                                "source_node_id": current_id,
                                "target_node_id": child_id,
                                "link_kind": "route_entry_link",
                                "route_index": route_index,
                            }
                            break
            yield from _derive_flow_links(
                _flow_from_mapping(route), parent_id=None
            )
        for handler_index, handler in enumerate(_handlers_for_module(module)):
            if current_id is not None:
                for child in _flow_from_mapping(handler):
                    if isinstance(child, dict):
                        child_id = _node_id(cast("JsonObject", child))
                        if child_id is not None:
                            yield {
                                "source_node_id": current_id,
                                "target_node_id": child_id,
                                "link_kind": "error_handler_link",
                                "handler_index": handler_index,
                            }
                            break
            yield from _derive_flow_links(
                _flow_from_mapping(handler), parent_id=None
            )
        previous_id = current_id


def _module_summary(path: str, module: Mapping[str, object]) -> JsonObject:
    return {
        "node_id": _node_id(module),
        "module": _optional_text(module.get("module")) or "",
        "path": path,
        "route_count": len(
            _routes_for_module(cast("MutableMapping[str, object]", module))
        ),
        "error_handler_count": len(
            _handlers_for_module(cast("MutableMapping[str, object]", module))
        ),
    }


def _filter_summary(
    *,
    module: Mapping[str, object],
    route_index: int,
    route: Mapping[str, object],
) -> JsonObject:
    return {
        "node_id": _node_id(module),
        "route_index": route_index,
        "has_filter": "filter" in route,
        "filter": _json_copy(route.get("filter"))
        if "filter" in route
        else None,
    }


def _write_response(
    *,
    repo_root: Path,
    project_id: str,
    scenario_path: Path,
    current: JsonObject,
    updated: JsonObject,
    arguments: Mapping[str, object],
    domain_surface: str,
    operation: str,
    target: JsonObject,
) -> JsonObject:
    changed = current != updated
    dry_run = _bool_argument(arguments.get("dry_run"), default=True)
    if changed and not dry_run:
        _write_json_object(scenario_path, updated)
    return {
        "status": "dry_run" if dry_run else "updated",
        "project_id": project_id,
        "domain_surface": domain_surface,
        "operation": operation,
        "dry_run": dry_run,
        "changed": bool(changed and not dry_run),
        "would_change": changed,
        "writes_performed": bool(changed and not dry_run),
        "write_actions": [f"write_project_{domain_surface}"]
        if changed and not dry_run
        else [],
        "target": target,
        "project": _project_metadata(
            repo_root=repo_root,
            project_id=project_id,
            scenario_path=scenario_path,
        ),
        **_local_offline_safety_flags(),
    }


def _project_metadata(
    *, repo_root: Path, project_id: str, scenario_path: Path
) -> JsonObject:
    project_path = _local_project_display_path(
        repo_root=repo_root, path=scenario_path.parent
    )
    scenario_path_text = _local_project_display_path(
        repo_root=repo_root, path=scenario_path
    )
    metadata_row = _local_project_metadata_row(
        repo_root=repo_root, project_id=project_id
    )
    if metadata_row is not None:
        path_report = _local_project_path_report(
            repo_root=repo_root,
            scenario_path=scenario_path,
            project_kind=str(metadata_row["project_kind"]),
        )
        return {
            "project_id": project_id,
            "project_kind": metadata_row["project_kind"],
            "project_path": project_path,
            "scenario_path": scenario_path_text,
            **path_report,
            "source_of_truth": f"sqlite:{LOCAL_PROJECT_METADATA_TABLE}",
            "artifact_source": "generated_project_envelope",
            "artifact_status": (
                "artifact_present"
                if scenario_path.exists()
                else "sqlite_metadata_without_artifact"
            ),
            "sqlite_ssot_path": DEFAULT_KNOWLEDGE_DB_PATH.as_posix(),
            "sqlite_project_metadata_table": LOCAL_PROJECT_METADATA_TABLE,
            "artifact_folder_policy": LOCAL_PROJECT_FOLDER_POLICY,
            "workspace_folder_key": _metadata_workspace_folder_key(
                metadata_row
            ),
            "scenario_or_product_key": metadata_row["scenario_or_product_key"],
            "project_slug": metadata_row["project_slug"],
            "folder_reconstructable_from_sqlite": True,
            "core_business_state_written": False,
        }
    scenario: JsonObject | None = None
    if scenario_path.exists():
        try:
            scenario = _read_json_object(scenario_path)
        except (json.JSONDecodeError, OSError, ValueError):
            scenario = None
    project_kind = _local_project_kind(
        project_id=project_id, scenario=scenario or {}
    )
    path_report = _local_project_path_report(
        repo_root=repo_root,
        scenario_path=scenario_path,
        project_kind=project_kind,
    )
    artifact_policy_status = str(path_report["artifact_policy_status"])
    planned_envelope = bool(path_report["generated_state_physical_path"])
    approved_template = (
        artifact_policy_status == "approved_repo_template_library"
    )
    return {
        "project_id": project_id,
        "project_kind": project_kind,
        "project_path": project_path,
        "scenario_path": scenario_path_text,
        **path_report,
        "source_of_truth": (
            f"sqlite:{LOCAL_PROJECT_METADATA_TABLE}"
            if planned_envelope
            else "local_template_library"
            if approved_template
            else "local_project_scenario"
        ),
        "artifact_source": (
            "planned_project_envelope"
            if planned_envelope
            else "template_library_json"
            if approved_template
            else "legacy_project_json"
        ),
        "artifact_status": (
            "planned_sqlite_metadata"
            if planned_envelope
            else "approved_template_library"
            if approved_template
            else "legacy_folder_without_sqlite_metadata"
        ),
        "sqlite_ssot_path": DEFAULT_KNOWLEDGE_DB_PATH.as_posix(),
        "sqlite_project_metadata_table": LOCAL_PROJECT_METADATA_TABLE,
        "artifact_folder_policy": LOCAL_PROJECT_FOLDER_POLICY,
        "folder_reconstructable_from_sqlite": planned_envelope,
        "core_business_state_written": False,
    }


def _local_project_path_report(
    *,
    repo_root: Path,
    scenario_path: Path,
    project_kind: str | None = None,
) -> JsonObject:
    physical_project_path = _local_project_display_path(
        repo_root=repo_root,
        path=scenario_path.parent,
    )
    physical_scenario_path = _local_project_display_path(
        repo_root=repo_root,
        path=scenario_path,
    )
    generated_root = _local_project_generated_state_root(repo_root)
    resolved_scenario = scenario_path.resolve()
    if (
        resolved_scenario == generated_root
        or generated_root in resolved_scenario.parents
    ):
        generated_relative_scenario = resolved_scenario.relative_to(
            generated_root
        )
        logical_scenario_path = PROJECT_ROOT / generated_relative_scenario
        return {
            "logical_project_path": logical_scenario_path.parent.as_posix(),
            "logical_scenario_path": logical_scenario_path.as_posix(),
            "physical_artifact_path": physical_project_path,
            "physical_scenario_artifact_path": physical_scenario_path,
            "artifact_policy_status": "approved_generated_state",
            "artifact_policy_detail": (
                "Physical artifacts live under approved temp generated state; "
                "projects/* "
                "paths are logical project coordinates only."
            ),
            "generated_state_physical_path": True,
            "legacy_migration_plan": {"status": "not_required"},
        }
    if _approved_template_library_path(
        physical_project_path=physical_project_path,
        project_kind=project_kind,
    ):
        return {
            "logical_project_path": physical_project_path,
            "logical_scenario_path": physical_scenario_path,
            "physical_artifact_path": physical_project_path,
            "physical_scenario_artifact_path": physical_scenario_path,
            "artifact_policy_status": "approved_repo_template_library",
            "artifact_policy_detail": (
                "Reusable redacted template libraries are approved under "
                "projects/templates."
            ),
            "generated_state_physical_path": False,
            "legacy_migration_plan": {
                "status": "not_required ",
                "reason": (
                    "projects/templates is the approved tracked "
                    "template-library surface."
                ),
            },
        }
    return {
        "logical_project_path": physical_project_path,
        "logical_scenario_path": physical_scenario_path,
        "physical_artifact_path": physical_project_path,
        "physical_scenario_artifact_path": physical_scenario_path,
        "artifact_policy_status": "legacy_repo_project_artifact",
        "artifact_policy_detail": (
            "This legacy project is physically stored under the repository "
            "projects folder."
        ),
        "generated_state_physical_path": False,
        "legacy_migration_plan": _legacy_project_artifact_migration_plan(
            logical_project_path=physical_project_path,
            physical_scenario_path=physical_scenario_path,
        ),
    }


def _approved_template_library_path(
    *,
    physical_project_path: str,
    project_kind: str | None,
) -> bool:
    if project_kind != "template_library":
        return False
    template_root = (PROJECT_ROOT / "templates").as_posix()
    return (
        physical_project_path == template_root
        or physical_project_path.startswith(f"{template_root}/")
    )


def _legacy_project_artifact_migration_plan(
    *,
    logical_project_path: str,
    physical_scenario_path: str,
) -> JsonObject:
    return {
        "status": "migration_recommended ",
        "reason": "Repo-local projects/* artifacts are legacy generated state.",
        "source_scenario_path": physical_scenario_path,
        "target_generated_state_root": LOCAL_PROJECT_ARTIFACT_ROOT.as_posix(),
        "recommended_action": (
            "Create a SQLite metadata envelope for the project, copy "
            "scenario.json into "
            "temp/pancakes/project-artifacts, validate project.verify, then "
            "remove the "
            f"legacy {logical_project_path} folder."
        ),
        "cleanup_allowed_after": (
            "A local_project_metadata row exists, the generated-state scenario "
            "is present, and "
            "project.verify passes for the migrated project."
        ),
    }


def _local_project_artifact_rows(
    *, repo_root: Path, query: str | None
) -> tuple[JsonObject, ...]:
    projects_root = repo_root / PROJECT_ROOT
    rows_by_project_id: dict[str, JsonObject] = {}
    metadata_scenario_paths: set[Path] = set()
    query_text = query.casefold() if query else None
    for metadata_row in _local_project_metadata_rows(repo_root=repo_root):
        project_id = str(metadata_row["project_id"])
        scenario_path = _local_project_metadata_path(
            repo_root=repo_root,
            path_text=str(metadata_row["scenario_artifact_path"]),
        )
        metadata_scenario_paths.add(scenario_path.resolve())
        row = _local_project_row_from_path(
            repo_root=repo_root,
            scenario_path=scenario_path,
            project_id=project_id,
            metadata_row=metadata_row,
        )
        if _local_project_row_matches_query(row=row, query_text=query_text):
            rows_by_project_id[project_id] = row
    if not projects_root.exists():
        return tuple(
            sorted(
                rows_by_project_id.values(),
                key=lambda row: (
                    str(row["project_kind"]),
                    str(row["project_id"]),
                ),
            )
        )
    for scenario_path in sorted(projects_root.rglob(SCENARIO_FILE_NAME)):
        if scenario_path.resolve() in metadata_scenario_paths:
            continue
        scenario: JsonObject | None = None
        try:
            scenario = _read_json_object(scenario_path)
        except (json.JSONDecodeError, OSError, ValueError):
            scenario = None
        project_id = _local_project_id_from_scenario(
            scenario=scenario,
            scenario_path=scenario_path,
        )
        if project_id in rows_by_project_id:
            continue
        row = _local_project_row_from_path(
            repo_root=repo_root,
            scenario_path=scenario_path,
            project_id=project_id,
            metadata_row=None,
            scenario=scenario,
        )
        if not _local_project_row_matches_query(row=row, query_text=query_text):
            continue
        rows_by_project_id[project_id] = row
    return tuple(
        sorted(
            rows_by_project_id.values(),
            key=lambda row: (str(row["project_kind"]), str(row["project_id"])),
        )
    )


def _local_project_row_from_path(
    *,
    repo_root: Path,
    scenario_path: Path,
    project_id: str,
    metadata_row: Mapping[str, object] | None,
    scenario: JsonObject | None = None,
) -> JsonObject:
    if metadata_row is not None:
        scenario_path = _local_project_metadata_path(
            repo_root=repo_root,
            path_text=str(metadata_row["scenario_artifact_path"]),
        )
    else:
        scenario_path = _project_root_confined_path(
            repo_root=repo_root, path=scenario_path
        )
    if scenario is None and scenario_path.exists():
        try:
            scenario = _read_json_object(scenario_path)
        except (json.JSONDecodeError, OSError, ValueError):
            scenario = {}
    if scenario is None:
        scenario = {}
    if scenario:
        summary = _scenario_summary(scenario)
    else:
        summary = {
            "module_count": 0,
            "link_count": 0,
            "link_count_semantics": "deduped_semantic_execution_links",
            "raw_route_and_flow_edge_count": 0,
            "route_count": 0,
            "filter_count": 0,
            "error_handler_count": 0,
        }
    name = _optional_text(scenario.get("name")) or project_id
    if metadata_row is None:
        project_kind = _local_project_kind(
            project_id=project_id, scenario=scenario
        )
        source_of_truth = "local_project_scenario"
        workspace_folder_key = None
        scenario_or_product_key = None
    else:
        project_kind = str(metadata_row["project_kind"])
        source_of_truth = f"sqlite:{LOCAL_PROJECT_METADATA_TABLE}"
        workspace_folder_key = _metadata_workspace_folder_key(metadata_row)
        scenario_or_product_key = metadata_row["scenario_or_product_key"]
    path_report = _local_project_path_report(
        repo_root=repo_root,
        scenario_path=scenario_path,
        project_kind=project_kind,
    )
    if metadata_row is None:
        approved_template = (
            path_report["artifact_policy_status"]
            == "approved_repo_template_library"
        )
        if approved_template:
            source_of_truth = "local_template_library"
            artifact_source = "template_library_json"
            artifact_status = "approved_template_library"
        else:
            artifact_source = "legacy_project_json"
            artifact_status = (
                "legacy_folder_without_sqlite_metadata"
                if path_report["artifact_policy_status"]
                == "legacy_repo_project_artifact"
                else "artifact_present"
            )
    else:
        artifact_source = "generated_project_envelope"
        artifact_status = (
            "artifact_present"
            if scenario_path.exists()
            else "sqlite_metadata_without_artifact"
        )
    row: JsonObject = {
        "project_id": project_id,
        "display_name": name,
        "project_kind": project_kind,
        "source_of_truth": source_of_truth,
        "artifact_source": artifact_source,
        "artifact_status": artifact_status,
        "scenario_path": _local_project_display_path(
            repo_root=repo_root, path=scenario_path
        ),
        **path_report,
        **summary,
    }
    if workspace_folder_key is not None:
        row["workspace_folder_key"] = workspace_folder_key
    if scenario_or_product_key is not None:
        row["scenario_or_product_key"] = scenario_or_product_key
    return row


def _metadata_workspace_folder_key(
    metadata_row: Mapping[str, object],
) -> object:
    if "workspace_folder_key" in metadata_row:
        return metadata_row["workspace_folder_key"]
    return metadata_row["customer_folder_key"]


def _local_project_id_from_scenario(
    *,
    scenario: Mapping[str, object] | None,
    scenario_path: Path,
) -> str:
    if scenario is not None:
        metadata = scenario.get("metadata")
        if isinstance(metadata, dict):
            project_id = _optional_text(
                cast("Mapping[str, object]", metadata).get("project_id")
            )
            if project_id:
                return project_id
    return scenario_path.parent.name


def _local_project_row_matches_query(
    *, row: Mapping[str, object], query_text: str | None
) -> bool:
    if query_text is None:
        return True
    searchable = (
        str(row.get("project_id") or ""),
        str(row.get("display_name") or ""),
        str(row.get("scenario_path") or ""),
    )
    return any(query_text in value.casefold() for value in searchable)


def _local_project_storage_request(
    *,
    arguments: Mapping[str, object],
    repo_root: Path,
) -> JsonObject:
    project_id = _required_project_id(arguments)
    workspace_key = _safe_project_folder_component(
        arguments.get("workspace_folder_key")
        or arguments.get("workspace_key")
        or arguments.get("workspace_number"),
        default=DEFAULT_LOCAL_PROJECT_WORKSPACE_KEY,
    )
    scenario_key = _safe_project_folder_component(
        arguments.get("scenario_or_product_key")
        or arguments.get("scenario_or_product_number")
        or arguments.get("scenario_number")
        or arguments.get("product_number"),
        default=DEFAULT_LOCAL_PROJECT_SCENARIO_KEY,
    )
    project_slug = _safe_project_folder_component(
        arguments.get("project_slug") or project_id,
        default=project_id,
    )
    logical_project_path = (
        PROJECT_ROOT / workspace_key / f"{scenario_key}-{project_slug}"
    )
    envelope_path = (
        LOCAL_PROJECT_ARTIFACT_ROOT
        / workspace_key
        / f"{scenario_key}-{project_slug}"
    )
    scenario_artifact_path = envelope_path / SCENARIO_FILE_NAME
    logical_scenario_path = logical_project_path / SCENARIO_FILE_NAME
    import_evidence_path = (
        envelope_path / "artifacts" / BLUEPRINT_IMPORT_EVIDENCE_FILE_NAME
    )
    scenario_path = _local_project_generated_state_confined_path(
        repo_root=repo_root,
        path=_operator_workspace_root(repo_root) / scenario_artifact_path,
    )
    return {
        "workspace_folder_key": workspace_key,
        "scenario_or_product_key": scenario_key,
        "project_slug": project_slug,
        "logical_project_path": logical_project_path.as_posix(),
        "logical_scenario_path": logical_scenario_path.as_posix(),
        "artifact_envelope_path": envelope_path.as_posix(),
        "scenario_artifact_path": scenario_artifact_path.as_posix(),
        "import_evidence_path": import_evidence_path.as_posix(),
        "scenario_path": scenario_path,
    }


def _safe_project_folder_component(value: object, *, default: str) -> str:
    text = _optional_text(value) or default
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", text.strip()).strip("-_")
    if not normalized or normalized in {".", ".."}:
        normalized = default
    if not all(char.isalnum() or char in {"-", "_"} for char in normalized):
        msg = "Project folder component must be repository-local and safe."
        raise ValueError(msg)
    return normalized


def _pancakes_sqlite_path(repo_root: Path) -> Path:
    return (repo_root / DEFAULT_KNOWLEDGE_DB_PATH).resolve()


def _local_project_metadata_row(
    *,
    repo_root: Path,
    project_id: str,
) -> JsonObject | None:
    database_path = _pancakes_sqlite_path(repo_root)
    if not database_path.exists():
        return None
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        if not _sqlite_table_exists(connection, LOCAL_PROJECT_METADATA_TABLE):
            return None
        row = cast(
            "sqlite3.Row | None",
            connection.execute(
                """
                SELECT *
                FROM local_project_metadata
                WHERE project_id = ?
                  AND valid_to IS NULL
                LIMIT 1
                """,
                (project_id,),
            ).fetchone(),
        )
        if row is None:
            return None
        return cast("JsonObject", {key: row[key] for key in row})
    finally:
        connection.close()


def _local_project_metadata_rows(*, repo_root: Path) -> tuple[JsonObject, ...]:
    database_path = _pancakes_sqlite_path(repo_root)
    if not database_path.exists():
        return ()
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        if not _sqlite_table_exists(connection, LOCAL_PROJECT_METADATA_TABLE):
            return ()
        rows = cast(
            "list[sqlite3.Row]",
            connection.execute(
                """
                SELECT *
                FROM local_project_metadata
                WHERE valid_to IS NULL
                ORDER BY project_id ASC
                """
            ).fetchall(),
        )
        return tuple(
            cast("JsonObject", {key: row[key] for key in row}) for row in rows
        )
    finally:
        connection.close()


def _upsert_local_project_metadata(
    *,
    repo_root: Path,
    project_id: str,
    project_kind: str,
    storage: Mapping[str, object],
) -> None:
    database_path = _pancakes_sqlite_path(repo_root)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    connection = sqlite3.connect(database_path)
    try:
        _ensure_local_project_metadata_schema(connection)
        columns = _sqlite_column_names(connection, LOCAL_PROJECT_METADATA_TABLE)
        folder_key_column = (
            "workspace_folder_key"
            if "workspace_folder_key" in columns
            else "customer_folder_key"
        )
        _ = connection.execute(
            f"""  # noqa: S608
            INSERT INTO local_project_metadata (
              project_id,
              project_kind,
              {folder_key_column},
              scenario_or_product_key,
              project_slug,
              artifact_envelope_path,
              scenario_artifact_path,
              source_kind,
              source_ref,
              created_at_utc,
              updated_at_utc,
              valid_to
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                project_id,
                project_kind,
                str(storage["workspace_folder_key"]),
                str(storage["scenario_or_product_key"]),
                str(storage["project_slug"]),
                str(storage["artifact_envelope_path"]),
                str(storage["scenario_artifact_path"]),
                "mcp:project.create ",
                "project.create",
                now,
                now,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _ensure_local_project_metadata_schema(
    connection: sqlite3.Connection,
) -> None:
    _ = connection.execute(LOCAL_PROJECT_METADATA_DDL)
    for statement in LOCAL_PROJECT_METADATA_INDEX_DDL:
        _ = connection.execute(statement)


def _local_project_kind(
    *, project_id: str, scenario: Mapping[str, object]
) -> str:
    metadata = scenario.get("metadata")
    if isinstance(metadata, dict):
        configured = _optional_text(
            cast("Mapping[str, object]", metadata).get("project_kind")
        )
        if configured in {
            "local_scenario_project ",
            "template_library ",
            "fixture_project ",
            "deleted_or_archived_project ",
            "invalid_project_artifact",
        }:
            return configured
        if configured == "scenario_project":
            return "local_scenario_project"
    if project_id.casefold() in {"template", "templates"}:
        return "template_library"
    if project_id.casefold().startswith(("fixture-", "fixtures-")):
        return "fixture_project"
    return "local_scenario_project"


def _sqlite_table_exists(
    connection: sqlite3.Connection, table_name: str
) -> bool:
    row = cast(
        "object | None",
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? "
            "LIMIT 1",
            (table_name,),
        ).fetchone(),
    )
    return row is not None


def _sqlite_column_names(
    connection: sqlite3.Connection, table_name: str
) -> frozenset[str]:
    rows = cast(
        "list[tuple[object, ...]]",
        connection.execute(f"PRAGMA table_info({table_name})").fetchall(),
    )
    return frozenset(str(row[1]) for row in rows)


def _relative_to_repo(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        msg = "Path escaped the repository root."
        raise ValueError(msg) from exc


def _local_offline_safety_flags() -> JsonObject:
    return {
        "provider_api_call": False,
        "credential_value_transfer": False,
        "secret_output": False,
        "live_make_called": False,
        "credentials_required": False,
    }


def _optional_text(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, int):
        return str(value)
    return None


def _text_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(
        item
        for item in cast("list[object]", value)
        if isinstance(item, str) and item.strip()
    )


def _bool_argument(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.casefold()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    msg = "Expected a boolean argument."
    raise ValueError(msg)


def _bounded_int(value: object, *, default: int, upper: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        msg = "Expected an integer argument."
        raise ValueError(msg)
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.isdecimal():
        parsed = int(value)
    else:
        msg = "Expected an integer argument."
        raise ValueError(msg)
    return max(1, min(parsed, upper))


def _nonnegative_int(value: object, *, default: int, upper: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        msg = "Expected an integer argument."
        raise ValueError(msg)
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.isdecimal():
        parsed = int(value)
    else:
        msg = "Expected an integer argument."
        raise ValueError(msg)
    return max(0, min(parsed, upper))


def _mapping_member(
    mapping: MutableMapping[str, object], key: str
) -> JsonObject:
    value = mapping.get(key)
    if not isinstance(value, dict):
        msg = f"{key} is missing."
        raise ValueError(msg)
    return cast("JsonObject", value)


def _merge_patch(
    target: MutableMapping[str, object], patch: Mapping[str, object]
) -> None:
    for key, value in patch.items():
        if value is None:
            _ = target.pop(key, None)
        elif isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge_patch(
                cast("MutableMapping[str, object]", target[key]),
                cast("Mapping[str, object]", value),
            )
        else:
            target[key] = _json_copy(cast("object", value))


def _json_copy(value: object) -> object:
    return cast("object", json.loads(json.dumps(value)))


bool_argument = _bool_argument
bounded_int = _bounded_int
derive_links = _derive_links
filter_summary = _filter_summary
flow_from_mapping = _flow_from_mapping
flow_path = _flow_path
handlers_for_module = _handlers_for_module
insert_position = _insert_position
iter_modules = _iter_modules
iter_routes = _iter_routes
json_copy = _json_copy
json_object_argument = _json_object_argument
legacy_scenario_path = _legacy_scenario_path
local_offline_safety_flags = _local_offline_safety_flags
local_project_artifact_rows = _local_project_artifact_rows
local_project_display_path = _local_project_display_path
local_project_metadata_row = _local_project_metadata_row
local_project_path_report = _local_project_path_report
local_project_storage_request = _local_project_storage_request
mapping_member = _mapping_member
merge_patch = _merge_patch
module_summary = _module_summary
node_id = _node_id
nonnegative_int = _nonnegative_int
operator_workspace_root = _operator_workspace_root
optional_node_id = _optional_node_id
optional_text = _optional_text
path_has_prefix = _path_has_prefix
project_metadata = _project_metadata
raw_route_and_flow_edge_count = _raw_route_and_flow_edge_count
read_json_object = _read_json_object
remove_module = _remove_module
require_unique_node_id = _require_unique_node_id
required_module = _required_module
required_node_id = _required_node_id
required_project_id = _required_project_id
routes_for_module = _routes_for_module
scenario_path = _scenario_path
scenario_summary = _scenario_summary
target_flow = _target_flow
text_list = _text_list
upsert_local_project_metadata = _upsert_local_project_metadata
write_json_object = _write_json_object
write_response = _write_response
