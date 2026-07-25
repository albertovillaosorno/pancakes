# Lead Routing Portfolio Notes

## Public title suggestion

- `Make Lead Routing Portfolio Demo`

## Description

Offline portfolio demonstration of a sanitized lead-routing workflow using a tracked
Make scenario JSON draft:

- fake webhook intake
- required-field checks (`email`, `company`, `source`, `score`)
- routing into two qualified branches
- two fake Data Store destinations:
  - `{{runtime.datastore.qualified_leads}}`
  - `{{runtime.datastore.incomplete_leads}}`

## Screenshot ideas

- `make-demo-canvas.png`: compact topology showing webhook trigger, routing filters, and two datastore branches.
- `make-demo-input-output-table.png`: sample input rows and their expected branch outcomes.
- `make-demo-handoff-sample.pdf`: one-page handoff summary with runtime placeholders, validation summary, and next actions.

## Recommended assets

- `make-demo-canvas.png`
- `make-demo-input-output-table.png`
- `make-demo-handoff-sample.pdf`

## Notes

- No real webhook URL, API key, token, or account identifiers are included.
- No claims, client names, or private account data are represented.
- Runtime setup is required before any live publish or test execution.
