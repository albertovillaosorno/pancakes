# Make AST Contract Policy

## Status

Accepted

## Scope

repository/make-ast

## Decision

## File Boundary

This ADR is a canonical policy record. It owns durable decision rules, scope, consequences,
traceability anchors, and derived-artifact obligations. It must not be used as round evidence,
migration inventory, or scratch notes.

## repo.make-ast.root-scenario-flow-metadata-contract

```json strict-policy
{
  "anchor": "repo.make-ast.root-scenario-flow-metadata-contract",
  "rule": "The Make AST root is typed around scenario identity, flow nodes, metadata, scenario inputs, scenario outputs, and schedule or trigger configuration.",
  "root_keys": ["name", "flow", "metadata"],
  "required_posture": [
    "parse JSON into typed domain structures before validation or generation",
    "preserve raw payloads for lossless future rendering",
    "treat scenario input and output declarations as first-class AST metadata"
  ]
}
```
## repo.make-ast.node-categories-and-source-trace

```json strict-policy
{
  "anchor": "repo.make-ast.node-categories-and-source-trace",
  "rule": "AST nodes expose typed node categories, source trace, and raw-spec binding fields.",
  "node_categories": [
    "module",
    "route",
    "filter",
    "router",
    "iterator",
    "aggregator",
    "webhook",
    "HTTP/API",
    "data store",
    "AI agent",
    "MCP/tool",
    "scenario input",
    "scenario output",
    "error-handler route",
    "schedule/trigger config",
    "unresolved"
  ],
  "source_trace_fields": [
    "path",
    "container_kind",
    "parent_node_id",
    "raw_node_id",
    "raw_module_token"
  ],
  "raw_spec_binding_fields": ["status", "catalog_module_id", "raw_spec_sha256", "issues"]
}
```
## repo.make-ast.route-filter-condition-normalization

```json strict-policy
{
  "anchor": "repo.make-ast.route-filter-condition-normalization",
  "rule": "Route-like AST filters expose a usable typed conditions object without dropping the original Make export payload.",
  "accepted_condition_shapes": [
    "conditions object",
    "condition scalar or object",
    "rules array or object",
    "expression scalar or object"
  ],
  "required_posture": [
    "canonical conditions objects remain unchanged",
    "alias-based filter conditions are wrapped under their source alias",
    "raw filter payloads preserve every original field for future lossless rendering",
    "validators treat supported aliases as non-empty filter conditions"
  ]
}
```
## repo.make-ast.unknown-fields-preserved

```json strict-policy
{
  "anchor": "repo.make-ast.unknown-fields-preserved",
  "rule": "Unknown or unsupported AST fields and module tokens must be preserved safely rather than dropped.",
  "required_posture": [
    "unsupported module tokens become unresolved nodes",
    "unsupported custom module tokens remain pass-through evidence instead of being deleted",
    "catalog-backed custom modules may resolve only when explicit source provenance exists",
    "unknown node fields remain available through unknown_fields and raw_payload",
    "raw payloads remain JSON-valid after parsing"
  ],
  "forbidden_posture": [
    "silently deleting unknown Make export fields",
    "treating unsupported modules as known catalog modules",
    "letting raw untyped JSON drive downstream domain logic without parsing"
  ]
}
```
## repo.make-ast.traversal-contract

```json strict-policy
{
  "anchor": "repo.make-ast.traversal-contract",
  "rule": "AST traversal is deterministic preorder through root flow, route flows, branch flows, tool flows, and direct error-handler children.",
  "recursive_child_paths": [
    "flow",
    "routes[].flow",
    "branches[].flow",
    "tools[].flow",
    "onerror[]",
    "on_error[]"
  ],
  "validation_requirement": "Tests must prove node identity, parent trace, child traversal, and unresolved-node retention."
}
```
## repo.make-ast.semantic-surface-ssot

```json strict-policy
{
  "anchor": "repo.make-ast.semantic-surface-ssot",
  "rule": "The active AST model is the single source of truth for node kind, source trace, traversal, and catalog/raw-spec binding.",
  "semantic_consumers": [
    "Validation owns deterministic semantic findings",
    "Repair owns repair candidate projection",
    "AST owns typed structure and local evidence only"
  ],
  "required_posture": [
    "semantic rules are implemented in the bounded context that consumes them",
    "AST nodes remain stable typed evidence instead of a second runtime policy engine",
    "retired promoted semantic attachment reports must not be restored as canonical runtime state"
  ],
  "forbidden_posture": [
    "creating a second semantic-attachment SSOT beside the typed AST",
    "using promotion-policy messages as validation truth",
    "making runtime code depend on stale generated semantic reports"
  ]
}
```
## repo.make-ast.catalog-backed-assembly

