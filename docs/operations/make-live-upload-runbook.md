# Make Live Upload Runbook

This runbook captures the safe live-upload path for a Pancakes-generated Make package. It
intentionally uses placeholders for live IDs and credential selections. Do not paste API keys,
OAuth tokens, webhook URLs, connection metadata, or customer payload values into commands, logs, or
review notes.

## Local Package

1. Stage or import a draft through the local staged-draft flow.
2. Create the local project from the staged draft.
3. Render the Make package with live-preflight output enabled.

```text
project.draft.stage(dry_run=true)
project.draft.stage(dry_run=false)
project.create(staged_draft_path=<local staged draft path>, dry_run=false)
project.make(
  project_id=<project id>,
  action=package,
  profile=live_preflight,
  include_blueprint_json=true,
  dry_run=false
)
```

Expected local gates:

- `package_status: ready`
- `live_preflight_status: ready`
- `zero_trace_status: passed`
- `leak_count: 0`
- `make_mcp_live_requirements_status: available`
- every importable module has `metadata.designer.x` and `metadata.designer.y`
- route filters are attached to the first module inside each Make route, not to the route wrapper
- `artifacts/make-live/datastructure.json`, `datastore.json`, `webhook.json`, and
  `upload-plan.json` exist as first-class files
- Make-native scenario notes contain visible `PDF index: NOTE-...` anchors and use only the
  supported Make note color palette

## One-Command Live Upload

The Make API token is runtime-only input. Do not store it in SQLite, local storage, generated
artifacts, command logs, TODO files, or handoff notes. Prefer a process environment variable or
stdin supplied by the web session.

```powershell
$env:MAKE_API_TOKEN = "<runtime token>"
python -m languages.make.live_upload `
  --project-folder <project artifact folder> `
  --team-id <team id> `
  --organization-id <organization id> `
  --connection runtime.connection.slack_ops=<make connection id> `
  --connection runtime.connection.google_email_ops=<make connection id> `
  --runtime-value runtime.slack.channel.ops_alerts=<channel id> `
  --apply
Remove-Item Env:\MAKE_API_TOKEN
```

The upload command must apply the dependency hierarchy:

```text
Data Structures -> Data Stores -> Webhooks -> bound inactive/on-demand scenario
  -> scenario notes batch -> export compare
```

The customer should not see Make prompts to create Data Stores, Data Structures, or webhooks. Those
resources are created by the upload command and their returned IDs are patched into the blueprint
before scenario creation. The only customer-owned prerequisites are app connections and app-specific
runtime choices such as a Slack channel.

Blueprint `metadata.notes` is portable export evidence, and generated blueprints also mirror the
same payload into `metadata.designer.notes` for Make editor compatibility. The live editor renders
persisted notes from the scenario notes service, so after creating the inactive scenario, the
uploader must mirror every Make-native note through
`POST /api/v2/scenarios/<scenario id>/notes/batch` with the same `moduleIds`, `content`,
`isFilterNote`, and canonical `metadata.color` values. The note body must show the PDF/manual
anchor, for example `PDF index: NOTE-MOD-3`, so the Make canvas and generated technical PDF point
at the same item.

## Make MCP Upload Evidence

Validate the exact `blueprint_artifact_json.scenario` before creating anything live.

```text
make._validate_blueprint_schema(blueprint=<scenario blueprint>)
```

Create runtime resources before scenario creation.

```text
make._data_structures_create(
  teamId=<team id>,
  name=<data structure name>,
  strict=true,
  spec=<Make parameter spec>
)

make._data_stores_create(
  teamId=<team id>,
  name=<data store name>,
  datastructureId=<created data structure id>,
  maxSizeMB=<small bounded size>
)

make._hook_config_get(typeName="gateway-webhook", format="instructions")
make._validate_hook_configuration(
  organizationId=<organization id>,
  teamId=<team id>,
  typeName="gateway-webhook",
  values={"headers": false, "method": false, "stringify": false},
  strict=true
)
make._hooks_create(
  teamId=<team id>,
  name=<webhook name>,
  typeName="gateway-webhook",
  data={"headers": false, "method": false, "stringify": false}
)
```

Bind only the created resource identifiers into the blueprint:

```text
flow[0].parameters.hook = <created hook id>
datastore:AddRecord.parameters.datastore = <created data store id>
```

Provider connections must be valid Make connection IDs supplied by the client web session. If a
connection is missing or returns reauthorization errors, do not fake it. The onboarding checklist
must tell the client which app connections are required before upload.

```text
make._connections_list(teamId=<team id>, type=["slack2", "slack3"])
make._connections_list(teamId=<team id>, type=["google-email"])
```

Create and export the scenario:

```text
make._scenarios_create(
  teamId=<team id>,
  confirmed=true,
  scheduling={"type": "on-demand"},
  blueprint=<bound scenario blueprint>
)

make._scenarios_get(scenarioId=<created scenario id>)
```

Manual browser review:

```text
https://us2.make.com/<team id>/scenarios/<scenario id>/edit
```

Check that the scenario is inactive, the webhook trigger is present, router routes are present,
route filters are attached to the first module in each route, and data-store modules point to the
intended data store. The designer must show readable left-to-right module spacing, not a stack of
overlapping modules. Do not run provider-send modules until valid provider connections are selected.

## Optional Cleanup

Clean scratch resources only after the exported scenario has been compared.

```text
make._scenarios_delete(scenarioId=<created scenario id>)
make._hooks_delete(hookId=<created hook id>)
make._data_stores_delete(dataStoreId=<created data store id>)
make._data_structures_delete(dataStructureId=<created data structure id>)
```
