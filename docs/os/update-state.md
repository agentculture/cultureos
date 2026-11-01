# Update state file

The CultureOS update agent writes `/var/lib/cultureos/update-state.json` after
every update attempt. `cultureos os status` reads it (path override:
`CULTUREOS_UPDATE_STATE`). The file is a single JSON object, replaced
atomically (write a temp file, then rename). A missing file means no update has
been attempted and is reported as outcome `none`.

## Fields

| Field | Type | Required | Meaning |
|-------|------|----------|---------|
| `schema_version` | integer | yes | Currently `1`. |
| `outcome` | string | yes | One of `applied`, `rolled-back`, `failed`, `none`. |
| `timestamp` | string | yes, unless outcome is `none` | UTC ISO-8601 time the attempt finished, e.g. `2026-11-01T12:00:00Z`. |
| `deployed_version` | string or null | no | Version of the deployment the attempt targeted. |
| `deployed_commit` | string or null | no | OSTree commit checksum the attempt targeted. |
| `previous_commit` | string or null | no | Commit that was booted before the attempt. |
| `reason` | string or null | no | Human-readable cause; expected for `rolled-back` and `failed`. |

## Outcome semantics

- `applied`: the new deployment booted and passed health checks. Healthy.
- `none`: no update attempted yet. Healthy.
- `rolled-back`: the new deployment was staged or booted but failed health
  checks, and the system returned to `previous_commit`. Degraded.
- `failed`: the update did not complete (fetch, verify or deploy error) and no
  new deployment is booted. Degraded.

## Consumer behavior

`cultureos os status` exits 0 for `applied` and `none`, 1 for `rolled-back` and
`failed`, and 2 when the file exists but is not valid JSON or its `outcome` is
missing or not one of the four values.

## Example

```json
{
  "schema_version": 1,
  "outcome": "rolled-back",
  "timestamp": "2026-11-01T12:00:00Z",
  "deployed_version": "0.4.0",
  "deployed_commit": "3f2a9c1d",
  "previous_commit": "9ab01e22",
  "reason": "health check failed: culture daemon did not start"
}
```
