# Operator Command Vocabulary And Diff Blueprint Policy

This ADR records the product-facing command vocabulary expected by legacy Pancakes Golden fixtures.

The `repo.operator-commands.command-registry` contract recognizes the local Golden command surface:

```json
{
  "name": "Golden",
  "purpose": "Run deterministic local Golden comparison and batch checks for Pancakes fixtures."
}
```
The command must stay local, deterministic, and free of live service access.
