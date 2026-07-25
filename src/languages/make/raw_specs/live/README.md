# Live Raw Specs

This subpackage owns the explicit live Make API adapter for raw-spec refreshes.

## File Boundary

- Owns: live Make API request construction, response shape guards, scraper-local
  live errors, retry timing hooks, and `MakeRawSpecSource` adaptation.
- Must not: write raw-spec files, build manifests, own credential loading,
  bypass live-readiness checks, mutate Make accounts, or run during default tests.
- Inputs: explicit live scraper configuration, injected HTTP transports,
  organization ids, optional search limits, and Make API JSON responses.
- Outputs: app-version targets, raw app spec payloads, scraper-local live errors,
  and normalized JSON objects for the parent raw-spec refresh boundary.
- Split when: another provider, transport implementation, or credentialed
  service workflow needs an independently reviewed live adapter boundary.
