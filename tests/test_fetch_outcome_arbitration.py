# ./tests/test_fetch_outcome_arbitration.py
"""
Validate fetch-attempt normalization and arbitration so empty 200 responses never look successful.
Run: `python -m pytest tests/test_fetch_outcome_arbitration.py -q`.
Inputs: deterministic in-memory attempt tuples and metadata dictionaries.
Outputs: assertions on blocked-state normalization and primary-vs-fallback selection.
Side effects: none.
Operational notes: protects smart_fetch truthfulness without needing live anti-bot targets.
"""

from __future__ import annotations

from web_scraper_toolkit.diagnostics import (
    normalize_fetch_attempt,
    select_preferred_outcome,
)


def test_empty_200_is_blocked_not_success() -> None:
    outcome = normalize_fetch_attempt(
        content="",
        final_url="https://example.com",
        status=200,
        metadata={"attempt_profile": "baseline_headless"},
        attempt_name="baseline_headless",
    )
    assert outcome.blocked is True
    assert outcome.content_length == 0
    assert outcome.evidence.progressed is False


def test_fallback_real_page_beats_primary_empty_200() -> None:
    primary = normalize_fetch_attempt(
        content="",
        final_url="https://example.com",
        status=200,
        metadata={"attempt_profile": "baseline_headless"},
        attempt_name="baseline_headless",
    )
    fallback = normalize_fetch_attempt(
        content="<html><main><article>" + ("word " * 400) + "</article></main></html>",
        final_url="https://example.com/docs",
        status=200,
        metadata={"attempt_profile": "native_channel_chrome"},
        attempt_name="native_channel_chrome",
    )
    selected = select_preferred_outcome(primary, fallback)
    assert selected.attempt_name == "native_channel_chrome"
    assert selected.evidence.likely_real_page is True


def test_primary_real_page_beats_blocked_fallback() -> None:
    primary = normalize_fetch_attempt(
        content="<html><main><article>" + ("word " * 400) + "</article></main></html>",
        final_url="https://example.com/docs",
        status=200,
        metadata={"attempt_profile": "baseline_headless"},
        attempt_name="baseline_headless",
    )
    fallback = normalize_fetch_attempt(
        content="Just a moment",
        final_url="https://example.com/challenge",
        status=403,
        metadata={"attempt_profile": "native_channel_chrome"},
        attempt_name="native_channel_chrome",
    )
    selected = select_preferred_outcome(primary, fallback)
    assert selected.attempt_name == "baseline_headless"
    assert selected.evidence.likely_real_page is True
