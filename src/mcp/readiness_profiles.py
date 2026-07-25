# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001067#repo.mcp.client-routing.native-gpt-latency-and-output
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Shared MCP readiness profile semantics.

Boundary contract:
- Owns: normalized profile names and profile-level readiness semantics.
- Must not: inspect projects, validate blueprints, render artifacts, or call
providers.
- Allows: transport-agnostic payload projection for MCP responses.
- Split when: profile rules need adapter-specific policy outside MCP.
- Merge when: another MCP module owns the same profile vocabulary.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, NamedTuple

from mcp.response_contracts import blocked_surface_payload

if TYPE_CHECKING:
    from mcp.models import JsonObject

type ReadinessProfileName = Literal[
    "import_test", "parity_fixture", "client_handoff"
]
type NoteFindingsSurface = Literal["import", "handoff", "advisory"]
type ZeroTracePolicy = Literal["rendered_only", "blocked_not_evaluated"]
type CompactRawPolicy = Literal["grouped_only"]
type BlockedSurfacePolicy = Literal["explicit"]

READINESS_PROFILE_IMPORT_TEST: ReadinessProfileName = "import_test"
READINESS_PROFILE_PARITY_FIXTURE: ReadinessProfileName = "parity_fixture"
READINESS_PROFILE_CLIENT_HANDOFF: ReadinessProfileName = "client_handoff"
DEFAULT_READINESS_PROFILE: ReadinessProfileName = READINESS_PROFILE_IMPORT_TEST
READINESS_PROFILE_NAMES = frozenset(
    (
        READINESS_PROFILE_IMPORT_TEST,
        READINESS_PROFILE_PARITY_FIXTURE,
        READINESS_PROFILE_CLIENT_HANDOFF,
    )
)


class ProfileSemantics(NamedTuple):
    """Shared readiness semantics for import, parity fixture, and handoff.

    surfaces.
    """

    name: ReadinessProfileName
    note_findings_surface: NoteFindingsSurface
    blocks_import_on_notes: bool
    blocks_artifact_generation_on_notes: bool
    evaluates_zero_trace_before_render: bool
    exposes_handoff_summary: bool
    exposes_parity_summary: bool
    zero_trace_policy: ZeroTracePolicy
    compact_raw_policy: CompactRawPolicy
    blocked_surface_policy: BlockedSurfacePolicy
    status_wording: str


PROFILE_SEMANTICS: dict[ReadinessProfileName, ProfileSemantics] = {
    READINESS_PROFILE_IMPORT_TEST: ProfileSemantics(
        name=READINESS_PROFILE_IMPORT_TEST,
        note_findings_surface="handoff",
        blocks_import_on_notes=False,
        blocks_artifact_generation_on_notes=False,
        evaluates_zero_trace_before_render=False,
        exposes_handoff_summary=True,
        exposes_parity_summary=False,
        zero_trace_policy="rendered_only",
        compact_raw_policy="grouped_only",
        blocked_surface_policy="explicit",
        status_wording=(
            "Make import readiness is evaluated independently from client "
            "handoff readiness."
        ),
    ),
    READINESS_PROFILE_PARITY_FIXTURE: ProfileSemantics(
        name=READINESS_PROFILE_PARITY_FIXTURE,
        note_findings_surface="advisory",
        blocks_import_on_notes=False,
        blocks_artifact_generation_on_notes=False,
        evaluates_zero_trace_before_render=False,
        exposes_handoff_summary=True,
        exposes_parity_summary=True,
        zero_trace_policy="rendered_only",
        compact_raw_policy="grouped_only",
        blocked_surface_policy="explicit",
        status_wording=(
            "Parity fixture readiness keeps handoff findings advisory unless "
            "import is blocked."
        ),
    ),
    READINESS_PROFILE_CLIENT_HANDOFF: ProfileSemantics(
        name=READINESS_PROFILE_CLIENT_HANDOFF,
        note_findings_surface="handoff",
        blocks_import_on_notes=False,
        blocks_artifact_generation_on_notes=True,
        evaluates_zero_trace_before_render=False,
        exposes_handoff_summary=True,
        exposes_parity_summary=False,
        zero_trace_policy="blocked_not_evaluated",
        compact_raw_policy="grouped_only",
        blocked_surface_policy="explicit",
        status_wording=(
            "Client handoff readiness may block handoff artifact generation "
            "while import remains "
            "available."
        ),
    ),
}