```json strict-policy
{
  "anchor": "repo.make-ast.catalog-backed-assembly",
  "rule": "Blueprint assembly may create AST roots only from canonical catalog module IDs and caller-supplied mappings.",
  "required_posture": [
    "requested modules are resolved by exact catalog module ID",
    "raw-spec binding metadata is embedded for validation and traceability",
    "root metadata includes scenario, designer, notes, placeholder registry, and schedule scaffolding",
    "assembled nodes include safe integer version and designer metadata",
    "the assembler does not invent modules, field values, or placeholder mappings",
    "assembled output must pass the normal validation and renderer gates before importable JSON is emitted"
  ],
  "forbidden_posture": [
    "assembling free-form module names directly into importable JSON",
    "bypassing catalog validation",
    "creating fake placeholder modules to satisfy a request"
  ]
}
```
## repo.make-ast.export-local-evidence-and-control-flow

```json strict-policy
{
  "anchor": "repo.make-ast.export-local-evidence-and-control-flow",
  "rule": "Make export-local metadata and native control-flow nodes are AST evidence and must not be discarded during parsing, validation, repair, rendering, or explanation.",
  "export_local_metadata": ["metadata.notes", "metadata.expect", "metadata.parameters"],
  "control_flow_posture": [
    "direct error-handler children under onerror[] and on_error[] are traversed",
    "Make-owned builtin:* control modules inside error-handler arrays are native control-flow evidence",
    "builtin:* control modules do not require app-catalog rows merely to pass offline diagnostics"
  ],
  "required_posture": [
    "notes remain anchored under blueprint metadata instead of a second notes authority",
    "node-local metadata can support compatibility checks for that exact node",
    "offline diagnostics preserve native control-flow evidence"
  ]
}
```
## repo.make-ast.delta-reporting

```json strict-policy
{
  "anchor": "repo.make-ast.delta-reporting",
  "rule": "AST payload comparison is an AST concern and returns deterministic added, removed, and changed JSON paths.",
  "implementation_tool": "src/blueprints/ast/delta.py",
  "required_posture": [
    "delta reports are local and deterministic",
    "generated artifact persistence is not part of the AST delta utility",
    "obsolete Axiom or legacy artifact settings are not restored"
  ],
  "forbidden_posture": [
    "writing artifact bundles from AST comparison",
    "depending on retired artifact directory policies",
    "placing generated comparison output under src/"
  ]
}
```
## repo.make-ast.local-evidence-reporting

```json strict-policy
{
  "anchor": "repo.make-ast.local-evidence-reporting",
  "rule": "AST may expose deterministic local evidence paths for opaque fields and designer message locations without writing generated artifact bundles.",
  "implementation_tool": "src/blueprints/ast/evidence.py",
  "required_posture": [
    "opaque fields are reported as JSON paths derived from the typed AST",
    "designer message evidence reports paths and counts without becoming validation policy",
    "diagnostic evidence is in-memory unless a caller deliberately stores it under an approved data, cache, or temp location"
  ],
  "forbidden_posture": [
    "writing root artifacts/make_blueprints bundles",
    "making AST evidence depend on retired Axiom settings",
    "treating evidence reports as a second validation or repair SSOT"
  ]
}
```
## repo.make-ast.blueprint-bundle-persistence

```json strict-policy
{
  "anchor": "repo.make-ast.blueprint-bundle-persistence",
  "rule": "Durable blueprint bundle persistence is allowed only under data/blueprints with repository-relative manifest paths.",
  "implementation_tool": "src/blueprints/ast/artifacts.py",
  "canonical_data_root": "data/blueprints",
  "required_posture": [
    "bundle slugs are deterministic and filesystem-safe",
    "manifest file paths are repository-relative",
    "manifest checksums record bundle file SHA-256 digests and validation reports mismatches",
    "manifest file and checksum keys are limited to canonical bundle file stems and must include source_ast",
    "canonical optional bundle JSON files present on disk must be covered by manifest files and checksums entries",
    "bundle validation checks manifest, source AST, JSON object shapes, flow[], and live-verification drift",
    "Refactor and parent-directory escapes are blocked"
  ],
  "forbidden_posture": [
    "creating root artifacts/",
    "creating root .artifacts/",
    "depending on AxiomSettings",
    "returning absolute machine paths in bundle manifests"
  ]
}
```
## repo.make-ast.reference-rewrite-and-role-classification

```json strict-policy
{
  "anchor": "repo.make-ast.reference-rewrite-and-role-classification",
  "rule": "AST reference utilities collect Make expression targets, rewrite node IDs only in Make-owned bindings, and classify coarse module roles without mutating payload semantics.",
  "implementation_tool": "src/blueprints/ast/references.py",
  "required_posture": [
    "template references are collected only from expression-capable payload fields",
    "root metadata examples and note content are documentation, not executable references",
    "note moduleIds are Make-owned bindings and may be collected or rewritten",
    "malformed or non-positive note moduleIds are shape errors, not unknown executable references",
    "designer moduleId and stepId scalar bindings must be strings or integers before collection or rewrite",
    "business fields named moduleId or stepId inside mapper payloads are not rewritten",
    "rewritten node ID replacements preserve string identity when integer conversion would change the replacement",
    "webhook response modules are write actions, not triggers"
  ],
  "forbidden_posture": [
    "rewriting arbitrary scalar IDs in business payloads",
    "treating documentation examples as executable Make references",
    "using token guesses to override explicit catalog module kinds"
  ]
}
```
## repo.make-ast.wrapper-aliases-require-evidence

