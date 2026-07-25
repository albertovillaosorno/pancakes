# Make-Native Parity Completion Gates Policy

## Status

Accepted

## Scope

repository/make-adapter

## Context

Pancakes can now render Make-native blueprint artifacts, but a successful import is not the same as
full Make.com coverage. The adapter needs an explicit definition of `perfect within declared scope`
so reports and MCP tools can be precise without pretending every Make module, filter, UI state, or
roundtrip behavior is supported.

The Make backend must optimize for native shape and roundtrip stability inside a declared scope,
while unsupported or weakly supported areas remain labeled as unsupported or safe pass-through.

## Scope V1

The first serious Make-native parity scope is:

- `webhook`
- `router`
- `datastore`
- `slack`
- `basic_filters`
- `runtime_placeholders`
- `import_readiness`
- `zero_trace`
- `handoff_report_abstraction`
- `giant_stress_fixtures`
- `semantic_diff_classification`

This scope is allowed to become perfect within declared scope. It is not complete across all of
Make.com.

## Completion States

Make-native parity uses these ordered states:

- `not_supported`: no support claim; no pass-through or import guarantee.
- `pass_through`: Pancakes preserves a safe artifact without claiming native parity.
- `import_safe`: Pancakes can render an importable zero-trace artifact by default.
- `native_shape`: mapper, parameters, metadata, layout, filters, and placeholders match known
  Make-native shape for the supported case.
- `roundtrip_stable`: generated artifact and Make re-export have minimal semantic diff under the
  canonical diff rules for that fixture family.

The states prevent false claims. A module can be import-safe without being native-shape, and a
native-shape module can still be below roundtrip-stable until re-export evidence supports it.

## Required Completion Gates

A v1 scope item is complete only when it satisfies every gate below:

- `manifest_or_matrix_record`
- `fixture_family_coverage`
- `damp_tests_where_lineage_matters`
- `native_mapper_parameters_expect_restore_coverage`
- `zero_trace_coverage`
- `diff_classification_coverage`
- `pass_through_behavior_for_unsupported_variants`
- `import_export_dry_run_evidence`
- `no_live_make_or_provider_call_by_default`

Gates whose wording says `where_lineage_matters` or `coverage` are still mandatory. If a specific
scope item has no lineage-bearing behavior or no module-native UI shape, the evidence must say why
that gate is not applicable for that item rather than silently omitting it.

## Product Claim Boundary

The product principle is:

```text
perfect within declared scope, not complete across all of Make.com
```

Reports, MCP tool output, docs, and handoff copy must not collapse `pass_through`, `import_safe`,
`native_shape`, and `roundtrip_stable` into one vague success state. They must preserve the current
state and the missing gates when a scope item is incomplete.

## Validation

The enforceable gate vocabulary lives in `src/languages/make/parity_gates.py`.
`tests/languages/make/make_native_parity_completion_gates_contract.py` verifies the v1 scope,
states, required gates, completion logic, and false-claim guard.
