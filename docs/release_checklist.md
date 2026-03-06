# Production Release Checklist

Use this checklist before tagging `v*` releases.

## Quality gates
- [ ] `ruff format --check .`
- [ ] `ruff check src`
- [ ] `mypy` (configured target set)
- [ ] `pytest -q -m "not integration"`
- [ ] `python -m build`
- [ ] `python -m twine check dist/*`

## Security gates
- [ ] `python -m bandit -q -r src/web_scraper_toolkit -lll -iii`
- [ ] `python -m pip_audit -r .audit-requirements.txt --strict`
- [ ] Secret scan passes (Gitleaks in CI)

## Hygiene
- [ ] `python scripts/clean_workspace.py --dry-run`
- [ ] no unintended generated artifacts in git status
- [ ] docs updated for any new flags/behavior

## Release controls
- [ ] `pyproject.toml` version matches release tag (`vX.Y.Z`)
- [ ] changelog/release notes summarize user-facing changes
- [ ] publish workflow passes strict tag-version verification

