# Diff Blueprint Fixtures

These fixtures are synthetic known-good triplets for `blueprint.diff` tests.
They do not come from Make.com exports and must not contain account IDs,
credential values, live connection identifiers, or private endpoint details.

## File Boundary

This folder owns sanitized blueprint comparison fixtures for structured diff
contracts. It must not contain live Make exports or become a durable diff
artifact store.

## Triplets

- `generated_router.json`: draft local router blueprint with intentional drift.
- `exported_router.json`: synthetic reviewed export shape.
- `known_good_router.json`: synthetic known-good reference matching the reviewed
  export shape.

The triplet covers route/filter semantic drift, metadata-only drift, designer
layout drift, connection reference drift, and placeholder drift.

## Roundtrip Discovery Pipeline

Every observed generated-to-Make-reexport delta must be routed to a generalized
rule target instead of a one-off project patch:

- `volatile_noise`: candidate canonicalizer rule after repeated evidence.
- `native_shape_rule`: module projector, manifest, matrix, or semantic diff rule.
- `layout_rule`: Make-native layout policy.
- `restore_expect_rule`: metadata `expect` or `restore` generation.
- `runtime_binding_rule`: readiness or runtime resource binding policy.
- `semantic_breakage`: behavior-changing diff until fixtures prove otherwise.
- `zero_trace_violation`: hard export gate.
- `unknown_requires_evidence`: quarantine until another fixture or corpus sample exists.

Fixture assertions must reject project names, demo IDs, and one-off values as
repair logic. Those values can appear only as fixture-local data, never as
compiler conditions.
