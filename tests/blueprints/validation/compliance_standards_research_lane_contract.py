# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contract tests for standards-derived linter research intake.

Boundary contract:
- Owns: standards-source metadata, rights posture, and advisory candidate
intake.
- Must not: implement standards-derived validator behavior, copy standard text,
or
  assert compliance, certification, audit completion, or legal sufficiency.
- Allows: local JSON ledgers that prove standards ideas stay advisory until a
  deterministic promoted-rule task owns implementation.
- Split when: standards research gains a dedicated source registry or citations
API.
- Merge when: linter candidate-intake tests own the same source-rights gate.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from blueprints.validation import (
    MakeLinterCandidateReviewRecord,
    make_linter_review_record_errors,
    make_linter_supported_codes,
)

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from pathlib import Path

    from blueprints.validation.linter_rule_intake import (
        MakeLinterCandidateDecision,
        MakeLinterEvidenceSurface,
        MakeLinterProfileGate,
        MakeLinterSeverityPosture,
    )

COMPLIANCE_DATA_ROOT = (
    repo_root()
    / "src"
    / "blueprints"
    / "validation"
    / "data"
    / "linter"
    / "compliance"
)
STANDARDS_SOURCE_LEDGER_PATH = (
    COMPLIANCE_DATA_ROOT / "standards-source-ledger.json"
)
STANDARDS_CANDIDATE_INTAKE_PATH = (
    COMPLIANCE_DATA_ROOT / "standards-candidate-intake.json"
)
EXPECTED_STANDARD_IDS = (
    "pci-dss",
    "iso-iec-27001",
    "iso-iec-27002",
    "gdpr-pii",
    "soc-2",
    "nist-csf",
    "owasp-asvs",
    "owasp-api-security-top-10",
)
EXPECTED_BIBLIOGRAPHY_NOTICES = frozenset(
    (
        "docs/bibliography/aicpa-cima-soc.md",
        "docs/bibliography/european-union-gdpr.md",
        "docs/bibliography/iso-iec-27000-series.md",
        "docs/bibliography/nist-cybersecurity-framework.md",
        "docs/bibliography/owasp-application-security.md",
        "docs/bibliography/pci-security-standards-council.md",
    )
)
FORBIDDEN_CLIENT_CLAIM_WORDS = (
    "certification",
    "audit completion",
    "compliance determination",
    "attestation readiness",
    "legal sufficiency",
    "legal advice",
)
ALLOWED_RIGHTS_POSTURES = frozenset(
    (
        "official-open-project-cc-by-sa-4.0",
        "official-public-document-library",
        "official-public-government-publication",
        "official-regulator-legal-text",
        "official-resource-page-with-professional-guidance",
        "official-standard-page-licensed-standard",
    )
)


def test_standards_source_ledger_is_advisory_source_rights_metadata() -> None:
    """The standards lane records source posture without activating linter.

    output.
    """
    ledger = _json_mapping(STANDARDS_SOURCE_LEDGER_PATH)

    assert ledger["schema_version"] == 1, f"Unexpected ledger schema: {ledger}"
    assert ledger["reviewed_at"] == "2026-05-13", (
        f"Review date drifted: {ledger}"
    )
    assert ledger["active_rule_behavior"] is False, (
        f"Standards research must not activate rules by itself: {ledger}"
    )
    assert "legal advice" in str(ledger["non_advice_notice"]).casefold(), (
        f"Ledger must say it is not legal advice: {ledger}"
    )

    standards = _standards_by_id(ledger)
    assert tuple(standards) == EXPECTED_STANDARD_IDS, (
        f"Standards source coverage drifted: {tuple(standards)}"
    )
    bibliography_notices: set[str] = set()
    for standard_id, standard in standards.items():
        assert standard["rights_posture"] in ALLOWED_RIGHTS_POSTURES, (
            f"Unknown rights posture for {standard_id}: {standard}"
        )
        assert str(standard["official_source_url"]).startswith("https://"), (
            f"Official source URL must be an HTTPS citation: {standard}"
        )
        assert str(standard["official_terms_url"]).startswith("https://"), (
            f"Official terms URL must be an HTTPS citation: {standard}"
        )
        assert str(standard["official_rights_url"]).startswith("https://"), (
            f"Official rights URL must be an HTTPS citation: {standard}"
        )
        assert (
            standard["copying_policy"] == "metadata-and-original-analysis-only"
        ), f"Standards text cannot be copied into Pancakes: {standard}"
        assert standard["profile_gate_required"] is True, (
            f"Standards-derived runtime behavior requires profile gates: "
            f"{standard}"
        )
        assert standard["runtime_activation_allowed"] is False, (
            f"Source metadata cannot activate runtime behavior: {standard}"
        )
        bibliography_notice = str(standard["bibliography_notice"])
        bibliography_notices.add(bibliography_notice)
        bibliography_path = repo_root() / bibliography_notice
        assert bibliography_path.exists(), (
            f"Missing bibliography notice: {bibliography_path}"
        )
        assert (
            "claim" in str(standard["engineering_use_boundary"]).casefold()
        ), f"Engineering boundary must forbid output claims: {standard}"
        assert (
            "local" in str(standard["local_predicate_boundary"]).casefold()
        ), f"Standards-derived predicates must be local: {standard}"

    assert bibliography_notices == EXPECTED_BIBLIOGRAPHY_NOTICES, (
        f"Bibliography notice coverage drifted: {bibliography_notices}"
    )

    forbidden_claims = tuple(
        cast("list[str]", ledger["forbidden_client_claims"])
    )
    assert set(FORBIDDEN_CLIENT_CLAIM_WORDS).issubset(forbidden_claims), (
        f"Forbidden client claim vocabulary drifted: {forbidden_claims}"
    )


