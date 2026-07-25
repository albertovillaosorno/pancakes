# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001046#repo.blueprint-validation.validator-policy
# - 001061#repo.delivery.client-ready-handoff-contract
# - 001068#repo.operator-commands.command-registry
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Setup-readiness checks over local Make designer and validation evidence.

Boundary contract:
- Owns: local setup-required diagnostics that block client-ready Golden
completion.
- Must not: call Make.com, compare semantic parity, inspect privacy, or mutate
payloads.
- Allows: deterministic projection from designer diagnostic JSON and validation
findings.
- Split when: live Make setup probing or repair planning needs independent
ownership.
- Merge when: another validation module emits the same setup-readiness report.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Literal, NamedTuple, cast

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from blueprints.ast.models import JsonObject
    from blueprints.validation.models import (
        BlueprintFindingSeverity,
        BlueprintValidationFinding,
    )

type SetupReadinessDimension = Literal["setup_readiness"]
type SetupReadinessSource = Literal["designer_diagnostic", "validation_finding"]

SETUP_REQUIRED_CATEGORY: Final = "setupreq"
SETUP_REQUIRED_CATEGORIES: Final[frozenset[str]] = frozenset(
    ("setup", SETUP_REQUIRED_CATEGORY, "epochreq")
)
SETUP_REQUIRED_MESSAGE_MARKERS: Final[tuple[str, ...]] = (
    "module is not set up",
    "not set up",
    "setup required",
    "requires setup",
    "requires runtime setup",
    "value must not be empty",
    "must first choose from which point",
)
SETUP_READINESS_BLOCKER: Final = "setup_readiness"
SETUP_READINESS_BLOCKER_CODE: Final = "setup_readiness.setup_required"
MODULE_FIELD_KEYS: Final[tuple[str, ...]] = (
    "affected_module",
    "module",
    "module_id",
    "moduleId",
    "module_token",
    "node_id",
    "nodeId",
)
EVIDENCE_PATH_FIELD_KEYS: Final[tuple[str, ...]] = (
    "evidence_path",
    "evidencePath",
    "source_path",
    "sourcePath",
    "json_pointer",
    "jsonPointer",
    "path",
)


class SetupReadinessFinding(NamedTuple):
    """One setup-required finding derived from local evidence."""

    dimension: SetupReadinessDimension
    source: SetupReadinessSource
    affected_module: str | None
    category: str
    severity: BlueprintFindingSeverity
    message: str
    evidence_path: str | None
    model_dependent_uncertainty: tuple[str, ...]

    def as_dict(self) -> JsonObject:
        """Return a JSON-ready setup-readiness finding payload."""
        return {
            "dimension": self.dimension,
            "source": self.source,
            "affected_module": self.affected_module,
            "category": self.category,
            "severity": self.severity,
            "message": self.message,
            "evidence_path": self.evidence_path,
            "model_dependent_uncertainty": list(
                self.model_dependent_uncertainty
            ),
        }


class SetupReadinessReport(NamedTuple):
    """Local setup-readiness report distinct from semantic or privacy parity."""

    dimension: SetupReadinessDimension
    client_ready: bool
    checked_without_live_make: bool
    findings: tuple[SetupReadinessFinding, ...]
    model_dependent_uncertainty: tuple[str, ...]

    def as_dict(self) -> JsonObject:
        """Return a JSON-ready setup-readiness report payload."""
        return {
            "dimension": self.dimension,
            "client_ready": self.client_ready,
            "checked_without_live_make": self.checked_without_live_make,
            "findings": [finding.as_dict() for finding in self.findings],
            "model_dependent_uncertainty": list(
                self.model_dependent_uncertainty
            ),
        }


def check_setup_readiness(
    *,
    designer_diagnostics: Sequence[Mapping[str, object]] = (),
    validation_findings: Sequence[BlueprintValidationFinding] = (),
) -> SetupReadinessReport:
    """Return whether local evidence contains setup-required module failures."""
    findings = (
        *_designer_setup_findings(designer_diagnostics),
        *_validation_setup_findings(validation_findings),
    )
    return SetupReadinessReport(
        dimension="setup_readiness",
        client_ready=not findings,
        checked_without_live_make=True,
        findings=findings,
        model_dependent_uncertainty=_ordered_uncertainty(findings),
    )


def setup_readiness_completion_blockers(
    report: SetupReadinessReport,
) -> tuple[str, ...]:
    """Return Golden completion blocker codes for a setup-readiness report."""
    if report.client_ready:
        return ()
    return (SETUP_READINESS_BLOCKER,)


