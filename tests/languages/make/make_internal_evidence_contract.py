# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contracts for private Make-native evidence ledgers."""

from __future__ import annotations

import json

import pytest
from languages.make.evidence import (
    make_evidence_entry,
    make_internal_evidence_availability,
    make_internal_evidence_ledger,
)


def test_internal_evidence_summary_does_not_expose_private_recipe() -> None:
    """Public availability summary keeps the detailed rule ledger internal."""
    ledger = make_internal_evidence_ledger(
        (
            make_evidence_entry(
                evidence_type="module_projector_manifest",
                judgment="make_native_module_projection",
                source_id="slack:CreateMessage",
                rule_id="make.projector.slack.create_message",
                module="slack:CreateMessage",
                confidence="low",
                detail={
                    "fixture_count": 1,
                    "projector_kind": "slack_create_message",
                },
            ),
        )
    )

    summary = make_internal_evidence_availability(ledger)

    encoded_summary = json.dumps(summary, sort_keys=True)
    assert summary == {
        "schema_version": 1,
        "visibility": "internal_available",
        "available": True,
        "entry_count": 1,
        "contains_internal_details": False,
        "request_internal_details": (
            "Set include_internal_evidence=true for private debug output."
        ),
    }
    assert "entries" not in summary, (
        f"Summary leaked private ledger rows: {summary}"
    )
    assert "make.projector.slack.create_message" not in encoded_summary, (
        f"Summary leaked private rule ids: {summary}"
    )
    assert "slack_create_message" not in encoded_summary, (
        f"Summary leaked projector details: {summary}"
    )


def test_internal_evidence_rejects_secret_like_values() -> None:
    """Evidence rows must never become a secret storage surface."""
    with pytest.raises(ValueError, match="resembles secret-bearing material"):
        _ = make_evidence_entry(
            evidence_type="risk_model_rule",
            judgment="unsafe_fixture",
            source_id="fixture",
            detail={"authorization_header": "Bearer abc123"},
        )
