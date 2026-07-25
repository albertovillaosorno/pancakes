# Enterprise Handoff Readiness Policy

Status: accepted

## Decision

Pancakes must remain agent-native and deterministically validated, but it must also be
understandable to an external technical owner without weakening the strict workflow that makes the
engine useful.

The repository should not become conventional by lowering gates or hiding the agent workflow. It
should become explainable: each critical product surface must state what it owns, how it is
validated, how a human reviews it, and how an agent may safely change it.

Repository-visible handoff material must be product-safe. It may describe the engine, validation
gates, bootstrap flow, rule-authoring flow, waiver process, and audit path. It must not include
private operator control-plane doctrine, private commercial planning, transaction planning,
personal financial planning, or personal operator workflow.

## Required Handoff Material

- Architecture overview for the IR-centered engine and Make adapter.
- Validation gate profile and command entry points.
- Fresh-clone bootstrap path.
- Rule authoring guide.
- Safe gate-waiver procedure.
- Product-critical gate inventory.
- Reusable versus product-specific tool boundary.
- Agent operation guide for repository-local work.
- Human audit guide for reviewing agent-authored changes.

## Required Framing

The safe product summary is:

```text
Human-governed, agent-executed, deterministically validated.
```
Use this as a repository handoff principle, not as a private sale slogan.

## Readiness Surfaces

Repository handoff material must keep readiness surfaces separate:

- Make import readiness: whether a local Make-native artifact can be generated and imported.
- Client handoff readiness: whether the artifact is ready for a client or operator to receive.
- Native parity readiness: whether generated and re-exported Make structure match.
- Runtime setup status: whether local placeholders still require operator configuration.
- Zero-trace status: whether a rendered artifact was checked for private or local traces.

Missing module or connection notes are client handoff blockers. They are not Make import blockers
under import-test readiness. If client handoff blocks before artifact rendering, zero trace is
`not_evaluated`, not failed or passed.

Compact MCP and Web-facing readiness output must show surface-specific statuses rather than one
global blocked label. An import-ready but handoff-blocked scenario should read as Make import ready,
client handoff invalid or blocked, runtime setup required, scenario tests passed or not configured,
and zero trace passed or not evaluated depending on whether an artifact was rendered.

## Non-Goals

- Do not lower validation strictness to make the repository feel familiar.
- Do not remove deterministic gates without a replacement policy and tests.
- Do not copy private operator skills, TODOs, business strategy, or command
doctrine into the repository.
- Do not hide agent-native workflows when they are part of the technical value.
- Do not describe the repository through private transaction strategy.

## Completion Gate

The repository is handoff-ready only when its architecture, bootstrap, validation commands,
rule-authoring flow, waiver policy, agent operation, and human audit path are documented in
product-safe files and covered by fast guard tests.
