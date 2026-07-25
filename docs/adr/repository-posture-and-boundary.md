# Repository Posture and Boundary

Status: accepted

## Decision

This repository owns the Pancakes product engine: Make catalog, AST, linter, validator, MCP surface,
repair logic, and product documentation.

The repository has a proprietary private/product posture. The directory bucket recorded by the
private control-plane repository index is the authority for license and privacy posture. If copied
notes, package metadata, or stale license text disagrees with the bucket, update the conflicting
file rather than changing posture ad hoc.

## Boundaries

- Keep this repository focused on $repoId source, tests, fixtures, product documentation, and
  repo-local validation policy.
- Keep cross-repository TODO routing, private operator prompts, personal notes, business strategy,
  acquisition planning, credentials, and unrelated product policy outside this repository.
- Do not publish, deploy, push, rewrite history, or run destructive cleanup unless an explicit task
  names the allowed path and canonical command.
- Treat unknown push or deployment commands as do-not-push and do-not-deploy.
- Translate reusable private operating rules into product-safe repo ADRs before adding them here.

## Repository Notes

Generic repository workflow rules now live in private skills. Public sales/provider strategy, Upwork
material, media cross-repo planning, PDF handoff planning, and Windows service orchestration have
been moved out of this repo ADR canon.
