# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001046#repo.blueprint-validation.theoretical-cycle-rules
# - 001060#repo.architecture.srp.extreme-one-responsibility
# - 001063#repo.architecture.file-boundary.contract-required
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Detect deterministic theoretical cycles in Make scenario ASTs.

Boundary contract:
- Owns: local validation for scenario self-invocation without exit evidence.
- Must not: call live Make APIs, resolve catalog modules, or infer broad graph
reachability.
- Allows: inspecting typed AST payloads for explicit current-scenario invocation
evidence.
- Split when: cross-scenario live dependency analysis becomes an operator-gated
feature.
- Merge when: another validator owns the same local self-invocation cycle rule.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, TypeGuard, cast

from blueprints.ast.module_roles import module_token_semantic_key
from blueprints.ast.traversal import iter_ast_nodes
from blueprints.validation.findings import build_validation_finding

if TYPE_CHECKING:
    from blueprints.ast.models import JsonObject, MakeAstNode, MakeAstRoot
    from blueprints.validation.models import BlueprintValidationFinding

SCENARIO_IDENTITY_KEYS: Final[frozenset[str]] = frozenset(
    ("id", "name", "scenarioid", "scenarioname", "uid")
)
SCENARIO_IDENTITY_CONTAINERS: Final[frozenset[str]] = frozenset(
    ("scenario", "blueprint")
)
CHILD_FLOW_CONTAINER_KEYS: Final[frozenset[str]] = frozenset(
    ("routes", "branches", "tools")
)
DIRECT_ERROR_CHILD_KEYS: Final[frozenset[str]] = frozenset(
    ("onerror", "on_error")
)
MIN_SCENARIO_IDENTITY_TOKEN_LENGTH: Final = 4
SCENARIO_INVOCATION_TOKENS: Final[tuple[str, ...]] = (
    "callscenario",
    "executescenario",
    "invokescenario",
    "runscenario",
    "startscenario",
)
SCENARIO_SELF_REFERENCE_TOKENS: Final[tuple[str, ...]] = (
    "current",
    "currentscenario",
    "self",
    "thisscenario",
)
SCENARIO_CYCLE_EXIT_TOKENS: Final[tuple[str, ...]] = (
    "attempt",
    "counter",
    "dedupe",
    "depth",
    "exit",
    "exitcondition",
    "guard",
    "halt",
    "idempotency",
    "limit",
    "loopguard",
    "maxdepth",
    "maxiterations",
    "maxruns",
    "once",
    "recursionguard",
    "stop",
    "stopcondition",
    "terminate",
    "termination",
    "terminationcondition",
    "until",
)


def validate_scenario_cycles(
    root: MakeAstRoot,
) -> tuple[BlueprintValidationFinding, ...]:
    """Validate deterministic scenario self-invocation cycle risks.

    Returns:
        Blocking findings for local self-invocation without exit evidence.
    """
    scenario_identifiers = _current_scenario_identifiers(root)
    if not scenario_identifiers:
        return ()
    findings: list[BlueprintValidationFinding] = []
    for node in iter_ast_nodes(root):
        if _node_is_error_path(node):
            continue
        if not _node_targets_current_scenario(
            node, scenario_identifiers=scenario_identifiers
        ):
            continue
        if _node_has_cycle_exit_evidence(node):
            continue
        findings.append(_scenario_self_invocation_finding(node))
    return tuple(findings)


def _node_is_error_path(node: MakeAstNode) -> bool:
    """Return whether one node is reached only through an error-handler path."""
    return any(
        isinstance(part, str) and part in DIRECT_ERROR_CHILD_KEYS
        for part in node.source_trace.path
    )


def _current_scenario_identifiers(root: MakeAstRoot) -> frozenset[str]:
    """Return normalized identifiers for the current scenario."""
    identifiers: set[str] = set()
    _add_identity_token(identifiers, root.scenario.name)
    for candidate in _identity_values(root.raw_payload):
        _add_identity_token(identifiers, candidate)
    for candidate in _identity_values(root.scenario.metadata):
        _add_identity_token(identifiers, candidate)
    scenario_payload = root.scenario.metadata.get("scenario")
    if _is_json_object(scenario_payload):
        for candidate in _identity_values(scenario_payload):
            _add_identity_token(identifiers, candidate)
    return frozenset(identifiers)


def _identity_values(payload: JsonObject) -> tuple[str, ...]:
    """Return top-level scenario identity values from one JSON object."""
    values: list[str] = []
    for key, value in payload.items():
        key_token = module_token_semantic_key(key)
        if key_token in SCENARIO_IDENTITY_KEYS and _identity_scalar(value):
            values.append(str(value))
            continue
        if key_token in SCENARIO_IDENTITY_CONTAINERS and _is_json_object(value):
            values.extend(_identity_values(value))
    return tuple(values)


