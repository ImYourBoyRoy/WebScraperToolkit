# API Stability & Deprecation Policy

## Stability baseline

The following are considered public/stable surfaces:
- CLI entrypoint: `web-scraper`
- MCP entrypoint: `web-scraper-server`
- Python package root exports from `web_scraper_toolkit.__init__`
- Diagnostic mode names: `toolkit_route`, `challenge_matrix`, `bot_check`, `browser_info`

## Versioning expectations

- **Patch**: bug fixes only, no breaking behavior changes.
- **Minor**: additive features and new flags/fields.
- **Major**: any removal or incompatible contract change.

## Deprecation process (for future changes)

1. Add replacement path in the same minor release.
2. Mark deprecated symbols/flags in docs and changelog.
3. Keep deprecations for at least one full minor cycle.
4. Remove only in the next major release.

## Current policy decision

Legacy `scripts/test_*.py` diagnostic shims were intentionally removed in favor of canonical
`scripts/diag_*.py` tooling. This repository now treats `diag_*` names as the only supported script paths.

