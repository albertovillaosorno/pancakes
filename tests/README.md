# Tests

The active test suite is sliced by repository surface and behavior. Root-level
test modules are not the target layout; nested `*_contract.py`, `*_spec.py`, and
`*_fitness.py` files own executable coverage.

## File Boundary

This README owns the test-tree entrypoint and discovery policy. It does not own
individual domain assertions, fixture data, or repository validation commands.

Run the full suite from the repository root:

```powershell
python -B tests/run_all.py
```

Do not treat repo-local dependency paths, direct pytest invocations, legacy
package scripts, or ignored workflow files as command authority for this
checkout.
