# Lead Routing Portfolio Checklist

- [ ] Project source of truth is `scenario.json`.
- [ ] `project.validate_offline` runs successfully.
- [ ] `live_make_called` is `false`.
- [ ] `credentials_required` is `false`.
- [ ] `missing_module_blockers` is empty.
- [ ] `runtime_configuration_required` only includes expected placeholders:
  - `runtime.webhook.lead_intake_hook`
  - `runtime.datastore.qualified_leads`
  - `runtime.datastore.incomplete_leads`
- [ ] No fake module IDs are introduced.
- [ ] Warnings/optimization hints are understood and documented in notes.
- [ ] Offline payload files are fake:
  - `sample_payloads.json`
  - `expected_outputs.json`
- [ ] `validation_summary.next_actions` is actionable and non-empty while errors exist.
