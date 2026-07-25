# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001064#repo.make-knowledge.structural-ssot
# - 001064#repo.make-knowledge.temporal-facts
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Typed records for the Make knowledge store boundary.

Boundary contract:
- Owns: immutable records returned by Make knowledge store commands and queries.
- Must not: open SQLite connections, parse raw specs, or validate blueprints.
- Allows: small typed records shared by CLI, service, validator, and tests.
- Split when: command reports and query projections gain independent
  life cycles.
- Merge when: another module defines the same knowledge-store records.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

if TYPE_CHECKING:
    from catalog.models import CatalogRawSpecDiagnostic

KNOWLEDGE_SCHEMA_VERSION: Final = 13
DEFAULT_DB_SNAPSHOT_DIR: Final[Path] = Path("src/data/sql_snapshots")
DEFAULT_KNOWLEDGE_DB_PATH: Final[Path] = Path("src/data/pancakes.sqlite")
DEFAULT_GENERATED_FACTS_PATH: Final[Path] = Path(
    "src/data/sql_snapshots/make.sql"
)


class KnowledgeStoreBuildReport(NamedTuple):
    """Summary for one rebuilt Make knowledge SQLite database."""

    database_path: str
    snapshot_dir: str
    schema_version: int
    sql_snapshot_count: int
    raw_spec_manifest_path: str
    raw_spec_manifest_available: bool
    raw_spec_manifest_sha256: str | None
    raw_spec_record_count: int
    app_count: int
    app_version_count: int
    module_count: int
    field_count: int
    constraint_count: int
    alias_count: int
    rule_count: int
    optimizer_hint_count: int
    transaction_profile_count: int
    course_claim_count: int
    claim_evidence_count: int
    claim_conflict_count: int
    native_expectation_count: int
    native_gap_count: int
    raw_spec_diagnostics: tuple[CatalogRawSpecDiagnostic, ...]
    fingerprint: str


class KnowledgeStoreDumpReport(NamedTuple):
    """Summary for one deterministic SQL fact dump."""

    database_path: str
    output_path: str
    table_count: int
    row_count: int
    fingerprint: str


class NativeModuleGap(NamedTuple):
    """One Make-native/platform module coverage gap."""

    app_slug: str
    expected_module_count: int
    observed_module_count: int
    expected_kinds: tuple[str, ...]
    observed_kinds: tuple[str, ...]
    missing_kinds: tuple[str, ...]
    critical: bool


class KnowledgeStoreStatusReport(NamedTuple):
    """Read-side status for the generated Make knowledge database."""

    status: str
    database_path: str
    database_available: bool
    schema_version: int | None
    raw_spec_manifest_path: str
    missing_paths: tuple[str, ...]
    recommended_commands: tuple[str, ...]
    raw_spec_manifest_available: bool
    raw_spec_manifest_generated_at_utc: str | None
    raw_spec_manifest_sha256: str | None
    database_raw_spec_manifest_generated_at_utc: str | None
    database_raw_spec_manifest_sha256: str | None
    raw_spec_manifest_matches_database: bool | None
    raw_spec_record_count: int
    app_count: int
    app_version_count: int
    module_count: int
    alias_count: int
    rule_count: int
    optimizer_hint_count: int
    transaction_profile_count: int
    course_claim_count: int
    claim_evidence_count: int
    claim_conflict_count: int
    native_expectation_count: int
    native_module_gaps: tuple[NativeModuleGap, ...]
    fingerprint: str | None


class KnowledgeModuleAlias(NamedTuple):
    """One current module alias promoted from ADR or course evidence."""

    alias_text: str
    canonical_token: str
    canonical_module_id: str | None
    confidence: str
    adr_anchor: str


class KnowledgeRuleFact(NamedTuple):
    """One current deterministic validation or generation rule."""

    rule_id: str
    domain: str
    rule_code: str
    severity: str
    description: str
    adr_anchor: str


class KnowledgeOptimizerHint(NamedTuple):
    """One current optimization hint derived from promoted knowledge."""

    hint_id: str
    domain: str
    hint_code: str
    severity: str
    description: str
    adr_anchor: str


class KnowledgeTransactionProfile(NamedTuple):
    """One current transaction-safety profile for a Make module selector."""

    profile_id: str
    module_selector_kind: str
    module_selector: str
    operation_kind: str
    mutates_state: bool
    rollback_capability: str
    acid_compatibility: str
    safety_level: str
    description: str
    adr_anchor: str


