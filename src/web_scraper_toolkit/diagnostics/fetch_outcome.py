# ./src/web_scraper_toolkit/diagnostics/fetch_outcome.py
"""
Normalize smart-fetch attempt results so browser orchestration can choose the truthful final outcome.
Run: imported by Playwright smart-fetch orchestration and regression tests.
Inputs: per-attempt content/url/status tuples plus optional metadata dictionaries.
Outputs: FetchAttemptOutcome objects and deterministic primary-vs-fallback selection.
Side effects: none.
Operational notes: explicitly treats 200-with-empty-content as a failure candidate, not a success.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .challenge_evidence import ChallengeEvidence, evaluate_page_evidence


@dataclass(frozen=True)
class FetchAttemptOutcome:
    content: Optional[str]
    content_length: int
    status: Optional[int]
    final_url: str
    block_reason: str
    blocked: bool
    metadata: Dict[str, Any] = field(default_factory=dict)
    attempt_name: str = ""
    evidence: ChallengeEvidence = field(
        default_factory=lambda: evaluate_page_evidence(
            status=None, final_url="", content=""
        )
    )

    @property
    def has_content(self) -> bool:
        return self.content_length > 0


def normalize_fetch_attempt(
    *,
    content: Optional[str],
    final_url: str,
    status: Optional[int],
    metadata: Optional[Dict[str, Any]] = None,
    attempt_name: str = "",
) -> FetchAttemptOutcome:
    normalized_content = content or ""
    evidence = evaluate_page_evidence(
        status=status,
        final_url=final_url,
        content=normalized_content,
    )
    payload = dict(metadata or {})
    if attempt_name:
        payload.setdefault("attempt_name", attempt_name)
    payload.setdefault(
        "attempt_profile", attempt_name or payload.get("attempt_profile", "")
    )
    payload["status"] = status
    payload["final_url"] = final_url
    payload["blocked_reason"] = evidence.block_reason
    payload["content_length"] = len(normalized_content)
    payload["likely_real_page"] = evidence.likely_real_page
    payload["challenge_detected"] = evidence.challenge_detected
    blocked = bool(
        evidence.challenge_detected
        or status is None
        or status in {403, 429, 503}
        or len(normalized_content) == 0
    )
    payload["blocked"] = blocked
    return FetchAttemptOutcome(
        content=content,
        content_length=len(normalized_content),
        status=status,
        final_url=final_url,
        block_reason=evidence.block_reason,
        blocked=blocked,
        metadata=payload,
        attempt_name=attempt_name or str(payload.get("attempt_profile", "") or ""),
        evidence=evidence,
    )


def _ranking_tuple(outcome: FetchAttemptOutcome) -> tuple[int, int, int, int, int, int]:
    return (
        int(
            not outcome.blocked
            and outcome.has_content
            and outcome.evidence.likely_real_page
        ),
        int(not outcome.blocked and outcome.has_content),
        int(outcome.has_content),
        int(not outcome.blocked),
        int(outcome.status == 200),
        outcome.content_length,
    )


def select_preferred_outcome(
    primary: FetchAttemptOutcome,
    fallback: FetchAttemptOutcome,
) -> FetchAttemptOutcome:
    if _ranking_tuple(fallback) > _ranking_tuple(primary):
        return fallback
    return primary
