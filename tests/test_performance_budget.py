# ./tests/test_performance_budget.py
"""
Performance budget checks for deterministic utility hot paths.
Run: pytest tests/test_performance_budget.py -q
Inputs: local CPU runtime and pure utility function calls.
Outputs: pass/fail assertions against simple elapsed-time thresholds.
Side effects: none.
Operational notes: intentionally excludes browser/network operations; acts as regression tripwire.
"""

from __future__ import annotations

import time

import pytest

from web_scraper_toolkit.browser.domain_identity import host_lookup_candidates
from web_scraper_toolkit.core.script_diagnostics import split_cli_args


@pytest.mark.benchmark
def test_split_cli_args_budget() -> None:
    start = time.perf_counter()
    for _ in range(20_000):
        split_cli_args('--flag "value with spaces" --x=1 --y "hello world"')
    elapsed = time.perf_counter() - start
    assert elapsed < 2.5, f"split_cli_args regression: elapsed={elapsed:.4f}s"


@pytest.mark.benchmark
def test_host_lookup_candidates_budget() -> None:
    start = time.perf_counter()
    for _ in range(20_000):
        host_lookup_candidates("https://sub.example.co.uk/path?q=1")
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0, f"host_lookup_candidates regression: elapsed={elapsed:.4f}s"