def test_standards_candidate_intake_records_one_6eb34277() -> None:
    """At least one standards-derived candidate passes intake without new.

    behavior.
    """
    payload = _json_mapping(STANDARDS_CANDIDATE_INTAKE_PATH)

    assert payload["active_rule_behavior"] is False, (
        f"Candidate intake must not activate runtime behavior: {payload}"
    )

    records = cast("list[dict[str, object]]", payload["records"])
    assert len(records) == 1, (
        f"Expected one reviewed standards candidate: {records}"
    )

    supported_codes = set(make_linter_supported_codes())
    review_record = _review_record(records[0])
    errors = make_linter_review_record_errors(review_record)

    assert not (errors), f"Standards candidate failed manual intake: {errors}"
    assert review_record.candidate_id == "STD-OWASP-API-001", (
        f"Unexpected standards candidate ID: {review_record}"
    )
    assert review_record.canonical_rule_code in supported_codes, (
        f"Candidate mapped to unsupported rule code: {review_record}"
    )
    assert (
        records[0]["activation_state"]
        == "research_complete_no_new_runtime_behavior"
    ), f"Standards candidate cannot auto-promote runtime behavior: {records[0]}"


def test_standards_research_lane_avoids_customer_safe_claim_language() -> None:
    """Standards research metadata must not contain customer-facing assurance.

    claims.
    """
    payload_text = (
        STANDARDS_SOURCE_LEDGER_PATH.read_text(encoding="utf-8")
        + "\n"
        + STANDARDS_CANDIDATE_INTAKE_PATH.read_text(encoding="utf-8")
    ).casefold()

    for forbidden_phrase in (
        "certifies compliance",
        "certified compliant",
        "audit complete",
        "attestation ready",
        "legally sufficient",
    ):
        assert forbidden_phrase not in payload_text, (
            f"Standards lane leaked a customer assurance claim: "
            f"{forbidden_phrase}"
        )


def _json_mapping(path: Path) -> dict[str, object]:
    payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(payload, dict), (
        f"Expected JSON object at {path}: {payload!r}"
    )
    return cast("dict[str, object]", payload)


def _standards_by_id(
    ledger: dict[str, object],
) -> dict[str, dict[str, object]]:
    standards = cast("list[dict[str, object]]", ledger["standards"])
    return {str(standard["standard_id"]): standard for standard in standards}


def _review_record(
    record: dict[str, object],
) -> MakeLinterCandidateReviewRecord:
    return MakeLinterCandidateReviewRecord(
        candidate_id=str(record["candidate_id"]),
        source_file=str(record["source_file"]),
        original_heading=str(record["original_heading"]),
        decision=cast("MakeLinterCandidateDecision", record["decision"]),
        canonical_rule_code=cast("str | None", record["canonical_rule_code"]),
        alias_of_candidate_id=cast(
            "str | None", record["alias_of_candidate_id"]
        ),
        evidence_surfaces=tuple(
            cast("list[MakeLinterEvidenceSurface]", record["evidence_surfaces"])
        ),
        deterministic_predicate=str(record["deterministic_predicate"]),
        severity_posture=cast(
            "MakeLinterSeverityPosture", record["severity_posture"]
        ),
        profile_gates=tuple(
            cast("list[MakeLinterProfileGate]", record["profile_gates"])
        ),
        implementation_owner=str(record["implementation_owner"]),
        failing_fixture_plan=str(record["failing_fixture_plan"]),
        passing_fixture_plan=str(record["passing_fixture_plan"]),
        adr_impact=str(record["adr_impact"]),
        bibliography_impact=str(record["bibliography_impact"]),
        false_positive_risk=str(record["false_positive_risk"]),
        quarantine_reason=cast("str | None", record["quarantine_reason"]),
        rejection_reason=cast("str | None", record["rejection_reason"]),
        rationale=str(record["rationale"]),
    )