```json strict-policy
{
  "anchor": "repo.make-ast.wrapper-aliases-require-evidence",
  "rule": "Module-scoped output wrapper aliases are allowed only when backed by real export evidence and deterministic tests.",
  "required_posture": [
    "aliases are scoped to the module or export shape that proved them",
    "aliases do not convert a wrapper into an arbitrary dynamic object",
    "dynamic children are allowed only when the source schema already declares dynamic children"
  ],
  "forbidden_posture": [
    "using wrapper aliases as a generic schema escape hatch",
    "accepting output aliases from prompts or examples alone",
    "dropping the raw exported wrapper after alias normalization"
  ]
}
```
## Rationale

This ADR preserves the accepted repository decision while moving the Pancakes documentation canon
from numbered ADR records to flat, unnumbered common Markdown ADRs.

## Consequences

- Blueprint parsing now has a typed AST surface before parser, validator, and
renderer work continues.
- Future blueprint parsing and module registry work can use source traces and
raw-spec bindings without inventing module truth.
- Unknown Make export fields are retained for future lossless rendering work.
- Export-local metadata, notes, error-handler control flow, and wrapper aliases
stay governed by evidence instead of ad hoc parser behavior.

## Validation

- The migrated ADR must be readable as normal Markdown.
- The migrated filename must be flat, unnumbered, lowercase, and descriptive under `docs/adr/`.
- Repository validation or focused documentation checks must report any remaining blockers.

## Related Material

- Former ADR ID: `001044`.
- Decision ID: `repo.make-ast.contract-policy`.
- Previous authority level: `policy`.
- Previous numeric filename was removed during the common Markdown ADR migration.

<details>
<summary>Former metadata retained during migration</summary>

```yaml
alwaysApply: true
adr_id: '001044'
decision_id: 'repo.make-ast.contract-policy'
title: 'Make AST Contract Policy'
status: 'ACTIVE'
authority_level: 'policy'
decision_type:
  - architecture
  - runtime
  - testing
scope: 'repository/make-ast'
applies_to:
  - src/blueprints/ast/**/*
  - tests/blueprints/ast/blueprint_ast_contract.py
  - tests/blueprints/fixtures/make_ast/**/*
  - docs/bibliography/make.com.md
applies_when:
  - make_blueprint_json_is_parsed
  - make_ast_nodes_are_traversed
profiles:
  - base
  - make
supersedes: []
superseded_by: []
depends_on:
  - '000010'
  - '000016'
  - '000017'
  - '001033'
  - '001034'
  - '001042'
source_material:
  - path: 'Refactor/make/adr/0007-make-blueprint-ast-contract-and-family-doctrine.md'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/root-material/forge_make_ast_runtime_intelligence_map.md'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/root-material/make_render_policy.json'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/src/forge/blueprint_assembler.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/src/forge/make_ast.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/tests/unit/test_make_ast_contract.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/src/forge/make_ast_semantics.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/tests/unit/test_make_ast_semantics.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/src/forge/make_ast_compiler.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/tests/unit/test_make_ast_compiler.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/src/forge/make_blueprint_artifacts.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/tests/unit/test_make_blueprint_artifacts.py'
    usage: source reference
    copied_verbatim: false
derived_artifacts:
  - src/blueprints/ast/**/*
  - tests/blueprints/ast/blueprint_ast_contract.py
  - tests/blueprints/fixtures/make_ast/**/*
bibliography_refs:
  - 'https://developers.make.com/'
traceability_anchors:
  - repo.make-ast.root-scenario-flow-metadata-contract
  - repo.make-ast.node-categories-and-source-trace
  - repo.make-ast.route-filter-condition-normalization
  - repo.make-ast.unknown-fields-preserved
  - repo.make-ast.traversal-contract
  - repo.make-ast.semantic-surface-ssot
  - repo.make-ast.catalog-backed-assembly
  - repo.make-ast.delta-reporting
  - repo.make-ast.local-evidence-reporting
  - repo.make-ast.blueprint-bundle-persistence
  - repo.make-ast.reference-rewrite-and-role-classification
  - repo.make-ast.export-local-evidence-and-control-flow
  - repo.make-ast.wrapper-aliases-require-evidence
non_goals:
  - implement final blueprint rendering in this round
  - contact live Make services
  - copy Make source code
  - rebuild graph/RAG, TigerGraph, Nerve, generic dataset, Notion, Life Engine, or backup scope
```
</details>