def _add_identity_token(identifiers: set[str], value: object) -> None:
    """Add one normalized scenario identity token when it is specific enough."""
    if not _identity_scalar(value):
        return
    token = module_token_semantic_key(str(value))
    if len(token) >= MIN_SCENARIO_IDENTITY_TOKEN_LENGTH:
        identifiers.add(token)


def _identity_scalar(value: object) -> bool:
    """Return whether a JSON value can be a scenario identity."""
    return isinstance(value, str | int) and not isinstance(value, bool)


def _node_targets_current_scenario(
    node: MakeAstNode,
    *,
    scenario_identifiers: frozenset[str],
) -> bool:
    """Return whether one node explicitly invokes the current scenario."""
    if not _node_can_invoke_scenario(node):
        return False
    if _json_has_token(
        node.raw_payload,
        tokens=SCENARIO_SELF_REFERENCE_TOKENS,
        node_local=True,
    ):
        return True
    payload_token = module_token_semantic_key(
        _json_text_blob(node.raw_payload, node_local=True)
    )
    return any(
        identifier in payload_token for identifier in scenario_identifiers
    )


def _node_can_invoke_scenario(node: MakeAstNode) -> bool:
    """Return whether one node can invoke a Make scenario."""
    module_token = module_token_semantic_key(node.module_token)
    if any(token in module_token for token in SCENARIO_INVOCATION_TOKENS):
        return True
    if not _node_is_http_api(node):
        return False
    payload_text = _json_text_blob(node.raw_payload, node_local=True)
    payload_token = module_token_semantic_key(payload_text)
    return "scenario" in payload_token and any(
        marker in payload_text
        for marker in ("/scenario", "/scenarios", "api/v2", "make.com")
    )


def _node_is_http_api(node: MakeAstNode) -> bool:
    """Return whether one node is an HTTP/API request module."""
    module_token = module_token_semantic_key(node.module_token)
    return (
        node.kind == "http_api"
        or module_token.startswith("http")
        or "makerequest" in module_token
    )


def _node_has_cycle_exit_evidence(node: MakeAstNode) -> bool:
    """Return whether one self-invocation node declares a local exit guard."""
    return _json_has_token(
        node.raw_payload,
        tokens=SCENARIO_CYCLE_EXIT_TOKENS,
        node_local=True,
    )


def _json_has_token(
    value: object,
    *,
    tokens: tuple[str, ...],
    node_local: bool,
    path: tuple[str | int, ...] = (),
) -> bool:
    """Return if JSON-like data contains one normalized key or text token."""
    if node_local and _descends_into_child_node(path):
        return False
    normalized_tokens = tuple(
        module_token_semantic_key(token) for token in tokens
    )
    if _is_json_object(value):
        for key, item in value.items():
            key_token = module_token_semantic_key(key)
            if any(
                token in key_token for token in normalized_tokens
            ) and _truthy_json(item):
                return True
            if _json_has_token(
                item,
                tokens=tokens,
                node_local=node_local,
                path=(*path, key),
            ):
                return True
    if isinstance(value, list):
        return any(
            _json_has_token(
                item,
                tokens=tokens,
                node_local=node_local,
                path=(*path, index),
            )
            for index, item in enumerate(cast("list[object]", value))
        )
    if isinstance(value, str):
        value_token = module_token_semantic_key(value)
        return any(token in value_token for token in normalized_tokens)
    return False


def _json_text_blob(
    value: object,
    *,
    node_local: bool,
    path: tuple[str | int, ...] = (),
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


def _descends_into_child_node(path: tuple[str | int, ...]) -> bool:
    """Return whether a node-local scan path enters a nested child node."""
    string_parts = tuple(part for part in path if isinstance(part, str))
    if any(part in DIRECT_ERROR_CHILD_KEYS for part in string_parts):
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


def _truthy_json(value: object) -> bool:
    """Return whether a JSON configuration value is meaningfully enabled."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        return module_token_semantic_key(value) not in {
            "",
            "false",
            "no",
            "none",
            "off",
            "0",
        }
    if isinstance(value, dict):
        return bool(cast("dict[object, object]", value))
    if isinstance(value, list):
        return bool(cast("list[object]", value))
    return value is not None


def _scenario_self_invocation_finding(
    node: MakeAstNode,
) -> BlueprintValidationFinding:
    """Return a blocking self-invocation cycle finding."""
    return build_validation_finding(
        code="semantic.scenario_self_invocation_cycle",
        severity="error",
        node=(node.node_id, node.source_trace.path),
        catalog_module_id=None,
        messages=(
            "A scenario appears to invoke itself without an exit condition.",
            (
                f"Node {node.node_id} targets the current scenario without "
                f"local cycle guard evidence."
            ),
        ),
    )


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    """Return whether a value is a string-keyed JSON object."""
    if not isinstance(value, dict):
        return False
    raw_mapping = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in raw_mapping)
