# ./src/web_scraper_toolkit/diagnostics/fixtures.py
"""
Sanitized fixture helpers for deterministic challenge-diagnostic replay and regression testing.
Run: imported by diagnostics scripts, tests, and wrapper layers.
Inputs: live HTML snapshots, headers, cookie/event summaries, and expected evidence metadata.
Outputs: ChallengeFixture models plus JSON fixture files safe to commit.
Side effects: writes JSON files only when fixture recording is explicitly requested.
Operational notes: raw cookie values and volatile challenge tokens are redacted before persistence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .challenge_evidence import ChallengeEvidence, evaluate_page_evidence

_ALLOWLIST_HEADERS = {
    "content-type",
    "server",
    "cf-ray",
    "cf-cache-status",
    "x-frame-options",
    "content-security-policy",
    "cache-control",
    "location",
}

_OPAQUE_QUERY_KEYS = {"__cf_chl_rt_tk", "__cf_chl_f_tk", "token", "sig", "signature"}


@dataclass(frozen=True)
class ChallengeFixture:
    fixture_name: str
    captured_utc: str
    tool_source: str
    status: Optional[int]
    url: str
    title: str
    html: str
    headers: Dict[str, str] = field(default_factory=dict)
    cookie_summary: List[Dict[str, Any]] = field(default_factory=list)
    event_summary: List[Dict[str, Any]] = field(default_factory=list)
    expected_evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _sanitize_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url)
    sanitized_query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in _OPAQUE_QUERY_KEYS:
            sanitized_query.append((key, "<redacted>"))
        else:
            sanitized_query.append((key, value))
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(sanitized_query),
            parts.fragment,
        )
    )


def _sanitize_html(html: str) -> str:
    sanitized = html or ""
    sanitized = re.sub(
        r"(__cf_chl_[^=\s\"']+)=([^&\s\"']+)",
        r"\1=<redacted>",
        sanitized,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(
        r"([?&](?:token|sig|signature)=)([^&\s\"']+)",
        r"\1<redacted>",
        sanitized,
        flags=re.IGNORECASE,
    )
    return sanitized


def _sanitize_headers(headers: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    if not headers:
        return {}
    sanitized: Dict[str, str] = {}
    for key, value in headers.items():
        lowered = str(key).lower()
        if lowered not in _ALLOWLIST_HEADERS:
            continue
        sanitized[lowered] = str(value)
    return sanitized


def _sanitize_cookie_summary(
    cookies: Optional[Iterable[Mapping[str, Any]]],
) -> List[Dict[str, Any]]:
    summary: List[Dict[str, Any]] = []
    for cookie in cookies or []:
        summary.append(
            {
                "name": str(cookie.get("name", "")),
                "domain": str(cookie.get("domain", "")),
                "path": str(cookie.get("path", "")),
                "sameSite": str(cookie.get("sameSite", "")),
                "secure": bool(cookie.get("secure", False)),
                "value_length": len(str(cookie.get("value", ""))),
            }
        )
    return summary


def _sanitize_event_summary(
    events: Optional[Iterable[Mapping[str, Any]]],
) -> List[Dict[str, Any]]:
    sanitized: List[Dict[str, Any]] = []
    for event in events or []:
        sanitized_event: Dict[str, Any] = {}
        for key, value in event.items():
            if key in {"headers", "request_headers", "response_headers"} and isinstance(
                value, Mapping
            ):
                sanitized_event[key] = _sanitize_headers(value)
            elif key == "url":
                sanitized_event[key] = _sanitize_url(str(value))
            elif key in {"response_body_preview", "body_preview"}:
                sanitized_event[key] = str(value)[:500]
            else:
                sanitized_event[key] = value
        sanitized.append(sanitized_event)
    return sanitized


def _coerce_expected_evidence(
    expected_evidence: Optional[Mapping[str, Any]],
    evidence: ChallengeEvidence,
) -> Dict[str, Any]:
    payload = dict(expected_evidence or {})
    payload.setdefault("likely_real_page", evidence.likely_real_page)
    payload.setdefault("challenge_detected", evidence.challenge_detected)
    payload.setdefault("deny_page_detected", evidence.deny_page_detected)
    payload.setdefault("marker_soft_signal_only", evidence.marker_soft_signal_only)
    payload.setdefault("content_quality", evidence.content_quality)
    return payload


def record_sanitized_fixture(
    *,
    path: str | Path,
    fixture_name: str,
    tool_source: str,
    status: Optional[int],
    url: str,
    title: str,
    html: str,
    headers: Optional[Mapping[str, Any]] = None,
    cookies: Optional[Iterable[Mapping[str, Any]]] = None,
    events: Optional[Iterable[Mapping[str, Any]]] = None,
    expected_evidence: Optional[Mapping[str, Any]] = None,
) -> Path:
    sanitized_url = _sanitize_url(url)
    sanitized_html = _sanitize_html(html)
    evidence = evaluate_page_evidence(
        status=status,
        final_url=sanitized_url,
        content=sanitized_html,
        title_hint=title,
    )
    fixture = ChallengeFixture(
        fixture_name=fixture_name,
        captured_utc=datetime.now(timezone.utc).isoformat(),
        tool_source=tool_source,
        status=status,
        url=sanitized_url,
        title=title,
        html=sanitized_html,
        headers=_sanitize_headers(headers),
        cookie_summary=_sanitize_cookie_summary(cookies),
        event_summary=_sanitize_event_summary(events),
        expected_evidence=_coerce_expected_evidence(expected_evidence, evidence),
    )
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(fixture.to_dict(), indent=2), encoding="utf-8")
    return output_path


def load_fixture(path: str | Path) -> ChallengeFixture:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return ChallengeFixture(**payload)


def replay_fixture(path: str | Path) -> Dict[str, Any]:
    fixture = load_fixture(path)
    evidence = evaluate_page_evidence(
        status=fixture.status,
        final_url=fixture.url,
        content=fixture.html,
        title_hint=fixture.title,
    )
    return {
        "fixture": fixture.to_dict(),
        "evidence": evidence.to_dict(),
    }
