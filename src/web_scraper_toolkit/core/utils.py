# ./src/web_scraper_toolkit/core/utils.py
# WebScraperToolkit/src/web_scraper_toolkit/utils.py
from typing import Optional
from urllib.parse import urlparse, urljoin
import logging

logger = logging.getLogger(__name__)


def normalize_url(url: str, base_url: Optional[str] = None) -> Optional[str]:
    """Normalizes a URL, making it absolute if a base_url is provided."""
    try:
        if base_url:
            url = urljoin(base_url, url.strip())

        parsed = urlparse(url.strip())
        if not parsed.scheme or parsed.scheme not in ["http", "https"]:
            return None  # Scheme required and must be http/https
        if not parsed.netloc:
            return None  # Domain name required

        # Remove 'www.' prefix for consistency in domain comparison
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]

        # Reconstruct with lowercase scheme and netloc, and stripped path/query/fragment
        path = (
            parsed.path.rstrip("/") if parsed.path else ""
        )  # Remove trailing slash from path for consistency

        normalized = f"{parsed.scheme.lower()}://{netloc}{path}"
        if parsed.query:
            normalized += f"?{parsed.query}"

        return normalized
    except Exception as e:
        logger.debug(f"Failed to normalize URL '{url}': {e}")
        return None


def get_domain_from_url(url: str) -> Optional[str]:
    """Extracts the normalized domain (e.g., example.com) from a URL."""
    try:
        parsed_url = urlparse(url.lower())
        domain = parsed_url.netloc
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return None


def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncates text to a maximum length, adding ellipsis if truncated."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip() + "..."
