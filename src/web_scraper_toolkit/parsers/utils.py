# ./src/web_scraper_toolkit/parsers/utils.py
"""
Parser Utilities
================

Helper definitions for text extraction, URL normalization, and data cleanup.
Used by serp_parser and other parsing modules.

Usage:
    norm_url = normalize_url("/foo", "https://base.com")

Key Functions:
    - normalize_url: Resolves relative links.
    - truncate_text: Safe string shortening.
"""

from urllib.parse import urljoin, urlparse
from typing import Optional

def normalize_url(url: str, base_url: str = "") -> Optional[str]:
    """
    Resolves relative URLs against a base URL.
    Returns None if URL is invalid or empty.
    Strips trailing slashes to canonicalize.
    """
    if not url:
        return None
    
    try:
        # Strip whitespace
        url = url.strip()
        
        # Handle javascript: links
        if url.startswith('javascript:') or url.startswith('#'):
            return None
            
        # Join
        full_url = urljoin(base_url, url)
        
        # Validate scheme
        parsed = urlparse(full_url)
        if parsed.scheme not in ['http', 'https']:
            return None
        
        # Canonicalize: Remove trailing slash if path > 1 (keep root /)
        if parsed.path.endswith('/') and len(parsed.path) > 1:
            full_url = full_url.rstrip('/')
            
        return full_url
        
    except Exception:
        return None

def truncate_text(text: str, max_length: int = 100) -> str:
    """
    Truncates text to max_length, appending '...' if truncated.
    """
    if not text:
        return ""
    
    clean_text = text.strip()
    if len(clean_text) <= max_length:
        return clean_text
        
    return clean_text[:max_length].rstrip() + "..."
