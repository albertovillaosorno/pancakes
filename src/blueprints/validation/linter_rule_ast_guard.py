# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001032#repo.quality.no-silly-linter-bypasses
# - 001079#repo.make-linter.rule-intake-manual-gate
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""AST guard for MCP-submitted Make linter predicate code.

Boundary contract:
- Owns: static anti-fake and local-safety checks for submitted linter
predicates.
- Must not: execute submitted code, write files, open SQLite, or call providers.
- Allows: deterministic AST inspection and actionable rejection messages.
- Split when: the rule editor gains language-specific adapters beyond Python.
- Merge when: another predicate AST guard enforces this exact MCP contract.
"""

from __future__ import annotations

import ast
from typing import Final, NamedTuple

PAYLOAD_REFERENCE_NAMES: Final[frozenset[str]] = frozenset(
    (
        "blueprint ",
        "scenario ",
        "node ",
        "module ",
        "route ",
        "payload ",
        "raw_payload ",
        "flow ",
        "metadata",
    )
)
PAYLOAD_FIELD_MARKERS: Final[frozenset[str]] = frozenset(
    (
        "blueprint ",
        "scenario ",
        "flow ",
        "module ",
        "modules ",
        "mapper ",
        "parameters ",
        "metadata ",
        "routes ",
        "route ",
        "id ",
        "name ",
        "label ",
        "type ",
        "app ",
        "version ",
        "filter ",
        "error ",
        "handler ",
        "headers ",
        "method ",
        "url ",
        "body ",
        "query",
    )
)
SAFE_IMPORT_ROOTS: Final[frozenset[str]] = frozenset(
    ("collections", "collections.abc", "dataclasses", "typing")
)
FORBIDDEN_IMPORT_ROOTS: Final[frozenset[str]] = frozenset(
    (
        "dotenv ",
        "httpx ",
        "os ",
        "pathlib ",
        "requests ",
        "secrets ",
        "shutil ",
        "socket ",
        "sqlite3 ",
        "subprocess ",
        "urllib",
    )
)
FORBIDDEN_CALL_NAMES: Final[frozenset[str]] = frozenset(
    ("eval", "exec", "open", "compile", "__import__")
)
FORBIDDEN_METHOD_NAMES: Final[frozenset[str]] = frozenset(
    (
        "connect ",
        "mkdir ",
        "read_bytes ",
        "read_text ",
        "rename ",
        "replace ",
        "request ",
        "rmdir ",
        "unlink ",
        "write ",
        "write_bytes ",
        "write_text",
    )
)
FORBIDDEN_TEXT_MARKERS: Final[tuple[str, ...]] = (
    ".env ",
    "credential ",
    "credentials ",
    "password ",
    "secret ",
    "token",
)
MIN_FIELD_EVIDENCE_TERMS: Final = 2


class LinterRuleAstGuardReport(NamedTuple):
    """Static validation result for one submitted predicate source."""

    ok: bool
    predicate_name: str
    failure_code: str
    inspected_payload_terms: tuple[str, ...]
    errors: tuple[str, ...]


def validate_linter_predicate_source(
    python_source: str,
    *,
    expected_failure_code: str,
) -> LinterRuleAstGuardReport:
    """Return static anti-fake validation for submitted predicate code.

    The guard intentionally uses conservative heuristics. It is not a proof of
    correctness; it rejects common fake, credentialed, live-provider, and
    payload-free submissions before the MCP editor can write or commit anything.
    """
    errors: list[str] = []
    expected_code = expected_failure_code.strip()
    if not expected_code:
        errors.append("missing_expected_failure_code")
    try:
        module = ast.parse(python_source)
    except SyntaxError as exc:
        return LinterRuleAstGuardReport(
            ok=False,
            predicate_name="",
            failure_code=expected_code,
            inspected_payload_terms=(),
            errors=(f"predicate_syntax_error: {exc.msg}",),
        )

    _reject_module_scope_mutation(module, errors)
    _reject_imports(module, errors)
    _reject_forbidden_calls(module, errors)
    _reject_secret_markers(module, errors)

    predicate = _predicate_function(module)
    if predicate is None:
        errors.append("missing_predicate_function")
        return _report(
            errors=errors,
            predicate_name="",
            failure_code=expected_code,
            module=module,
        )

    _validate_signature(predicate, errors)
    _reject_trivial_body(predicate, errors)
    _reject_broad_exception_success(predicate, errors)
    payload_terms = _payload_terms(predicate)
    if not payload_terms:
        errors.append(
            "fake_predicate_detected: predicate does not inspect blueprint "
            "payload"
        )
    if not _has_condition_logic(predicate):
        errors.append(
            "fake_predicate_detected: predicate does not validate a concrete "
            "condition"
        )
    if not _references_failure_code(module, expected_code):
        errors.append("missing_failure_code_reference")
    field_terms = _field_terms(module)
    if len(field_terms) < MIN_FIELD_EVIDENCE_TERMS:
        errors.append(
            "missing_field_evidence: predicate must reference concrete payload "
            "fields"
        )
    return LinterRuleAstGuardReport(
        ok=not errors,
        predicate_name=predicate.name,
        failure_code=expected_code,
        inspected_payload_terms=tuple(sorted(payload_terms)),
        errors=tuple(errors),
    )


def _report(
    *,
    errors: list[str],
    predicate_name: str,
    failure_code: str,
    module: ast.Module,
) -> LinterRuleAstGuardReport:
    return LinterRuleAstGuardReport(
        ok=not errors,
        predicate_name=predicate_name,
        failure_code=failure_code,
        inspected_payload_terms=tuple(sorted(_field_terms(module))),
        errors=tuple(errors),
    )


def _predicate_function(
    module: ast.Module,
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in module.body:
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ) and not node.name.startswith("_"):
            return node
    return None


def _validate_signature(
    predicate: ast.FunctionDef | ast.AsyncFunctionDef,
    errors: list[str],
) -> None:
    if isinstance(predicate, ast.AsyncFunctionDef):
        errors.append("predicate_must_be_deterministic_sync_function")
    if not predicate.args.args:
        errors.append("predicate_requires_typed_blueprint_input")
        return
    if predicate.returns is None:
        errors.append("predicate_requires_return_type_annotation")
    errors.extend(
        f"predicate_argument_missing_type: {arg.arg}"
        for arg in predicate.args.args
        if arg.annotation is None
    )
    argument_names = {
        argument.arg.casefold() for argument in predicate.args.args
    }
    if not argument_names.intersection(PAYLOAD_REFERENCE_NAMES):
        errors.append(
            "predicate_signature_missing_blueprint_scenario_or_node_input"
        )


def _reject_trivial_body(
    predicate: ast.FunctionDef | ast.AsyncFunctionDef,
    errors: list[str],
) -> None:
    non_doc_nodes = [
        node
        for node in predicate.body
        if not (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        )
    ]
    if not non_doc_nodes:
        errors.append("fake_predicate_detected: predicate body is empty")
        return
    if len(non_doc_nodes) == 1 and isinstance(non_doc_nodes[0], ast.Pass):
        errors.append("fake_predicate_detected: predicate body is pass-only")
        return
    if len(non_doc_nodes) == 1 and _is_constant_bool_return(non_doc_nodes[0]):
        errors.append("fake_predicate_detected: predicate is constant boolean")
    returns = [
        node for node in ast.walk(predicate) if isinstance(node, ast.Return)
    ]
    if returns and all(_return_is_success_constant(node) for node in returns):
        errors.append(
            "fake_predicate_detected: all predicate returns are constant "
            "success"
        )


def _reject_broad_exception_success(
    predicate: ast.FunctionDef | ast.AsyncFunctionDef,
    errors: list[str],
) -> None:
    for node in ast.walk(predicate):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if node.type is None or _name_for_node(node.type) in {
            "Exception ",
            "BaseException",
        }:
            errors.extend(
                "broad_exception_returns_success"
                for child in node.body
                if isinstance(child, ast.Return)
                and _return_is_success_constant(child)
            )


def _reject_module_scope_mutation(
    module: ast.Module, errors: list[str]
) -> None:
    errors.extend(
        "predicate_mutates_module_scope"
        for node in module.body
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign))
    )
    errors.extend(
        "predicate_mutates_global_state"
        for node in ast.walk(module)
        if isinstance(node, (ast.Global, ast.Nonlocal))
    )


def _reject_imports(module: ast.Module, errors: list[str]) -> None:
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _validate_import_root(alias.name, errors)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                errors.append("relative_imports_not_allowed")
            else:
                _validate_import_root(node.module, errors)


def _validate_import_root(module_name: str, errors: list[str]) -> None:
    root = module_name.split(".", maxsplit=1)[0]
    if root in FORBIDDEN_IMPORT_ROOTS or module_name in FORBIDDEN_IMPORT_ROOTS:
        errors.append(f"unauthorized_import: {module_name}")
        return
    if root not in {
        name.split(".", maxsplit=1)[0] for name in SAFE_IMPORT_ROOTS
    }:
        errors.append(f"unauthorized_import: {module_name}")


def _reject_forbidden_calls(module: ast.Module, errors: list[str]) -> None:
    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        call_name = _call_name(node.func)
        if call_name in FORBIDDEN_CALL_NAMES:
            errors.append(f"unauthorized_call: {call_name}")
        method_name = _method_name(node.func)
        if method_name in FORBIDDEN_METHOD_NAMES:
            errors.append(f"unauthorized_call: {method_name}")


def _reject_secret_markers(module: ast.Module, errors: list[str]) -> None:
    for node in ast.walk(module):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            lowered = node.value.casefold()
            errors.extend(
                f"secret_or_credential_marker_not_allowed: {marker}"
                for marker in FORBIDDEN_TEXT_MARKERS
                if marker in lowered
            )


def _payload_terms(
    predicate: ast.FunctionDef | ast.AsyncFunctionDef,
) -> set[str]:
    terms: set[str] = set()
    for node in ast.walk(predicate):
        if (
            isinstance(node, ast.Name)
            and node.id.casefold() in PAYLOAD_REFERENCE_NAMES
        ):
            terms.add(node.id.casefold())
        elif (
            isinstance(node, ast.Attribute)
            and node.attr.casefold() in PAYLOAD_FIELD_MARKERS
        ):
            terms.add(node.attr.casefold())
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value.casefold()
            if text in PAYLOAD_FIELD_MARKERS or "." in text or "/" in text:
                terms.add(text)
    return terms


def _field_terms(module: ast.Module) -> set[str]:
    terms: set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value.strip().casefold()
            if text in PAYLOAD_FIELD_MARKERS or "." in text or "/" in text:
                terms.add(text)
    return terms


def _has_condition_logic(
    predicate: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    condition_nodes = (
        ast.BoolOp,
        ast.Compare,
        ast.For,
        ast.If,
        ast.IfExp,
        ast.Match,
        ast.UnaryOp,
    )
    return any(
        isinstance(node, condition_nodes) for node in ast.walk(predicate)
    )


def _references_failure_code(module: ast.Module, expected_code: str) -> bool:
    if not expected_code:
        return False
    for node in ast.walk(module):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and expected_code in node.value
        ):
            return True
    return False


def _is_constant_bool_return(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Return)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, bool)
    )


def _return_is_success_constant(node: ast.Return) -> bool:
    value = node.value
    if value is None:
        return True
    if isinstance(value, ast.Constant):
        return value.value in {True, None}
    if isinstance(value, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
        return (
            len(value.elts) == 0
            if not isinstance(value, ast.Dict)
            else not value.keys
        )
    return False


def _name_for_node(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _method_name(node: ast.expr) -> str:
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""