class KnowledgeModuleFact(NamedTuple):
    """One current normalized Make module fact from the knowledge store."""

    module_id: str
    app_slug: str
    app_version: str
    module_kind: str
    internal_name: str
    display_name: str
    deprecated: bool
    fingerprint: str
    adr_anchor: str


class KnowledgeFieldFact(NamedTuple):
    """One current normalized Make field fact from the knowledge store."""

    field_id: str
    module_id: str
    direction: str
    path: tuple[str, ...]
    label: str
    required: bool
    field_type: str | None
    fingerprint: str
    adr_anchor: str


class KnowledgeConstraintFact(NamedTuple):
    """One current normalized Make field-constraint fact."""

    constraint_id: str
    field_id: str
    constraint_key: str
    value_json: str
    fingerprint: str
    adr_anchor: str


class KnowledgeNativeExpectation(NamedTuple):
    """One current Make-native/platform coverage expectation."""

    app_slug: str
    expected_module_count: int
    expected_kinds: tuple[str, ...]
    critical: bool
    fingerprint: str
    adr_anchor: str


class KnowledgeModuleSearchReport(NamedTuple):
    """Bounded current-module search result for large knowledge stores."""

    module_ids: tuple[str, ...]
    returned_count: int
    total_candidate_count: int
    effective_limit: int
    truncated: bool
    truncation_reason: str | None


class KnowledgeClaimConflict(NamedTuple):
    """One current arbitrated conflict between course or raw-spec evidence."""

    conflict_id: str
    claim_key: str
    domain: str
    winning_evidence_id: str
    losing_evidence_id: str
    winning_value_json: str
    losing_value_json: str
    winning_source_kind: str
    winning_source_ref: str
    losing_source_kind: str
    losing_source_ref: str
    winning_source_confidence: int
    losing_source_confidence: int
    winning_evidence_observed_at: str
    losing_evidence_observed_at: str
    resolution_status: str
    arbitration_reason: str
    fingerprint: str
    adr_anchor: str


class KnowledgeDesignerMessageEvidence(NamedTuple):
    """One current reviewed Make designer-message evidence row."""

    finding_id: str
    node_id: str | None
    module_slug: str | None
    severity: str
    message: str
    category: str | None
    field_path: str | None
    review_status: str
    source_kind: str
    source_ref: str
    fingerprint: str
    adr_anchor: str