def normalize_profile_name(
    *,
    profile_value: object,
    strict_handoff_notes: bool,
    field_name: str,
) -> ReadinessProfileName:
    """Return the normalized MCP readiness profile name.

    Raises:
        TypeError: When the profile value is not a string.
        ValueError: When the profile value is not supported.
    """
    if strict_handoff_notes:
        return READINESS_PROFILE_CLIENT_HANDOFF
    if profile_value is None:
        return DEFAULT_READINESS_PROFILE
    if not isinstance(profile_value, str):
        message = (
            f"{field_name} must be one of: import_test, parity_fixture,"
            f"client_handoff."
        )
        raise TypeError(message)
    normalized = profile_value.strip().casefold().replace("-", "_")
    if normalized not in READINESS_PROFILE_NAMES:
        message = (
            f"{field_name} must be one of: import_test, parity_fixture,"
            f"client_handoff."
        )
        raise ValueError(message)
    return normalized


def profile_semantics(
    profile_name: ReadinessProfileName | str,
) -> ProfileSemantics:
    """Return the computed result for the caller."""
    normalized = normalize_profile_name(
        profile_value=profile_name,
        strict_handoff_notes=False,
        field_name="readiness_profile",
    )
    return PROFILE_SEMANTICS[normalized]


def profile_semantics_payload(semantics: ProfileSemantics) -> JsonObject:
    """Return the computed result for the caller."""
    return {
        "name": semantics.name,
        "note_findings_surface": semantics.note_findings_surface,
        "blocks_import_on_notes": semantics.blocks_import_on_notes,
        "blocks_artifact_generation_on_notes": (
            semantics.blocks_artifact_generation_on_notes
        ),
        "evaluates_zero_trace_before_render": (
            semantics.evaluates_zero_trace_before_render
        ),
        "exposes_handoff_summary": semantics.exposes_handoff_summary,
        "exposes_parity_summary": semantics.exposes_parity_summary,
        "zero_trace_policy": semantics.zero_trace_policy,
        "compact_raw_policy": semantics.compact_raw_policy,
        "blocked_surface_policy": semantics.blocked_surface_policy,
        "status_wording": semantics.status_wording,
    }


def profile_surface_status_payload(
    *,
    semantics: ProfileSemantics,
    import_status: str,
    client_handoff_status: str,
    zero_trace_status: str | None = None,
    scenario_tests_status: str | None = None,
) -> JsonObject:
    """Return explicit blocked and unblocked readiness surfaces for one profile.

    response.
    """
    blocked_surfaces = _blocked_surfaces(
        import_status=import_status,
        client_handoff_status=client_handoff_status,
        zero_trace_status=zero_trace_status,
    )
    unblocked_surfaces = _unblocked_surfaces(
        import_status=import_status,
        client_handoff_status=client_handoff_status,
        zero_trace_status=zero_trace_status,
        scenario_tests_status=scenario_tests_status,
    )
    return blocked_surface_payload(
        blocked_surfaces=blocked_surfaces,
        unblocked_surfaces=unblocked_surfaces,
        status_reason=_status_reason(
            semantics=semantics,
            import_status=import_status,
            client_handoff_status=client_handoff_status,
            zero_trace_status=zero_trace_status,
        ),
    )


def _blocked_surfaces(
    *,
    import_status: str,
    client_handoff_status: str,
    zero_trace_status: str | None,
) -> list[str]:
    blocked: list[str] = []
    if import_status == "blocked":
        blocked.append("make_import")
    if client_handoff_status == "blocked":
        blocked.append("client_handoff")
    if zero_trace_status == "failed":
        blocked.append("zero_trace")
    return blocked


def _unblocked_surfaces(
    *,
    import_status: str,
    client_handoff_status: str,
    zero_trace_status: str | None,
    scenario_tests_status: str | None,
) -> list[str]:
    unblocked: list[str] = []
    if import_status == "ready":
        unblocked.append("make_import")
    if client_handoff_status == "ready":
        unblocked.append("client_handoff")
    if zero_trace_status == "passed":
        unblocked.append("zero_trace")
    if scenario_tests_status == "passed":
        unblocked.append("scenario_tests")
    return unblocked


def _status_reason(
    *,
    semantics: ProfileSemantics,
    import_status: str,
    client_handoff_status: str,
    zero_trace_status: str | None,
) -> str:
    if import_status == "ready" and client_handoff_status == "blocked":
        return (
            "Client handoff notes are incomplete; import-safe artifact "
            "generation remains "
            "available."
        )
    if zero_trace_status == "failed":
        return "Rendered artifact failed the zero-trace gate."
    if import_status == "ready" and client_handoff_status == "not_ready":
        return (
            "Make import readiness is available; client handoff readiness "
            "still "
            "requires setup, "
            "tests, or notes."
        )
    if import_status == "blocked":
        return (
            "Make import is blocked by import-surface validation or artifact "
            "generation."
        )
    if semantics.name == "client_handoff" and client_handoff_status == "ready":
        return (
            "Client handoff readiness is available for the evaluated local "
            "artifact."
        )
    return semantics.status_wording
