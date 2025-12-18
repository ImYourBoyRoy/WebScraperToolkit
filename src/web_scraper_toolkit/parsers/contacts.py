# ./src/web_scraper_toolkit/parsers/contacts.py
"""
Contact Extraction Tools
========================

Extracts emails, phone numbers, and social media links from text or HTML.
Relies on 'emailtoolkit' and 'phonenumbers' for robust parsing.

Usage:
    emails = extract_emails("Contact us at info@example.com", "https://example.com")
    phones = extract_phones("Call 555-0199", "https://example.com")
    socials = extract_socials(soup, "https://example.com")

"""

import logging
from typing import List, Dict, Any
from urllib.parse import urlparse

# Optional dependencies handling is tricky with Type Checking if we enforce them.
# But here they are required dependencies per user request.
import phonenumbers
import emailtoolkit

# Default social domains to look for
SOCIAL_DOMAINS = {
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "tiktok.com",
    "youtube.com",
    "pinterest.com",
    "github.com",
    "gitlab.com",
    "medium.com",
}

logger = logging.getLogger(__name__)


def _find_context(text: str, target: str, window: int = 30) -> str:
    """Finds text surrounding a target string."""
    try:
        idx = text.find(target)
        if idx == -1:
            return ""
        start = max(0, idx - window)
        end = min(len(text), idx + len(target) + window)
        return text[start:end].replace("\n", " ").strip()
    except Exception:
        return ""


def extract_emails(text: str, source_url: str = "") -> List[Dict[str, Any]]:
    """
    Extracts emails using emailtoolkit.
    Handles standard regex and Cloudflare encryption automatically by emailtoolkit.
    """
    if not text:
        return []

    try:
        found_emails = emailtoolkit.extract(text)
    except Exception as e:
        logger.warning(f"emailtoolkit extract failed: {e}")
        return []

    # Convert to list of dicts with context
    results = []
    seen = set()

    for em in found_emails:
        # emailtoolkit returns Email objects. Use .normalized or .canonical
        normalized = em.normalized
        if normalized in seen:
            continue
        seen.add(normalized)

        context = _find_context(
            text, em.original
        )  # Use original match for context search if possible?
        # Actually em.original is the string segment found.

        results.append(
            {
                "value": normalized,
                "type": "email",
                "source": source_url,
                "context": context,
            }
        )

    return results


def extract_phones(
    text: str, source_url: str = "", region: str = "US"
) -> List[Dict[str, Any]]:
    """
    Extracts phone numbers using Google's phonenumbers library.
    """
    results = []
    seen = set()

    if not text:
        return []

    try:
        for match in phonenumbers.PhoneNumberMatcher(text, region):
            phone_obj = match.number
            # Check validity
            if not phonenumbers.is_valid_number(phone_obj):
                continue

            # Format to International or National
            formatted = phonenumbers.format_number(
                phone_obj, phonenumbers.PhoneNumberFormat.NATIONAL
            )

            if formatted in seen:
                continue
            seen.add(formatted)

            # Context
            start, end = match.start, match.end
            context_snippet = (
                text[max(0, start - 30) : min(len(text), end + 30)]
                .replace("\n", " ")
                .strip()
            )

            results.append(
                {
                    "value": formatted,
                    "type": "phone",
                    "source": source_url,
                    "context": context_snippet,
                }
            )
    except Exception as e:
        # e.g. if phonenumbers is not installed or errors
        logger.warning(f"Phone extraction error: {e}")

    return results


def extract_socials(soup, source_url: str = "") -> List[Dict[str, Any]]:
    """
    Extracts social media links from a BeautifulSoup object.

    Args:
        soup: BeautifulSoup object
        source_url: The URL of the page being parsed (for logging/metadata)
    """
    results = []
    seen = set()

    if not soup:
        return []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        try:
            parsed = urlparse(href)
            domain = parsed.netloc.lower()
            # Handle www.
            if domain.startswith("www."):
                domain = domain[4:]

            if domain in SOCIAL_DOMAINS:
                # Clean URL (remove query params usually)
                clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

                # Deduplicate
                if clean_url in seen:
                    continue
                seen.add(clean_url)

                results.append(
                    {"value": clean_url, "type": "social", "source": source_url}
                )
        except Exception:
            continue

    return results


def extract_heuristic_names(soup) -> Dict[str, str]:
    """
    Attempts to guess the name of the business or author from metadata.

    Returns:
        Dict with keys 'business_name' and/or 'author_name' if found.
    """
    names = {}
    if not soup:
        return names

    # 1. Business Name (og:site_name)
    try:
        og_site = soup.find("meta", property="og:site_name")
        if og_site and og_site.get("content"):
            names["business_name"] = og_site["content"].strip()
    except Exception:
        pass

    # 2. Author Name (meta author)
    try:
        meta_author = soup.find("meta", attrs={"name": "author"})
        if meta_author and meta_author.get("content"):
            names["author_name"] = meta_author["content"].strip()
    except Exception:
        pass

    # 3. Heuristic: "Meet [Name]" in H1/H2 (Person)
    # Only if we haven't found an explicit author
    if "author_name" not in names:
        try:
            for tag in ["h1", "h2"]:
                for el in soup.find_all(tag):
                    text = el.get_text(strip=True)
                    if text.lower().startswith("meet "):
                        # "Meet Roy Dawson" -> "Roy Dawson"
                        candidate = text[5:].strip()
                        # Sanity check length
                        if 2 < len(candidate) < 50:
                            names["person_name_guess"] = candidate
                            break
                if "person_name_guess" in names:
                    break
        except Exception:
            pass

    return names
