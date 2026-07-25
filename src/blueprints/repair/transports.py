# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001041#repo.make-scraper.raw-specs.live-scraping-disabled-by-default
# - 001049#repo.blueprint-repair.offline-action-contract
# - 001066#repo.make-linter.offline-validator-remains-default
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Offline Make import probe transports for repair tests.

Boundary contract:
- Owns: deterministic fixture-backed import probe response normalization.
- Must not: construct API URLs, read credentials, call networks, or mutate
blueprints.
- Allows: local JSON fixtures and repair diagnostic projection.
- Split when: operator-authorized live probes become a separate adapter.
- Merge when: another repair module owns the same fixture probe contract.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Literal, NamedTuple, Protocol, cast

from blueprints.repair.diagnostics import (
    RepairDiagnosticsReport,
    propose_repair_candidates,
)
from blueprints.validation.findings import build_validation_finding
from blueprints.validation.models import BlueprintValidationReport

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from blueprints.ast.models import AstPathPart, JsonObject
    from blueprints.validation.models import BlueprintValidationFinding

type ImportProbeStatus = Literal["accepted", "rejected"]


class MakeImportProbe(Protocol):
    """Protocol for deterministic Make import probe boundaries."""

    def probe_import(self, blueprint: JsonObject) -> ImportProbeReport:
        """Return a normalized import probe result for one blueprint payload."""
        ...


class ImportProbeReport(NamedTuple):
    """Normalized fixture-backed import probe result."""

    status: ImportProbeStatus
    findings: tuple[BlueprintValidationFinding, ...]
    diagnostics: RepairDiagnosticsReport

    @property
    def accepted(self) -> bool:
        """Return whether the simulated import was accepted."""
        return self.status == "accepted"


class FixtureImportProbe(NamedTuple):
    """Fake Make import probe backed by a local JSON fixture."""

    response: JsonObject

    @classmethod
    def from_path(cls, path: Path) -> FixtureImportProbe:
        """Load a fake import probe from a local fixture path.

        Returns:
            The fixture-backed probe.

        Raises:
            TypeError: If the fixture does not contain a JSON object.
        """

        def reject_non_standard_constant(raw_value: str) -> object:
            message = (
                f"Import probe fixture uses non-standard JSON constant"
                f"{raw_value}: {path}"
            )
            raise ValueError(message)

        parsed = cast(
            "object",
            json.loads(
                path.read_text(encoding="utf-8"),
                parse_constant=reject_non_standard_constant,
            ),
        )
        if not isinstance(parsed, dict):
            message = f"Import probe fixture must be an object: {path}"
            raise TypeError(message)
        return cls(
            response=_json_object_from_mapping(
                cast("Mapping[object, object]", parsed)
            )
        )

    def probe_import(self, blueprint: JsonObject) -> ImportProbeReport:
        """Return the fixture response without reading credentials or network.

        state.

        Returns:
            The normalized fixture-backed result.
        """
        _ = blueprint
        findings = _findings_from_response(self.response)
        status = _status_from_response(self.response, findings=findings)
        report = BlueprintValidationReport(
            catalog_fingerprint="fixture:make-import-probe",
            findings=findings,
        )
        return ImportProbeReport(
            status=status,
            findings=findings,
            diagnostics=propose_repair_candidates(report),
        )


def _status_from_response(
    response: JsonObject,
    *,
    findings: tuple[BlueprintValidationFinding, ...],
) -> ImportProbeStatus:
    status = response.get("status")
    if status == "accepted" and not findings:
        return "accepted"
    if status == "rejected":
        return "rejected"
    message = f"Unsupported import probe fixture status: {status!r}"
    raise ValueError(message)


def _findings_from_response(
    response: JsonObject,
) -> tuple[BlueprintValidationFinding, ...]:
    raw_findings = response.get("findings")
    if raw_findings is None:
        return ()
    if not isinstance(raw_findings, list):
        message = "Import probe fixture findings must be a list."
        raise TypeError(message)
    findings: list[BlueprintValidationFinding] = []
    for item in cast("list[object]", raw_findings):
        if not isinstance(item, dict):
            message = "Import probe fixture finding must be an object."
            raise TypeError(message)
        findings.append(
            _finding_from_payload(
                _json_object_from_mapping(cast("Mapping[object, object]", item))
            )
        )
    return tuple(findings)


def _finding_from_payload(payload: JsonObject) -> BlueprintValidationFinding:
    code = _finding_code(payload)
    severity = _required_severity(payload)
    return build_validation_finding(
        code=code,
        severity=severity,
        node=(
            _optional_text(payload.get("node_id")),
            _path(payload.get("path")),
        ),
        catalog_module_id=None,
        messages=(
            _required_text(payload, "client_message"),
            _required_text(payload, "internal_message"),
        ),
    )


def _finding_code(payload: JsonObject) -> str:
    direct_code = _optional_text(payload.get("code"))
    if direct_code is not None:
        return direct_code
    return _required_text(payload, "code_prefix") + _required_text(
        payload, "code_suffix"
    )


def _required_severity(
    payload: JsonObject,
) -> Literal["error", "warning", "optimization"]:
    value = _required_text(payload, "severity")
    if value in {"error", "warning", "optimization"}:
        return cast("Literal['error', 'warning', 'optimization']", value)
    message = f"Unsupported import probe severity: {value}"
    raise ValueError(message)


def _path(value: object) -> tuple[AstPathPart, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        message = "Import probe fixture path must be a list."
        raise TypeError(message)
    path: list[AstPathPart] = []
    for item in cast("list[object]", value):
        if isinstance(item, str | int) and not isinstance(item, bool):
            path.append(item)
            continue
        message = f"Import probe fixture path item is invalid: {item!r}"
        raise TypeError(message)
    return tuple(path)


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    text = _optional_text(value)
    if text is None:
        message = f"Import probe fixture field {key!r} must be non-empty text."
        raise ValueError(message)
    return text


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        message = "Import probe fixture value must be text."
        raise TypeError(message)
    text = value.strip()
    return text or None


def _json_object_from_mapping(value: Mapping[object, object]) -> JsonObject:
    if not all(isinstance(key, str) for key in value):
        message = "Import probe fixture object keys must be strings."
        raise TypeError(message)
    return cast("JsonObject", dict(value))
