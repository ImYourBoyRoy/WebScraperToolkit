# ./src/web_scraper_toolkit/__init__.py
"""
Expose the public WebScraperToolkit package API used by CLI, MCP, and Python imports.
Run: import this package directly (e.g., `import web_scraper_toolkit`) to access re-exported primitives.
Inputs: Python import calls and package metadata resolution during runtime/build/install workflows.
Outputs: stable symbols for configs, crawlers, diagnostics runners, parser helpers, and utility functions.
Side effects: imports submodules to bind public exports, which may initialize module-level constants/loggers.
Operational notes: this is the canonical API surface; keep exports intentional and synchronized with docs/tests.
"""

__version__ = "0.3.0"

# Configs (Modular)
from .browser.config import BrowserConfig
from .crawler.config import CrawlerConfig
from .parsers.config import ParserConfig
from .proxie.config import ProxieConfig
from .server.config import ServerConfig
from .core.logger import setup_logger
from .core.runtime import load_runtime_settings, resolve_worker_count
from .core.diagnostics import verify_environment, print_diagnostics
from .core.script_diagnostics import (
    ScriptDiagnosticsRunner,
    run_toolkit_route_diagnostic,
    run_challenge_matrix_diagnostic,
    run_bot_check_diagnostic,
    run_browser_info_diagnostic,
)
from .browser.playwright_handler import (
    PlaywrightManager,
    BotBlockReason,
    classify_bot_block,
)
from .browser.host_profiles import (
    HostProfileStore,
    normalize_host,
    sanitize_routing_profile,
)
from .browser.domain_identity import registrable_domain, host_lookup_candidates
from .browser.serp_native import (
    sanitize_headless_user_agent,
    build_serp_client_hints,
    is_serp_allowlisted,
    is_serp_blocked,
)
from .browser.playwright_crawler import WebCrawler
from .core.input import load_urls_from_source
from .crawler.engine import AutonomousCrawler
from .playbook.models import Playbook
from .parsers.html_to_markdown import MarkdownConverter
from .parsers.sitemap import (
    fetch_sitemap_content as fetch_sitemap,
    parse_sitemap_urls as parse_sitemap,
    extract_sitemap_tree,
)
from .parsers.discovery import smart_discover_urls
from .parsers.scraping_tools import (
    read_website_markdown,
    read_website_content,
    aread_website_markdown,
    capture_screenshot,
    save_as_pdf,
    extract_metadata,
)
from .parsers.extraction.contacts import (
    extract_emails,
    extract_phones,
    extract_socials,
)

__all__ = [
    # Configs
    "BrowserConfig",
    "CrawlerConfig",
    "ParserConfig",
    "ProxieConfig",
    "ServerConfig",
    "setup_logger",
    "load_runtime_settings",
    "resolve_worker_count",
    "verify_environment",
    "print_diagnostics",
    "ScriptDiagnosticsRunner",
    "run_toolkit_route_diagnostic",
    "run_challenge_matrix_diagnostic",
    "run_bot_check_diagnostic",
    "run_browser_info_diagnostic",
    "PlaywrightManager",
    "BotBlockReason",
    "classify_bot_block",
    "HostProfileStore",
    "normalize_host",
    "registrable_domain",
    "host_lookup_candidates",
    "sanitize_routing_profile",
    "sanitize_headless_user_agent",
    "build_serp_client_hints",
    "is_serp_allowlisted",
    "is_serp_blocked",
    "WebCrawler",
    "AutonomousCrawler",
    "Playbook",
    "load_urls_from_source",
    "MarkdownConverter",
    "fetch_sitemap",
    "parse_sitemap",
    "extract_sitemap_tree",
    "smart_discover_urls",
    "read_website_markdown",
    "read_website_content",
    "aread_website_markdown",
    "capture_screenshot",
    "save_as_pdf",
    "extract_metadata",
    "extract_emails",
    "extract_phones",
    "extract_socials",
]
