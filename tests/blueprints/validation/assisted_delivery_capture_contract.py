# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Tests for assisted-delivery capture validation.

Boundary contract:
- Owns: tests for assisted-delivery capture template validation.
- Must not: test PDF rendering, GitGuard, or generic repository scope cleanup.
- Allows: active data template reads and validation error assertions.
- Split when: capture schema and policy-risk checks need separate modules.
- Merge when: another assisted-delivery capture test duplicates this coverage.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import TYPE_CHECKING, cast

from blueprints.validation import validate_assisted_delivery_capture

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from tests.support.json_payloads import JsonObject


REPO_ROOT = repo_root()
CAPTURE_TEMPLATE = (
    REPO_ROOT
    / "src"
    / "blueprints"
    / "validation"
    / "data"
    / "assisted-delivery"
    / "templates"
    / "assisted_delivery_capture_template.json"
)


def load_template() -> JsonObject:
    """Load the active assisted-delivery capture template.

    Returns:
        The loaded value.
    """
    payload = cast(
        "object", json.loads(CAPTURE_TEMPLATE.read_text(encoding="utf-8"))
    )
    assert isinstance(payload, dict), "Capture template must be a JSON object."
    return cast("JsonObject", payload)


def test_assisted_delivery_capture_template_is_valid() -> None:
    """The repository data template follows the active validation contract."""
    result = validate_assisted_delivery_capture(load_template())
    assert result.valid, f"Capture template should be valid: {result.errors}"


def test_assisted_delivery_capture_rejects_obsolete_scope_and_local_paths() -> (
    None
):
    """Manual capture packets must not revive old scope or hardcoded paths."""
    payload = load_template()
    planning = cast("JsonObject", payload["planning"])
    planning["selection_rationale"] = [
        f"{'Ax' + 'iom'} GraphRAG file at C:\\Users\\example\\repo"
    ]

    result = validate_assisted_delivery_capture(payload)

    assert not (result.valid), (
        "Obsolete scope and hardcoded paths must fail validation."
    )
    assert any("obsolete scope" in error for error in result.errors), (
        f"Expected obsolete-scope error: {result.errors}"
    )
    assert any("hardcoded local path" in error for error in result.errors), (
        f"Expected hardcoded-path error: {result.errors}"
    )


def test_assisted_delivery_capture_records_blocked_runs_honestly() -> None:
    """Blocked manual captures need an explicit blocker value."""
    payload = deepcopy(load_template())
    session = cast("JsonObject", payload["session"])
    session["blocked"] = True
    session["blocker"] = "Manual canary was not run."
    decision = cast("JsonObject", payload["decision"])
    decision["status"] = "blocked"

    result = validate_assisted_delivery_capture(payload)

    assert result.valid, (
        f"Blocked capture with blocker should be valid: {result.errors}"
    )
    assert result.blockers == ("Manual canary was not run.",), (
        f"Blocked capture should preserve blocker text: {result.blockers}"
    )


def test_assisted_delivery_capture_rejects_structured_verdict_tokens() -> None:
    """Accepted verdicts must not be synthesized by coercing JSON containers."""
    payload = deepcopy(load_template())
    decision = cast("JsonObject", payload["decision"])
    decision["accepted_verdicts"] = [{"status": "blocked"}]
    decision["status"] = "{'status': 'blocked'}"

    result = validate_assisted_delivery_capture(payload)

    assert not (result.valid), (
        "Structured accepted verdict tokens must fail validation."
    )
    assert any("accepted_verdicts" in error for error in result.errors), (
        f"Expected accepted-verdicts error: {result.errors}"
    )


def test_assisted_delivery_capture_rejects_empty_accepted_verdicts() -> None:
    """Accepted verdicts must preserve the canonical decision boundary."""
    payload = deepcopy(load_template())
    decision = cast("JsonObject", payload["decision"])
    decision["accepted_verdicts"] = []

    result = validate_assisted_delivery_capture(payload)

    assert not (result.valid), "Empty accepted verdicts must fail validation."
    assert any("accepted_verdicts" in error for error in result.errors), (
        f"Expected accepted-verdicts error: {result.errors}"
    )
