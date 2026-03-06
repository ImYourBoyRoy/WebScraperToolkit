# ./src/web_scraper_toolkit/browser/domain_identity.py
"""
Resolve host identity keys used by host-routing profile matching and learning.
Run: imported by browser host profile storage and routing resolution paths.
Inputs: URL/host strings from fetch requests and host-profile API operations.
Outputs: normalized exact host, registrable domain (eTLD+1), and lookup order.
Side effects: none; pure normalization helpers.
Operational notes: uses offline-safe tldextract parsing so domain matching stays
deterministic without network lookups.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List, Tuple
from urllib.parse import urlparse

import tldextract


@lru_cache(maxsize=1)
def _get_tld_extractor() -> tldextract.TLDExtract:
    """Return an offline-safe tldextract parser instance."""
    return tldextract.TLDExtract(suffix_list_urls=())


def normalize_host(value: str) -> str:
    """Normalize host-or-url input into a stable lowercase host key."""
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def registrable_domain(value: str) -> str:
    """
    Compute registrable domain (eTLD+1) for a host/url.

    Examples:
      - app.example.com -> example.com
      - app.example.co.uk -> example.co.uk
    """
    host = normalize_host(value)
    if not host:
        return ""
    extracted = _get_tld_extractor()(host)
    domain = str(extracted.domain or "").strip().lower()
    suffix = str(extracted.suffix or "").strip().lower()
    if domain and suffix:
        return f"{domain}.{suffix}"
    if domain:
        return domain
    return host


def host_lookup_candidates(value: str) -> List[Tuple[str, str]]:
    """
    Return host profile lookup candidates in priority order.

    Order:
      1) exact host
      2) registrable domain (if different from exact host)
    """
    exact = normalize_host(value)
    domain = registrable_domain(exact)
    candidates: List[Tuple[str, str]] = []
    if exact:
        candidates.append((exact, "exact"))
    if domain and domain != exact:
        candidates.append((domain, "domain"))
    return candidates


__all__ = [
    "normalize_host",
    "registrable_domain",
    "host_lookup_candidates",
]
