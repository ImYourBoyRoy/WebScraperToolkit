# Configuration & Profile Schema Contract

This document defines the **versioned stability contract** for runtime config and host-profile persistence.

## 1) Runtime config schema (effective merge result)

Resolution precedence remains:
1. Explicit CLI/MCP args
2. `WST_*` environment variables
3. `settings.local.cfg` / `settings.cfg`
4. `config.json`
5. in-code defaults

### Contracted keys (selected high-impact)
- `browser_type`: `chromium | firefox | webkit | chrome | msedge`
- `headless`: `bool`
- `native_fallback_policy`: `off | on_blocked | always`
- `native_browser_channels`: comma list / array from `{chrome, msedge, chromium}`
- `native_context_mode`: `incognito | persistent`
- `native_profile_dir`: `str`
- `host_profiles_enabled`: `bool`
- `host_profiles_read_only`: `bool`
- `host_learning_enabled`: `bool`
- `host_learning_promotion_threshold`: `int >= 1`

**Compatibility rule:** key removals require a major version bump; renames require additive migration windows.

## 2) Host profile store schema (`host_profiles.json`)

Current file-level schema:

```json
{
  "version": 1,
  "defaults": {
    "fallback_policy": "on_blocked",
    "session_policy": "incognito"
  },
  "hosts": {
    "example.com": {
      "active": {
        "routing": {
          "native_fallback_policy": "on_blocked",
          "native_browser_channels": ["chrome", "msedge", "chromium"],
          "allow_headed_retry": false,
          "serp_strategy": "none",
          "serp_retry_policy": "none",
          "serp_retry_backoff_seconds": 12.0
        },
        "updated_utc": "2026-01-01T00:00:00+00:00"
      }
    }
  }
}
```

**Compatibility rule:** `version` is authoritative. Reader/writer must preserve unknown keys and avoid destructive rewrites.

## 3) Forward migration rule

- Future schema upgrades must keep `version` monotonic (`1 -> 2 -> 3`).
- Runtime loads must support prior versions with in-memory normalization.
- Migration writes must be atomic (temp file + replace).

## 4) Audit compaction logic
- `host_profiles.json` entries are resolved by `base_url` to prevent unbounded growth from unique subpaths/queries.
- Audit events per host are capped at `10` (`MAX_AUDIT_EVENTS`).
- Per-audit metadata strips non-essential high-cardinality flags (like `run_id` and `final_url`).
- Redundant routing blocks in audit arrays are collapsed to `"inherited"` if they match the active routing strategy, reducing JSON boilerplate.