def _designer_setup_findings(
    diagnostics: Sequence[Mapping[str, object]],
) -> tuple[SetupReadinessFinding, ...]:
    findings: list[SetupReadinessFinding] = []
    for diagnostic in diagnostics:
        if not _is_setup_required_diagnostic(diagnostic):
            continue
        category = _setup_category(_text_field(diagnostic, ("category",)))
        message = _text_field(
            diagnostic, ("message", "client_message", "detail")
        )
        affected_module = _text_field(diagnostic, MODULE_FIELD_KEYS)
        evidence_path = _path_field(diagnostic, EVIDENCE_PATH_FIELD_KEYS)
        findings.append(
            SetupReadinessFinding(
                dimension="setup_readiness",
                source="designer_diagnostic",
                affected_module=affected_module,
                category=category,
                severity=cast("BlueprintFindingSeverity", "error"),
                message=message or "The module is not set up.",
                evidence_path=evidence_path,
                model_dependent_uncertainty=_diagnostic_uncertainty(
                    affected_module=affected_module,
                    evidence_path=evidence_path,
                    message=message,
                    inferred_from_message=False,
                ),
            )
        )
    return tuple(findings)


def _validation_setup_findings(
    findings: Sequence[BlueprintValidationFinding],
) -> tuple[SetupReadinessFinding, ...]:
    setup_findings: list[SetupReadinessFinding] = []
    for finding in findings:
        inferred_from_message = _message_indicates_setup_required(
            f"{finding.client_message} {finding.internal_message}"
        )
        if not _is_setup_required_validation_finding(
            finding=finding,
            inferred_from_message=inferred_from_message,
        ):
            continue
        affected_module = finding.catalog_module_id or finding.node_id
        evidence_path = _json_pointer(finding.source_path)
        setup_findings.append(
            SetupReadinessFinding(
                dimension="setup_readiness",
                source="validation_finding",
                affected_module=affected_module,
                category=_setup_category_from_validation_code(finding.code),
                severity=finding.severity,
                message=finding.client_message or finding.internal_message,
                evidence_path=evidence_path,
                model_dependent_uncertainty=_diagnostic_uncertainty(
                    affected_module=affected_module,
                    evidence_path=evidence_path,
                    message=finding.client_message or finding.internal_message,
                    inferred_from_message=inferred_from_message
                    and not _validation_code_has_setup_category(finding.code),
                ),
            )
        )
    return tuple(setup_findings)


def _is_setup_required_diagnostic(diagnostic: Mapping[str, object]) -> bool:
    severity = (_text_field(diagnostic, ("severity",)) or "").casefold()
    category = (_text_field(diagnostic, ("category",)) or "").casefold()
    code = (_text_field(diagnostic, ("code",)) or "").casefold()
    message = (
        _text_field(diagnostic, ("message", "client_message", "detail")) or ""
    )
    return severity == "error" and (
        bool(SETUP_REQUIRED_CATEGORIES & {category, code})
        or _message_indicates_setup_required(message)
    )


def _is_setup_required_validation_finding(
    *,
    finding: BlueprintValidationFinding,
    inferred_from_message: bool,
) -> bool:
    if finding.severity != "error":
        return False
    code = finding.code.casefold()
    return _validation_code_has_setup_category(code) or inferred_from_message


def _validation_code_has_setup_category(code: str) -> bool:
    normalized = code.casefold()
    return any(
        normalized == category or normalized.endswith(f".{category}")
        for category in SETUP_REQUIRED_CATEGORIES
    )


def _setup_category(value: str | None) -> str:
    if value is None:
        return SETUP_REQUIRED_CATEGORY
    normalized = value.casefold()
    return normalized if normalized in SETUP_REQUIRED_CATEGORIES else value


def _setup_category_from_validation_code(code: str) -> str:
    normalized = code.casefold()
    for category in sorted(SETUP_REQUIRED_CATEGORIES):
        if normalized == category or normalized.endswith(f".{category}"):
            return category
    return SETUP_REQUIRED_CATEGORY


def _message_indicates_setup_required(message: str) -> bool:
    normalized = message.casefold()
    return any(
        marker in normalized for marker in SETUP_REQUIRED_MESSAGE_MARKERS
    )


def _diagnostic_uncertainty(
    *,
    affected_module: str | None,
    evidence_path: str | None,
    message: str | None,
    inferred_from_message: bool,
) -> tuple[str, ...]:
    uncertainty: list[str] = []
    if affected_module is None:
        uncertainty.append(
            "setup-required evidence did not identify the affected module"
        )
    if evidence_path is None:
        uncertainty.append(
            "setup-required evidence did not identify a source path"
        )
    if message is None:
        uncertainty.append(
            "setup-required evidence did not include the original message"
        )
    if inferred_from_message:
        uncertainty.append("setup readiness was inferred from message text")
    return tuple(uncertainty)


def _ordered_uncertainty(
    findings: tuple[SetupReadinessFinding, ...],
) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for finding in findings:
        for uncertainty in finding.model_dependent_uncertainty:
            if uncertainty in seen:
                continue
            seen.add(uncertainty)
            ordered.append(uncertainty)
    return tuple(ordered)


def _text_field(
    mapping: Mapping[str, object], keys: tuple[str, ...]
) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _path_field(
    mapping: Mapping[str, object], keys: tuple[str, ...]
) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            pointer = _json_pointer(tuple(cast("list[object]", value)))
            if pointer is not None:
                return pointer
    return None


def _json_pointer(path: tuple[object, ...]) -> str | None:
    if not path:
        return None
    return "/" + "/".join(_escape_pointer_part(part) for part in path)


def _escape_pointer_part(value: object) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")
