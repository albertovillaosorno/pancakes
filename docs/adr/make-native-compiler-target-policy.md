# Make-Native Compiler Target Policy

## Status

Accepted

## Scope

repository/make-adapter

## Context

Pancakes is the core engine. Make.com is the first supported automation language and blueprint
target, but a Make blueprint is not plain JSON and must not be treated as a formatting exercise.

A useful Make artifact combines graph structure, runtime binding requirements, module-native data
shapes, router and filter behavior, editor state, import and re-export behavior, risk scoring, and
client-safe report abstraction. A blueprint can import successfully and still be below native parity
if filters, mapper shape, metadata, restore state, or runtime binding posture drift from how Make
itself represents the scenario.

## Decision

Pancakes treats Make blueprints as a compiler target:

```text
Make blueprint = graph semantics + runtime bindings + module-native shapes + router/filter semantics
               + editor/UI state + import/re-export behavior + risk model + report abstraction
```

The target must be learned from first principles and generalized into compiler rules. Manual
roundtrip discoveries are evidence for rule extraction, not permission to add demo-specific patches.

## First-Principles Doctrine

Pancakes targets all Make.com patterns by generalization, but it must not claim complete Make.com
platform coverage until local evidence supports that claim. Implementation may be staged; the
architecture must keep the improvement ceiling open.

The parity doctrine treats Make as these dimensions:

- `graph_semantics`
- `runtime_bindings`
- `module_native_shapes`
- `router_filter_semantics`
- `editor_ui_state`
- `import_reexport_behavior`
- `risk_model`
- `report_abstraction`

Every Make improvement must become at least one reusable unit:

- `pattern`
- `manifest`
- `projector`
- `matrix_record`
- `diff_rule`
- `fixture_family`
- `deterministic_test`

Browser, API, and re-export observations are evidence intake, not durable product behavior by
themselves. Evidence must move through this promotion path before it supports a product claim:

- `browser_or_api_observation`
- `redacted_local_fixture`
- `generalized_rule`
- `deterministic_test`
- `matrix_or_manifest_update`

Unknown or weakly understood Make behavior must use one of these postures:

- `pass_through`
- `advisory_gap`
- `preserve_customer_artifact`

This doctrine rejects JSON pretty-printing as the target, single-demo patches as fixes, live
provider calls by default, and full-platform claims without evidence.

## Target Layers

1. Graph semantics: modules, routes, node IDs, references, and data lineage.
2. Runtime bindings: connections, data store IDs, webhook hooks, and runtime placeholders.
3. Module-native shapes: mapper, parameters, expect, restore, and interface.
4. Router and filter semantics: filter location, condition arrays, and typed operators.
5. Editor state: Make metadata, restore state, layout, notes, and designer fields.
6. Import and re-export behavior: changes Make applies after import and later export.
7. Risk model: import readiness, handoff readiness, drift, runtime gaps, and secret risk.
8. Report abstraction: client-visible outcomes that do not reveal the private mechanism.

## Layering Constraints

- The core AST and IR remain neutral.
- Make-specific behavior lives under `src/languages/make/**`.
- Generic graph semantics belong in the neutral AST or IR surfaces only when they are not Make
  specific.
- Make-native parity and repeatable roundtrip behavior are the same engineering problem.
- Re-export evidence is used to extract general rules, never hard-coded demo exceptions.
- Unknown modules must preserve pass-through client artifacts and avoid corrupting customer-owned
  fields.
- Zero-trace export remains a hard gate for client-facing Make artifacts.

## Consequences

- `src/languages/make/**` owns Make-native module projection, parameter aliases, filter lowering,
  layout policy, metadata projection, zero-trace export checks, and importable blueprint rendering.
- Core AST and IR code may expose reusable graph, reference, lineage, validation, and report
  primitives, but must not import Make-only details such as `__IMTCONN__`, Make restore shape, or
  module-family mapper quirks.
- New Make discoveries must come with fixtures or tests that prove the general class of behavior.
- Generated artifacts can be import-safe before they are client-handoff-ready; reports must keep
  those readiness surfaces separate.

## Rejected Alternatives

- Treating Make as a simple JSON pretty-printer target.
- Patching only the current demo blueprint after every Make import failure.
- Moving Make UI metadata, parameter aliases, or connection projection into the neutral core.
- Claiming roundtrip parity from one successful import without re-export evidence.

## Validation

- Make adapter tests must cover target-specific projection under `src/languages/make/**`.
- Diff and roundtrip fixtures should classify layout, filter, mapper, metadata, restore, runtime
  placeholder, zero-trace, and native parity gaps without leaking private values.
- Unknown-module tests should prove pass-through behavior preserves source artifacts unless a
  validated Make-specific rule owns a transformation.
- `src/languages/make/parity_doctrine.py` is the enforceable source for the first-principles
  doctrine vocabulary.
- `tests/languages/make/make_native_parity_doctrine_contract.py` verifies the dimensions,
  reusable improvement units, evidence promotion path, unknown posture, and claim boundary.
