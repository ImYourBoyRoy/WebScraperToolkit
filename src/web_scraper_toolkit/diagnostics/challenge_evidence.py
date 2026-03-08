# ./src/web_scraper_toolkit/diagnostics/challenge_evidence.py
"""
Pure page-evidence classification helpers used by browser flows, tests, and diagnostics scripts.
Run: imported by toolkit internals and standalone diagnostics scripts.
Inputs: HTML content, URL, optional title hints, and optional HTTP status values.
Outputs: ChallengeEvidence objects describing progression, deny/challenge markers, and evidence richness.
Side effects: none.
Operational notes: visible-text extraction ignores script/style-heavy markup so deny pages cannot look real from raw HTML noise alone.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Dict, Iterable, List, Optional

from bs4 import BeautifulSoup

from ..browser._playwright_handler.constants import (
    _CF_CHALLENGE_MARKERS,
    _PX_CHALLENGE_MARKERS,
    classify_bot_block,
)

_TITLE_DENY_MARKERS = (
    "just a moment",
    "attention required",
    "access denied",
    "access to this page has been denied",
    "verify you are human",
)

_HTML_DENY_MARKERS = (
    "px-captcha",
    "captcha.js",
    "cf-challenge",
    "challenge-platform",
    "__cf_chl",
    "access to this page has been denied",
    "cf-error-details",
    "cf-im-under-attack",
)

_STRUCTURE_SIGNALS = (
    "<main",
    "<article",
    "<section",
    "<nav",
    "<footer",
    "<header",
    "<h1",
    "<h2",
    "<h3",
    "application/ld+json",
    "og:title",
    "twitter:title",
    "schema.org",
)

_VISIBLE_WORD_RE = re.compile(r"[a-zA-Z]{3,}")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", flags=re.IGNORECASE | re.DOTALL)
_CHALLENGE_URL_PATTERNS = (
    re.compile(r"__cf_chl", flags=re.IGNORECASE),
    re.compile(r"/cdn-cgi/challenge-platform", flags=re.IGNORECASE),
    re.compile(r"/captcha(?:[/?#]|$)", flags=re.IGNORECASE),
    re.compile(r"[?&](?:captcha|cf_captcha)=", flags=re.IGNORECASE),
)


@dataclass(frozen=True)
class ChallengeEvidence:
    title: str
    block_reason: str
    content_length: int
    visible_text_length: int
    visible_word_count: int
    structure_signal_count: int
    marker_hits_total: int
    marker_density: float
    px_markers_found: bool
    cf_markers_found: bool
    title_challenge: bool
    deny_page_detected: bool
    challenge_detected: bool
    likely_real_page: bool
    marker_soft_signal_only: bool
    status_is_2xx: bool
    strict_status_gate_failed: bool
    progressed: bool
    rich_content_length: bool
    content_quality: str
    reason_codes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def extract_title_from_html(html: str) -> str:
    match = _TITLE_RE.search(html or "")
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()


def extract_visible_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for element in soup(["script", "style", "noscript", "template", "svg", "canvas"]):
        element.decompose()
    if soup.head is not None:
        for element in soup.head.find_all(["style", "script", "noscript", "template"]):
            element.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def count_structure_signals(html: str) -> int:
    lowered = (html or "").lower()
    return sum(1 for signal in _STRUCTURE_SIGNALS if signal in lowered)


def _count_marker_hits(html: str, markers: Iterable[str]) -> int:
    lowered = (html or "").lower()
    return sum(lowered.count(marker) for marker in markers)


def _url_has_challenge_pattern(url: str) -> bool:
    lowered = (url or "").lower()
    return any(pattern.search(lowered) for pattern in _CHALLENGE_URL_PATTERNS)


def evaluate_page_evidence(
    *,
    status: Optional[int],
    final_url: str,
    content: str,
    title_hint: str = "",
    require_2xx_status: bool = False,
) -> ChallengeEvidence:
    html = content or ""
    title = title_hint or extract_title_from_html(html)
    title_lower = title.lower()
    visible_text = extract_visible_text(html)
    visible_text_length = len(visible_text)
    visible_word_count = len(_VISIBLE_WORD_RE.findall(visible_text))
    structure_signal_count = count_structure_signals(html)
    rich_content_length = len(html) >= 120_000
    block_reason = classify_bot_block(
        status=status,
        final_url=final_url,
        content_html=html,
    )
    px_marker_hits = _count_marker_hits(html, _PX_CHALLENGE_MARKERS)
    cf_marker_hits = _count_marker_hits(html, _CF_CHALLENGE_MARKERS)
    deny_marker_hits = _count_marker_hits(html, _HTML_DENY_MARKERS)
    marker_hits_total = px_marker_hits + cf_marker_hits + deny_marker_hits
    marker_density = marker_hits_total / max(1, len(html))
    title_challenge = any(marker in title_lower for marker in _TITLE_DENY_MARKERS)
    deny_page_detected = bool(title_challenge or deny_marker_hits > 0)
    challenge_url = _url_has_challenge_pattern(final_url)
    status_is_2xx = bool(status is not None and 200 <= int(status) < 300)
    strict_status_gate_failed = bool(require_2xx_status and not status_is_2xx)

    positive_richness = bool(
        rich_content_length or visible_word_count >= 250 or structure_signal_count >= 4
    )
    hard_negative = bool(
        (deny_page_detected and not positive_richness)
        or challenge_url
        or visible_word_count < 80
    )

    likely_real_page = bool(html.strip() and positive_richness and not hard_negative)
    marker_soft_signal_only = bool(
        likely_real_page
        and marker_hits_total > 0
        and marker_density < 0.00025
        and not title_challenge
        and not deny_page_detected
        and not challenge_url
    )

    adjusted_block_reason = block_reason
    if (
        adjusted_block_reason in {"px_challenge", "cf_challenge"}
        and marker_soft_signal_only
    ):
        adjusted_block_reason = "none"

    block_reason_requires_corroboration = bool(
        adjusted_block_reason != "none"
        and (
            not likely_real_page
            or title_challenge
            or challenge_url
            or deny_marker_hits > 0
            or (px_marker_hits + cf_marker_hits) > 0
        )
    )

    challenge_detected = bool(
        (title_challenge and not likely_real_page)
        or (challenge_url and not marker_soft_signal_only)
        or (block_reason_requires_corroboration and not marker_soft_signal_only)
        or (deny_marker_hits > 0 and not marker_soft_signal_only)
        or (
            (px_marker_hits + cf_marker_hits) > 0
            and not likely_real_page
            and not marker_soft_signal_only
        )
    )

    reason_codes: List[str] = []
    if title_challenge:
        reason_codes.append("deny_title")
    if deny_marker_hits > 0:
        reason_codes.append("deny_markup")
    if challenge_url:
        reason_codes.append("challenge_url")
    if px_marker_hits > 0:
        reason_codes.append("px_marker")
    if cf_marker_hits > 0:
        reason_codes.append("cf_marker")
    if visible_word_count < 80:
        reason_codes.append("thin_visible_text")
    if positive_richness:
        reason_codes.append("positive_content_richness")
    if marker_soft_signal_only:
        reason_codes.append("residual_soft_markers")
    if strict_status_gate_failed:
        reason_codes.append("strict_status_gate_failed")

    content_quality = "real" if likely_real_page else "thin"
    if deny_page_detected:
        content_quality = "deny"
    elif challenge_detected:
        content_quality = "challenge"
    elif not html.strip() or visible_text_length == 0:
        content_quality = "empty"

    progressed = bool(
        likely_real_page
        and not challenge_detected
        and not strict_status_gate_failed
        and (status is None or status not in {403, 429} or rich_content_length)
    )

    return ChallengeEvidence(
        title=title,
        block_reason=adjusted_block_reason,
        content_length=len(html),
        visible_text_length=visible_text_length,
        visible_word_count=visible_word_count,
        structure_signal_count=structure_signal_count,
        marker_hits_total=marker_hits_total,
        marker_density=marker_density,
        px_markers_found=px_marker_hits > 0,
        cf_markers_found=cf_marker_hits > 0,
        title_challenge=title_challenge,
        deny_page_detected=deny_page_detected,
        challenge_detected=challenge_detected,
        likely_real_page=likely_real_page,
        marker_soft_signal_only=marker_soft_signal_only,
        status_is_2xx=status_is_2xx,
        strict_status_gate_failed=strict_status_gate_failed,
        progressed=progressed,
        rich_content_length=rich_content_length,
        content_quality=content_quality,
        reason_codes=reason_codes,
    )