class KnowledgeStoreQuery(NamedTuple):
    """Small current-facts projection consumed by validators and advisors."""

    fingerprint: str
    aliases: tuple[KnowledgeModuleAlias, ...]
    rule_facts: tuple[KnowledgeRuleFact, ...]
    optimizer_hints: tuple[KnowledgeOptimizerHint, ...]
    transaction_profiles: tuple[KnowledgeTransactionProfile, ...] = ()
    modules: tuple[KnowledgeModuleFact, ...] = ()
    fields: tuple[KnowledgeFieldFact, ...] = ()
    constraints: tuple[KnowledgeConstraintFact, ...] = ()
    native_expectations: tuple[KnowledgeNativeExpectation, ...] = ()
    claim_conflicts: tuple[KnowledgeClaimConflict, ...] = ()
    designer_messages: tuple[KnowledgeDesignerMessageEvidence, ...] = ()

    def canonical_token_for_alias(self, alias_text: str) -> str | None:
        """Return the canonical token for one promoted alias if it exists."""
        normalized_alias = alias_text.casefold().strip()
        for alias in self.aliases:
            if alias.alias_text.casefold() == normalized_alias:
                return alias.canonical_token
        return None

    def module_by_id(self, module_id: str) -> KnowledgeModuleFact | None:
        """Return one normalized module fact by stable module ID."""
        for module in self.modules:
            if module.module_id == module_id:
                return module
        return None

    def fields_for_module(
        self,
        module_id: str,
        *,
        direction: str | None = None,
    ) -> tuple[KnowledgeFieldFact, ...]:
        """Return current fields for one normalized module."""
        return tuple(
            field
            for field in self.fields
            if field.module_id == module_id
            and (direction is None or field.direction == direction)
        )

    def constraints_for_field(
        self, field_id: str
    ) -> tuple[KnowledgeConstraintFact, ...]:
        """Return current constraints for one normalized field."""
        return tuple(
            constraint
            for constraint in self.constraints
            if constraint.field_id == field_id
        )

    def rule_by_code(self, rule_code: str) -> KnowledgeRuleFact | None:
        """Return one promoted validation rule by rule code."""
        for rule in self.rule_facts:
            if rule.rule_code == rule_code:
                return rule
        return None

    def optimizer_hint_by_code(
        self, hint_code: str
    ) -> KnowledgeOptimizerHint | None:
        """Return one promoted optimizer hint by hint code."""
        for hint in self.optimizer_hints:
            if hint.hint_code == hint_code:
                return hint
        return None

    def transaction_profiles_matching(
        self,
        *,
        module_token_key: str,
        module_id: str | None = None,
        app_slug: str | None = None,
        module_kind: str | None = None,
    ) -> tuple[KnowledgeTransactionProfile, ...]:
        """Return transaction profiles matching one module identity."""
        normalized_token_key = module_token_key.casefold().strip()
        return tuple(
            profile
            for profile in self.transaction_profiles
            if _transaction_profile_matches(
                profile=profile,
                module_token_key=normalized_token_key,
                module_id=module_id,
                app_slug=app_slug,
                module_kind=module_kind,
            )
        )

    def native_expectation_for_slug(
        self,
        app_slug: str,
    ) -> KnowledgeNativeExpectation | None:
        """Return one native/platform expectation by Make app slug."""
        for expectation in self.native_expectations:
            if expectation.app_slug == app_slug:
                return expectation
        return None

    def claim_conflicts_for_key(
        self, claim_key: str
    ) -> tuple[KnowledgeClaimConflict, ...]:
        """Return current evidence conflicts for one normalized claim key."""
        return tuple(
            conflict
            for conflict in self.claim_conflicts
            if conflict.claim_key == claim_key
        )

    def winning_claim_value_for_key(self, claim_key: str) -> str | None:
        """Return the winning JSON value for one claim key."""
        for conflict in self.claim_conflicts:
            if (
                conflict.claim_key == claim_key
                and conflict.resolution_status == "resolved"
            ):
                return conflict.winning_value_json
        return None

    def reviewed_designer_messages_for_node(
        self,
        node_id: str,
        module_slug: str | None = None,
    ) -> tuple[KnowledgeDesignerMessageEvidence, ...]:
        """Return reviewed Make designer-message evidence for one draft node."""
        normalized_module_slug = _normalized_optional_token(module_slug)
        return tuple(
            evidence
            for evidence in self.designer_messages
            if evidence.review_status == "reviewed"
            and evidence.source_kind == "designer_message"
            and evidence.severity == "warning"
            and evidence.node_id == node_id
            and _designer_message_module_matches(
                evidence.module_slug,
                normalized_module_slug,
            )
        )

    def reviewed_root_designer_messages(
        self,
    ) -> tuple[KnowledgeDesignerMessageEvidence, ...]:
        """Return reviewed scenario-level Make designer-message evidence."""
        return tuple(
            evidence
            for evidence in self.designer_messages
            if evidence.review_status == "reviewed"
            and evidence.source_kind == "designer_message"
            and evidence.severity == "warning"
            and evidence.node_id is None
            and evidence.module_slug is None
        )


def _normalized_optional_token(value: str | None) -> str | None:
    normalized = value.casefold().strip() if value is not None else ""
    return normalized or None


def _designer_message_module_matches(
    evidence_module_slug: str | None,
    normalized_module_slug: str | None,
) -> bool:
    normalized_evidence_module_slug = _normalized_optional_token(
        evidence_module_slug
    )
    if normalized_evidence_module_slug is None:
        return True
    if normalized_module_slug is None:
        return False
    return normalized_evidence_module_slug == normalized_module_slug


def _transaction_profile_matches(
    *,
    profile: KnowledgeTransactionProfile,
    module_token_key: str,
    module_id: str | None,
    app_slug: str | None,
    module_kind: str | None,
) -> bool:
    """Return whether one profile selector matches module identity."""
    selector = profile.module_selector.casefold().strip()
    if profile.module_selector_kind == "module_token_contains":
        return selector in module_token_key
    if profile.module_selector_kind == "module_id":
        return module_id == profile.module_selector
    if profile.module_selector_kind == "app_slug":
        return app_slug == profile.module_selector
    if profile.module_selector_kind == "module_kind":
        return module_kind == profile.module_selector
    return False
