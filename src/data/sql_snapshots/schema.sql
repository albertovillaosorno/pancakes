PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS snapshot_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingest_runs (
  run_id TEXT PRIMARY KEY,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  generated_at_utc TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  record_count INTEGER NOT NULL,
  created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS source_documents (
  document_id TEXT NOT NULL,
  domain TEXT NOT NULL,
  source_path TEXT NOT NULL,
  media_type TEXT NOT NULL,
  source_text TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  fingerprint TEXT NOT NULL,
  ingest_run_id TEXT NOT NULL,
  PRIMARY KEY (document_id, valid_from)
);

CREATE TABLE IF NOT EXISTS entity_nodes (
  node_id TEXT NOT NULL,
  domain TEXT NOT NULL,
  entity_kind TEXT NOT NULL,
  canonical_label TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  fingerprint TEXT NOT NULL,
  ingest_run_id TEXT NOT NULL,
  PRIMARY KEY (node_id, valid_from)
);

CREATE TABLE IF NOT EXISTS entity_edges (
  edge_id TEXT NOT NULL,
  domain TEXT NOT NULL,
  edge_kind TEXT NOT NULL,
  from_node_id TEXT NOT NULL,
  to_node_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  fingerprint TEXT NOT NULL,
  ingest_run_id TEXT NOT NULL,
  PRIMARY KEY (edge_id, valid_from)
);

CREATE TABLE IF NOT EXISTS make_raw_spec_payloads (
  app_slug TEXT NOT NULL,
  app_version TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  module_count INTEGER NOT NULL,
  module_kinds_json TEXT NOT NULL,
  source_type TEXT NOT NULL,
  is_truncated INTEGER NOT NULL,
  truncation_reason TEXT NOT NULL,
  sanitization_status TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  fingerprint TEXT NOT NULL,
  ingest_run_id TEXT NOT NULL,
  PRIMARY KEY (app_slug, app_version, valid_from)
);

CREATE TABLE IF NOT EXISTS make_raw_spec_manifest_records (
  app_slug TEXT NOT NULL,
  app_version TEXT NOT NULL,
  app_label TEXT NOT NULL,
  latest INTEGER NOT NULL,
  manifest_version INTEGER NOT NULL,
  relative_path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  module_count INTEGER NOT NULL,
  module_kinds_json TEXT NOT NULL,
  source_metadata_json TEXT NOT NULL,
  manifest_sha256 TEXT NOT NULL,
  generated_at_utc TEXT NOT NULL,
  raw_spec_dir TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  fingerprint TEXT NOT NULL,
  ingest_run_id TEXT NOT NULL,
  PRIMARY KEY (app_slug, app_version, valid_from)
);

CREATE TABLE IF NOT EXISTS make_raw_spec_update_reviews (
  review_id TEXT PRIMARY KEY,
  app_slug TEXT NOT NULL,
  app_version TEXT NOT NULL,
  app_label TEXT NOT NULL,
  update_kind TEXT NOT NULL,
  review_status TEXT NOT NULL,
  review_surfaces_json TEXT NOT NULL,
  source_sha256 TEXT NOT NULL,
  previous_sha256 TEXT NOT NULL,
  previous_valid_from TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  fingerprint TEXT NOT NULL,
  ingest_run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS linter_source_artifacts (
  artifact_id TEXT NOT NULL,
  artifact_kind TEXT NOT NULL,
  source_path TEXT NOT NULL,
  payload_text TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  fingerprint TEXT NOT NULL,
  ingest_run_id TEXT NOT NULL,
  PRIMARY KEY (artifact_id, valid_from)
);

CREATE TABLE IF NOT EXISTS assisted_delivery_artifacts (
  artifact_id TEXT NOT NULL,
  artifact_kind TEXT NOT NULL,
  source_path TEXT NOT NULL,
  payload_text TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  fingerprint TEXT NOT NULL,
  ingest_run_id TEXT NOT NULL,
  PRIMARY KEY (artifact_id, valid_from)
);

CREATE TABLE IF NOT EXISTS apps (
  app_slug TEXT NOT NULL,
  label TEXT NOT NULL,
  external_id TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  fingerprint TEXT NOT NULL,
  adr_anchor TEXT NOT NULL,
  PRIMARY KEY (app_slug, valid_from)
);

CREATE TABLE IF NOT EXISTS app_versions (
  app_slug TEXT NOT NULL,
  app_version TEXT NOT NULL,
  latest INTEGER NOT NULL,
  manifest_version INTEGER NOT NULL,
  raw_spec_sha256 TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  fingerprint TEXT NOT NULL,
  adr_anchor TEXT NOT NULL,
  PRIMARY KEY (app_slug, app_version, valid_from)
);

CREATE TABLE IF NOT EXISTS modules (
  module_id TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  app_version TEXT NOT NULL,
  module_kind TEXT NOT NULL,
  internal_name TEXT NOT NULL,
  display_name TEXT NOT NULL,
  external_id TEXT NOT NULL,
  deprecated INTEGER NOT NULL,
  raw_spec_sha256 TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  fingerprint TEXT NOT NULL,
  adr_anchor TEXT NOT NULL,
  PRIMARY KEY (module_id, valid_from)
);

CREATE TABLE IF NOT EXISTS fields (
  field_id TEXT NOT NULL,
  module_id TEXT NOT NULL,
  direction TEXT NOT NULL,
  path TEXT NOT NULL,
  label TEXT NOT NULL,
  required INTEGER NOT NULL,
  field_type TEXT,
  raw_schema_json TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  fingerprint TEXT NOT NULL,
  adr_anchor TEXT NOT NULL,
  PRIMARY KEY (field_id, valid_from)
);

CREATE TABLE IF NOT EXISTS constraints (
  constraint_id TEXT NOT NULL,
  field_id TEXT NOT NULL,
  constraint_key TEXT NOT NULL,
  value_json TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  fingerprint TEXT NOT NULL,
  adr_anchor TEXT NOT NULL,
  PRIMARY KEY (constraint_id, valid_from)
);

CREATE TABLE IF NOT EXISTS module_aliases (
  alias_text TEXT NOT NULL,
  canonical_token TEXT NOT NULL,
  canonical_module_id TEXT,
  confidence TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  fingerprint TEXT NOT NULL,
  adr_anchor TEXT NOT NULL,
  PRIMARY KEY (alias_text, canonical_token, valid_from)
);

CREATE TABLE IF NOT EXISTS rule_facts (
  rule_id TEXT NOT NULL,
  domain TEXT NOT NULL,
  rule_code TEXT NOT NULL,
  severity TEXT NOT NULL,
  description TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  fingerprint TEXT NOT NULL,
  adr_anchor TEXT NOT NULL,
  PRIMARY KEY (rule_id, valid_from)
);

CREATE TABLE IF NOT EXISTS optimizer_hints (
  hint_id TEXT NOT NULL,
  domain TEXT NOT NULL,
  hint_code TEXT NOT NULL,
  severity TEXT NOT NULL,
  description TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  fingerprint TEXT NOT NULL,
  adr_anchor TEXT NOT NULL,
  PRIMARY KEY (hint_id, valid_from)
);

CREATE TABLE IF NOT EXISTS module_transaction_profiles (
  profile_id TEXT NOT NULL,
  module_selector_kind TEXT NOT NULL,
  module_selector TEXT NOT NULL,
  operation_kind TEXT NOT NULL,
  mutates_state INTEGER NOT NULL,
  rollback_capability TEXT NOT NULL,
  acid_compatibility TEXT NOT NULL,
  safety_level TEXT NOT NULL,
  description TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  fingerprint TEXT NOT NULL,
  adr_anchor TEXT NOT NULL,
  PRIMARY KEY (profile_id, valid_from)
);

CREATE TABLE IF NOT EXISTS course_claims (
  claim_id TEXT NOT NULL,
  course_path TEXT NOT NULL,
  source_range TEXT NOT NULL,
  domain TEXT NOT NULL,
  claim_text TEXT NOT NULL,
  status TEXT NOT NULL,
  adr_anchor TEXT NOT NULL,
  code_target TEXT NOT NULL,
  test_target TEXT NOT NULL,
  source_hash TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  fingerprint TEXT NOT NULL,
  PRIMARY KEY (claim_id, valid_from)
);

CREATE TABLE IF NOT EXISTS claim_evidence (
  evidence_id TEXT NOT NULL,
  claim_key TEXT NOT NULL,
  domain TEXT NOT NULL,
  value_json TEXT NOT NULL,
  claim_text TEXT NOT NULL,
  source_confidence INTEGER NOT NULL,
  evidence_observed_at TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  claim_ref TEXT,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  fingerprint TEXT NOT NULL,
  adr_anchor TEXT NOT NULL,
  PRIMARY KEY (evidence_id, valid_from)
);

CREATE TABLE IF NOT EXISTS claim_conflicts (
  conflict_id TEXT NOT NULL,
  claim_key TEXT NOT NULL,
  domain TEXT NOT NULL,
  winning_evidence_id TEXT NOT NULL,
  losing_evidence_id TEXT NOT NULL,
  winning_value_json TEXT NOT NULL,
  losing_value_json TEXT NOT NULL,
  winning_source_kind TEXT NOT NULL,
  winning_source_ref TEXT NOT NULL,
  losing_source_kind TEXT NOT NULL,
  losing_source_ref TEXT NOT NULL,
  winning_source_confidence INTEGER NOT NULL,
  losing_source_confidence INTEGER NOT NULL,
  winning_evidence_observed_at TEXT NOT NULL,
  losing_evidence_observed_at TEXT NOT NULL,
  resolution_status TEXT NOT NULL,
  arbitration_reason TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  fingerprint TEXT NOT NULL,
  adr_anchor TEXT NOT NULL,
  PRIMARY KEY (conflict_id, valid_from)
);

CREATE TABLE IF NOT EXISTS designer_message_evidence (
  finding_id TEXT NOT NULL,
  node_id TEXT,
  module_slug TEXT,
  severity TEXT NOT NULL,
  message TEXT NOT NULL,
  category TEXT,
  field_path TEXT,
  review_status TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  fingerprint TEXT NOT NULL,
  adr_anchor TEXT NOT NULL,
  PRIMARY KEY (finding_id, valid_from)
);

CREATE TABLE IF NOT EXISTS native_module_expectations (
  app_slug TEXT NOT NULL,
  expected_module_count INTEGER NOT NULL,
  expected_kinds_csv TEXT NOT NULL,
  critical INTEGER NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  fingerprint TEXT NOT NULL,
  adr_anchor TEXT NOT NULL,
  PRIMARY KEY (app_slug, valid_from)
);

CREATE TABLE IF NOT EXISTS catalog_plan_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog_plan_ranges (
  range_id INTEGER PRIMARY KEY,
  range_label TEXT NOT NULL UNIQUE,
  range_start INTEGER NOT NULL,
  range_end INTEGER NOT NULL,
  surface TEXT NOT NULL,
  status TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT
);

CREATE TABLE IF NOT EXISTS catalog_plan_units (
  unit_number INTEGER PRIMARY KEY,
  range_id INTEGER NOT NULL REFERENCES catalog_plan_ranges(range_id),
  status TEXT NOT NULL,
  surface TEXT NOT NULL,
  evidence_path TEXT NOT NULL DEFAULT '',
  commit_hash TEXT NOT NULL DEFAULT '',
  semantic_answer_sha256 TEXT,
  updated_at_utc TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT
);

CREATE TABLE IF NOT EXISTS catalog_plan_progress_events (
  event_id TEXT PRIMARY KEY,
  legacy_event_id INTEGER,
  unit_number INTEGER REFERENCES catalog_plan_units(unit_number),
  event_type TEXT NOT NULL,
  event_json TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  fingerprint TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog_plan_semantic_answers (
  unit_number INTEGER NOT NULL REFERENCES catalog_plan_units(unit_number),
  unit_id TEXT NOT NULL,
  answer_json TEXT NOT NULL,
  answer_sha256 TEXT NOT NULL,
  answer_status TEXT NOT NULL,
  evidence_status TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  saved_by_tool TEXT NOT NULL,
  valid_to TEXT,
  PRIMARY KEY (unit_number, answer_sha256)
);

CREATE TABLE IF NOT EXISTS catalog_plan_quarantine_records (
  quarantine_id TEXT PRIMARY KEY,
  unit_number INTEGER,
  unit_id TEXT,
  quarantine_kind TEXT NOT NULL,
  reason TEXT NOT NULL,
  evidence_gap_json TEXT NOT NULL,
  retry_policy_json TEXT NOT NULL,
  priority INTEGER NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  resolved_at_utc TEXT
);

CREATE TABLE IF NOT EXISTS catalog_runs (
  run_id TEXT PRIMARY KEY,
  run_status TEXT NOT NULL,
  reset_strategy TEXT NOT NULL,
  priority_policy_json TEXT NOT NULL,
  old_semantic_status TEXT NOT NULL,
  incomplete_coverage_policy TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  fingerprint TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog_units (
  run_id TEXT NOT NULL REFERENCES catalog_runs(run_id),
  unit_id TEXT NOT NULL,
  unit_type TEXT NOT NULL,
  priority_band TEXT NOT NULL,
  priority_order INTEGER NOT NULL,
  source_ref TEXT NOT NULL,
  source_hash TEXT NOT NULL,
  source_size_bytes INTEGER NOT NULL,
  complexity_score INTEGER NOT NULL,
  status TEXT NOT NULL,
  locked_by TEXT,
  locked_at_utc TEXT,
  lease_expires_at_utc TEXT,
  lease_token TEXT,
  attempt_count INTEGER NOT NULL,
  completed_at_utc TEXT,
  validation_status TEXT NOT NULL,
  coverage_status TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  PRIMARY KEY (run_id, unit_id)
);

CREATE TABLE IF NOT EXISTS catalog_unit_notes (
  run_id TEXT NOT NULL,
  unit_id TEXT NOT NULL,
  note_surface TEXT NOT NULL,
  note_text TEXT NOT NULL,
  note_status TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  PRIMARY KEY (run_id, unit_id, note_surface),
  FOREIGN KEY (run_id, unit_id) REFERENCES catalog_units(run_id, unit_id)
);

CREATE TABLE IF NOT EXISTS catalog_unit_outputs (
  run_id TEXT NOT NULL,
  unit_id TEXT NOT NULL,
  lease_token TEXT NOT NULL,
  worker_id TEXT NOT NULL,
  output_json TEXT NOT NULL,
  output_sha256 TEXT NOT NULL,
  validation_status TEXT NOT NULL,
  saved_by_tool TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  PRIMARY KEY (run_id, unit_id, output_sha256),
  FOREIGN KEY (run_id, unit_id) REFERENCES catalog_units(run_id, unit_id)
);

CREATE TABLE IF NOT EXISTS catalog_module_intelligence_metadata (
  run_id TEXT NOT NULL,
  unit_id TEXT NOT NULL,
  module_id TEXT NOT NULL,
  input_schema_json TEXT,
  output_schema_json TEXT,
  field_constraints_json TEXT,
  error_rate_percentage REAL,
  api_rate_limit_rpm INTEGER,
  avg_execution_time_ms INTEGER,
  common_error_codes_json TEXT,
  auth_type TEXT,
  required_scopes_json TEXT,
  token_refresh_supported INTEGER,
  output_cardinality TEXT,
  requires_iterator INTEGER,
  suggested_control_structures_json TEXT,
  operation_cost_multiplier REAL,
  batch_processing_supported INTEGER,
  cheaper_alternative_module_id TEXT,
  evidence_status TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  valid_to TEXT,
  fingerprint TEXT NOT NULL,
  PRIMARY KEY (run_id, unit_id, module_id),
  FOREIGN KEY (run_id, unit_id) REFERENCES catalog_units(run_id, unit_id)
);

CREATE TABLE IF NOT EXISTS catalog_modification_events (
  event_id TEXT PRIMARY KEY,
  tool_name TEXT NOT NULL,
  operation TEXT NOT NULL,
  target_kind TEXT NOT NULL,
  target_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  worker_id TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  fingerprint TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog_edge_proposals (
  proposal_id TEXT PRIMARY KEY,
  domain TEXT NOT NULL,
  edge_kind TEXT NOT NULL,
  from_node_id TEXT NOT NULL,
  to_node_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  rationale TEXT NOT NULL,
  proposal_status TEXT NOT NULL,
  proposed_by TEXT NOT NULL,
  applied_edge_id TEXT,
  created_at_utc TEXT NOT NULL,
  applied_at_utc TEXT,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  fingerprint TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog_review_records (
  review_id TEXT PRIMARY KEY,
  domain TEXT NOT NULL,
  target_kind TEXT NOT NULL,
  target_id TEXT NOT NULL,
  review_status TEXT NOT NULL,
  priority INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  fingerprint TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog_legacy_semantic_archives (
  archive_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES catalog_runs(run_id),
  obsolete_status TEXT NOT NULL,
  legacy_range_count INTEGER NOT NULL,
  legacy_unit_count INTEGER NOT NULL,
  legacy_answer_count INTEGER NOT NULL,
  legacy_quarantine_count INTEGER NOT NULL,
  archived_at_utc TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  fingerprint TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog_search_documents (
  document_id TEXT PRIMARY KEY,
  surface TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  record_kind TEXT NOT NULL,
  tags_json TEXT NOT NULL,
  search_text TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT
);

CREATE VIEW IF NOT EXISTS catalog_run_progress AS
SELECT
  runs.run_id AS run_id,
  COUNT(units.unit_id) AS total_unit_count,
  COALESCE(SUM(CASE WHEN units.status = 'completed' THEN 1 ELSE 0 END), 0)
    AS completed_unit_count,
  COALESCE(SUM(units.complexity_score), 0) AS total_complexity_score,
  COALESCE(
    SUM(CASE WHEN units.status = 'completed' THEN units.complexity_score ELSE 0 END),
    0
  ) AS completed_complexity_score,
  COALESCE(SUM(CASE WHEN units.status != 'completed' THEN 1 ELSE 0 END), 0)
    AS incomplete_unit_count,
  CASE
    WHEN COUNT(units.unit_id) = 0 THEN 0.0
    ELSE COALESCE(SUM(CASE WHEN units.status = 'completed' THEN 1 ELSE 0 END), 0) * 1.0
      / COUNT(units.unit_id)
  END AS unit_count_progress_ratio,
  CASE
    WHEN COALESCE(SUM(units.complexity_score), 0) = 0 THEN 0.0
    ELSE COALESCE(
      SUM(CASE WHEN units.status = 'completed' THEN units.complexity_score ELSE 0 END),
      0
    ) * 1.0 / SUM(units.complexity_score)
  END AS weighted_progress_ratio,
  CASE
    WHEN COALESCE(SUM(CASE WHEN units.status != 'completed' THEN 1 ELSE 0 END), 0) = 0
      THEN 'complete'
    ELSE 'incomplete_non_blocking'
  END AS coverage_status
FROM catalog_runs AS runs
LEFT JOIN catalog_units AS units
  ON units.run_id = runs.run_id
GROUP BY runs.run_id;

CREATE TABLE IF NOT EXISTS make_datastore_structure_evidence (
  evidence_id TEXT PRIMARY KEY,
  app_slug TEXT NOT NULL,
  datastore_slug TEXT NOT NULL,
  structure_json TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  observed_at_utc TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT
);

CREATE TABLE IF NOT EXISTS make_webhook_structure_evidence (
  evidence_id TEXT PRIMARY KEY,
  app_slug TEXT NOT NULL,
  webhook_slug TEXT NOT NULL,
  structure_json TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  observed_at_utc TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT
);

CREATE TABLE IF NOT EXISTS make_scraped_datastore_evidence (
  evidence_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  resource_slug TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  observed_at_utc TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT
);

CREATE TABLE IF NOT EXISTS make_scraped_webhook_evidence (
  evidence_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  resource_slug TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  observed_at_utc TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT
);

CREATE TABLE IF NOT EXISTS make_scraped_structure_evidence (
  evidence_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  resource_slug TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  observed_at_utc TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT
);

CREATE TABLE IF NOT EXISTS make_scraped_connection_evidence (
  evidence_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  resource_slug TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  observed_at_utc TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT
);

CREATE TABLE IF NOT EXISTS make_scraped_scope_evidence (
  evidence_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  resource_slug TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  observed_at_utc TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT
);

CREATE TABLE IF NOT EXISTS make_scraped_import_export_evidence (
  evidence_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  resource_slug TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  observed_at_utc TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT
);

CREATE TABLE IF NOT EXISTS linter_rule_surface_matrix (
  family_id TEXT PRIMARY KEY,
  rule_surface TEXT NOT NULL,
  owner_path TEXT NOT NULL,
  code_predicate_sources_json TEXT NOT NULL,
  sqlite_predicate_sources_json TEXT NOT NULL,
  source_tables_json TEXT NOT NULL,
  source_files_json TEXT NOT NULL,
  promoted_code_count INTEGER NOT NULL,
  output_affecting INTEGER NOT NULL,
  fingerprint TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT
);

CREATE TABLE IF NOT EXISTS linter_data_source_inventory (
  inventory_id TEXT PRIMARY KEY,
  source_path TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  authority_state TEXT NOT NULL,
  sqlite_table TEXT NOT NULL,
  consumed_policy TEXT NOT NULL,
  source_of_truth TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  fingerprint TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT
);

CREATE INDEX IF NOT EXISTS idx_modules_current_app
  ON modules (app_slug, valid_to, module_kind);

CREATE INDEX IF NOT EXISTS idx_modules_current_exact_lookup
  ON modules (valid_to, deprecated, lower(module_id), module_id);

CREATE INDEX IF NOT EXISTS idx_modules_current_search_rank
  ON modules (
    valid_to, deprecated, app_slug, module_kind, internal_name, display_name, module_id
  );

CREATE INDEX IF NOT EXISTS idx_apps_current_key
  ON apps (app_slug, valid_to);

CREATE INDEX IF NOT EXISTS idx_app_versions_current_key
  ON app_versions (app_slug, app_version, valid_to);

CREATE INDEX IF NOT EXISTS idx_modules_current_key
  ON modules (module_id, valid_to);

CREATE INDEX IF NOT EXISTS idx_fields_current_key
  ON fields (field_id, valid_to);

CREATE INDEX IF NOT EXISTS idx_fields_current_module_scan
  ON fields (valid_to, module_id);

CREATE INDEX IF NOT EXISTS idx_constraints_current_key
  ON constraints (constraint_id, valid_to);

CREATE INDEX IF NOT EXISTS idx_aliases_current_key
  ON module_aliases (alias_text, canonical_token, valid_to);

CREATE INDEX IF NOT EXISTS idx_rule_facts_current_code
  ON rule_facts (rule_code, valid_to);

CREATE INDEX IF NOT EXISTS idx_optimizer_hints_current_code
  ON optimizer_hints (hint_code, valid_to);

CREATE INDEX IF NOT EXISTS idx_transaction_profiles_current_selector
  ON module_transaction_profiles (module_selector_kind, module_selector, valid_to);

CREATE INDEX IF NOT EXISTS idx_claim_evidence_current_key
  ON claim_evidence (claim_key, valid_to);

CREATE INDEX IF NOT EXISTS idx_claim_conflicts_current_key
  ON claim_conflicts (claim_key, valid_to);

CREATE INDEX IF NOT EXISTS idx_designer_message_evidence_current_node
  ON designer_message_evidence (
    review_status, source_kind, severity, node_id, module_slug, valid_to
  );

CREATE INDEX IF NOT EXISTS idx_catalog_plan_units_status
  ON catalog_plan_units (status, unit_number);

CREATE INDEX IF NOT EXISTS idx_catalog_plan_units_range
  ON catalog_plan_units (range_id, unit_number);

CREATE INDEX IF NOT EXISTS idx_catalog_plan_answers_current
  ON catalog_plan_semantic_answers (unit_number, valid_to);

CREATE INDEX IF NOT EXISTS idx_catalog_plan_answers_valid_scan
  ON catalog_plan_semantic_answers (valid_to, unit_number, created_at_utc);

CREATE INDEX IF NOT EXISTS idx_catalog_plan_quarantine_status
  ON catalog_plan_quarantine_records (status, priority, unit_number);

CREATE INDEX IF NOT EXISTS idx_catalog_plan_quarantine_open_priority
  ON catalog_plan_quarantine_records (
    resolved_at_utc, priority, created_at_utc, quarantine_id
  );

CREATE INDEX IF NOT EXISTS idx_catalog_runs_status
  ON catalog_runs (run_status, created_at_utc);

CREATE INDEX IF NOT EXISTS idx_catalog_units_work_order
  ON catalog_units (
    run_id, status, priority_order, priority_band, unit_type, source_size_bytes
  );

CREATE INDEX IF NOT EXISTS idx_catalog_units_lease
  ON catalog_units (run_id, locked_by, lease_expires_at_utc, lease_token);

CREATE INDEX IF NOT EXISTS idx_catalog_units_weighted_progress
  ON catalog_units (run_id, status, complexity_score);

CREATE INDEX IF NOT EXISTS idx_catalog_unit_notes_surface
  ON catalog_unit_notes (run_id, note_surface, note_status);

CREATE INDEX IF NOT EXISTS idx_catalog_unit_outputs_unit
  ON catalog_unit_outputs (run_id, unit_id, created_at_utc);

CREATE INDEX IF NOT EXISTS idx_catalog_module_intelligence_module
  ON catalog_module_intelligence_metadata (module_id, valid_to, created_at_utc);

CREATE INDEX IF NOT EXISTS idx_catalog_modification_events_target
  ON catalog_modification_events (target_kind, target_id, created_at_utc);

CREATE INDEX IF NOT EXISTS idx_catalog_edge_proposals_status
  ON catalog_edge_proposals (proposal_status, domain, edge_kind);

CREATE INDEX IF NOT EXISTS idx_catalog_review_records_target
  ON catalog_review_records (domain, target_kind, target_id, review_status);

CREATE INDEX IF NOT EXISTS idx_catalog_legacy_semantic_archives_run
  ON catalog_legacy_semantic_archives (run_id, obsolete_status);

CREATE INDEX IF NOT EXISTS idx_catalog_search_documents_current
  ON catalog_search_documents (surface, record_kind, valid_to);

CREATE INDEX IF NOT EXISTS idx_make_datastore_evidence_current
  ON make_datastore_structure_evidence (app_slug, datastore_slug, valid_to);

CREATE INDEX IF NOT EXISTS idx_make_webhook_evidence_current
  ON make_webhook_structure_evidence (app_slug, webhook_slug, valid_to);

CREATE INDEX IF NOT EXISTS idx_make_scraped_datastore_current
  ON make_scraped_datastore_evidence (project_id, node_id, valid_to);

CREATE INDEX IF NOT EXISTS idx_make_scraped_webhook_current
  ON make_scraped_webhook_evidence (project_id, node_id, valid_to);

CREATE INDEX IF NOT EXISTS idx_make_scraped_structure_current
  ON make_scraped_structure_evidence (project_id, node_id, valid_to);

CREATE INDEX IF NOT EXISTS idx_make_scraped_connection_current
  ON make_scraped_connection_evidence (project_id, node_id, valid_to);

CREATE INDEX IF NOT EXISTS idx_make_scraped_scope_current
  ON make_scraped_scope_evidence (project_id, node_id, valid_to);

CREATE INDEX IF NOT EXISTS idx_make_scraped_import_export_current
  ON make_scraped_import_export_evidence (project_id, node_id, valid_to);

CREATE INDEX IF NOT EXISTS idx_linter_rule_surface_matrix_surface
  ON linter_rule_surface_matrix (rule_surface, owner_path);

CREATE INDEX IF NOT EXISTS idx_linter_data_source_inventory_authority
  ON linter_data_source_inventory (authority_state, sqlite_table);

CREATE INDEX IF NOT EXISTS idx_source_documents_current
  ON source_documents (domain, source_path, valid_to);

CREATE INDEX IF NOT EXISTS idx_entity_nodes_current
  ON entity_nodes (domain, entity_kind, canonical_label, valid_to);

CREATE INDEX IF NOT EXISTS idx_entity_edges_current
  ON entity_edges (domain, edge_kind, from_node_id, to_node_id, valid_to);

CREATE INDEX IF NOT EXISTS idx_make_raw_spec_payloads_current
  ON make_raw_spec_payloads (app_slug, app_version, valid_to);

CREATE INDEX IF NOT EXISTS idx_make_raw_spec_manifest_records_current
  ON make_raw_spec_manifest_records (app_slug, app_version, generated_at_utc, valid_to);

CREATE INDEX IF NOT EXISTS idx_make_raw_spec_manifest_records_latest_metadata
  ON make_raw_spec_manifest_records (valid_to, generated_at_utc DESC, raw_spec_dir);

CREATE INDEX IF NOT EXISTS idx_make_raw_spec_update_reviews_pending
  ON make_raw_spec_update_reviews (
    review_status, valid_to, app_slug, app_version, update_kind
  );

CREATE INDEX IF NOT EXISTS idx_linter_source_artifacts_current
  ON linter_source_artifacts (artifact_kind, source_path, valid_to);

CREATE INDEX IF NOT EXISTS idx_assisted_delivery_artifacts_current
  ON assisted_delivery_artifacts (artifact_kind, source_path, valid_to);

INSERT OR REPLACE INTO snapshot_metadata (key, value)
VALUES ('schema_version', '13');
