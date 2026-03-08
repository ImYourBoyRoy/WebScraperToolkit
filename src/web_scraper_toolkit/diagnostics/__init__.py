# ./src/web_scraper_toolkit/diagnostics/__init__.py
"""
Shared diagnostic helpers for challenge classification, fetch arbitration, and fixture replay.
Run: imported by browser handlers, scripts, tests, and MCP wrappers; not a direct CLI entry point.
Inputs: HTML snapshots, URLs, statuses, cookies, headers, and script/runtime telemetry.
Outputs: typed evidence models, normalized fetch outcomes, and sanitized fixture payloads.
Side effects: fixture helpers can write JSON reports when explicitly requested.
Operational notes: keep these helpers pure and deterministic so live anti-bot behavior can be debugged offline.
"""

from .challenge_evidence import (
    ChallengeEvidence,
    evaluate_page_evidence,
    extract_visible_text,
)
from .fetch_outcome import (
    FetchAttemptOutcome,
    normalize_fetch_attempt,
    select_preferred_outcome,
)
from .fixtures import (
    ChallengeFixture,
    load_fixture,
    record_sanitized_fixture,
    replay_fixture,
)

__all__ = [
    "ChallengeEvidence",
    "ChallengeFixture",
    "FetchAttemptOutcome",
    "evaluate_page_evidence",
    "extract_visible_text",
    "load_fixture",
    "normalize_fetch_attempt",
    "record_sanitized_fixture",
    "replay_fixture",
    "select_preferred_outcome",
]
