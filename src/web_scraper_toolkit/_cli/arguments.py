# ./src/web_scraper_toolkit/_cli/arguments.py
"""
CLI argument parser module split from the public cli.py facade.
Used by cli facade to keep public parse_arguments API compatibility.
Run: imported by cli facade/runner only.
Inputs: argv list and optional defaults dict.
Outputs: argparse Namespace with normalized toolkit flags.
Side effects: none.
Operational notes: preserves existing flags and backward-compatible aliases.
"""

from __future__ import annotations

import argparse
import os


def parse_arguments(args=None, defaults=None):
    defaults = defaults or {}
    parser = argparse.ArgumentParser(description="Web Scraper Toolkit CLI")

    parser.add_argument(
        "--diagnostics", action="store_true", help="Run diagnostic checks."
    )
    parser.add_argument(
        "--run-diagnostic",
        type=str,
        default=None,
        help=(
            "Run a standalone script diagnostic and exit. "
            "Supported: toolkit_route, challenge_matrix, bot_check, browser_info."
        ),
    )
    parser.add_argument(
        "--diagnostic-url",
        type=str,
        default=None,
        help="Target URL override for diagnostic tools that accept URL inputs.",
    )
    parser.add_argument(
        "--diagnostic-timeout-ms",
        type=int,
        default=45000,
        help="Timeout in milliseconds for supported diagnostic tools.",
    )
    parser.add_argument(
        "--diagnostic-extra-args",
        type=str,
        default="",
        help="Extra CLI args appended verbatim to the selected diagnostic script.",
    )
    parser.add_argument(
        "--diagnostic-auto-commit-host-profile",
        action="store_true",
        help=(
            "After toolkit diagnostics succeed, run a clean incognito verification and "
            "write host profile evidence."
        ),
    )
    parser.add_argument(
        "--diagnostic-host-profiles-file",
        type=str,
        default=None,
        help="Optional host profile store path override for diagnostic auto-commit.",
    )
    parser.add_argument(
        "--diagnostic-read-only",
        action="store_true",
        help="Force diagnostics to read-only mode (never write host profile updates).",
    )
    parser.add_argument(
        "--diagnostic-browser",
        choices=["chrome", "edge"],
        default="chrome",
        help="Browser channel for matrix diagnostics.",
    )
    parser.add_argument(
        "--diagnostic-runs-per-variant",
        type=int,
        default=1,
        help="Run count per variant for matrix diagnostics.",
    )
    parser.add_argument(
        "--diagnostic-variants",
        type=str,
        default="baseline,minimal_stealth,legacy_stealth",
        help="Variant list for matrix diagnostics.",
    )
    parser.add_argument(
        "--diagnostic-skip-interactive",
        action="store_true",
        help="Skip interactive stage when running toolkit diagnostics.",
    )
    parser.add_argument(
        "--diagnostic-include-headless-stage",
        action="store_true",
        help="Include optional headless stage in toolkit diagnostics.",
    )
    parser.add_argument(
        "--diagnostic-require-2xx",
        action="store_true",
        help="Require final HTTP 2xx status for toolkit diagnostic stage success.",
    )
    parser.add_argument(
        "--diagnostic-save-artifacts",
        action="store_true",
        help="Persist per-stage diagnostic artifacts for toolkit route diagnostics.",
    )
    parser.add_argument(
        "--diagnostic-artifacts-dir",
        type=str,
        default=None,
        help="Optional artifacts directory override for toolkit route diagnostics.",
    )
    parser.add_argument(
        "--diagnostic-headless",
        action="store_true",
        help="Run supported diagnostics in headless mode when available.",
    )
    parser.add_argument(
        "--diagnostic-hold-method",
        choices=["auto", "playwright", "os"],
        default="auto",
        help="Hold strategy for matrix diagnostics.",
    )
    parser.add_argument(
        "--diagnostic-hold-seconds",
        type=float,
        default=12.0,
        help="Press-and-hold duration for matrix diagnostics.",
    )
    parser.add_argument(
        "--diagnostic-browsers",
        type=str,
        default="chromium,pw_chrome,system_chrome",
        help="Browser list for bot_check diagnostics.",
    )
    parser.add_argument(
        "--diagnostic-modes",
        type=str,
        default="baseline,stealth",
        help="Mode list for bot_check diagnostics.",
    )
    parser.add_argument(
        "--diagnostic-prefer-system",
        choices=["chrome", "chromium", "edge"],
        default="chrome",
        help="Preferred system browser lookup for bot_check diagnostics.",
    )
    parser.add_argument(
        "--diagnostic-use-default-sites",
        action="store_true",
        help="Visit built-in detector sites during bot_check diagnostics.",
    )
    parser.add_argument(
        "--diagnostic-sites",
        type=str,
        default="",
        help="Additional comma-separated sites for bot_check diagnostics.",
    )
    parser.add_argument(
        "--diagnostic-screenshots",
        action="store_true",
        help="Capture screenshots during bot_check diagnostics.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging."
    )
    parser.add_argument(
        "--config",
        type=str,
        default=os.environ.get("WST_CONFIG_JSON", "config.json"),
        help="Path to primary JSON configuration file.",
    )
    parser.add_argument(
        "--local-config",
        type=str,
        default=os.environ.get("WST_LOCAL_CFG"),
        help="Path to local cfg override file (e.g. settings.local.cfg).",
    )

    parser.add_argument("--url", "-u", type=str, help="Target URL to scrape.")
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        help="Input file (txt, csv, json, xml sitemap) OR a single generic URL to crawl.",
    )
    parser.add_argument(
        "--crawl",
        action="store_true",
        help="If input is a single URL, crawl it for links (same domain).",
    )
    parser.add_argument(
        "--export", "-e", action="store_true", help="Export individual files."
    )
    parser.add_argument(
        "--contacts",
        action="store_true",
        help="Autonomously extract emails, phones, and socials.",
    )
    parser.add_argument(
        "--playbook",
        type=str,
        help="Path to a Playbook JSON file (enables Autonomous Mode).",
    )

    parser.add_argument(
        "--format",
        "-f",
        type=str,
        default="markdown",
        choices=[
            "markdown",
            "text",
            "html",
            "metadata",
            "screenshot",
            "pdf",
            "json",
            "xml",
            "csv",
        ],
        help="Output format.",
    )
    parser.add_argument(
        "--no-proxy",
        action="store_true",
        help="Force Direct Mode (ignore proxies.json even if present).",
    )

    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Run browser in headless mode (default: False/Visible).",
    )
    parser.add_argument(
        "--native-fallback-policy",
        choices=["off", "on_blocked", "always"],
        default=None,
        help="Native browser fallback policy when anti-bot blocks occur.",
    )
    parser.add_argument(
        "--native-browser-channels",
        type=str,
        default=None,
        help="Comma-separated native browser channel order, e.g. chrome,msedge.",
    )
    parser.add_argument(
        "--native-browser-headless",
        action="store_true",
        default=False,
        help="Run native fallback channel attempts in headless mode.",
    )
    parser.add_argument(
        "--native-context-mode",
        choices=["incognito", "persistent"],
        default=None,
        help="Context mode for native fallback attempts.",
    )
    parser.add_argument(
        "--native-profile-dir",
        type=str,
        default=None,
        help="Persistent profile directory for native fallback (when context mode is persistent).",
    )
    parser.add_argument(
        "--interactive-channel",
        choices=["chrome", "msedge", "chromium"],
        default=None,
        help="Preferred browser channel for MCP interactive session launches.",
    )
    parser.add_argument(
        "--interactive-context-mode",
        choices=["incognito", "persistent"],
        default=None,
        help="Context mode for MCP interactive sessions.",
    )
    parser.add_argument(
        "--interactive-profile-dir",
        type=str,
        default=None,
        help="Persistent profile directory for MCP interactive sessions.",
    )
    parser.add_argument(
        "--host-profiles-file",
        type=str,
        default=None,
        help="Path to host profile learning store JSON file.",
    )
    parser.add_argument(
        "--host-profiles-read-only",
        choices=["on", "off"],
        default=None,
        help="Apply host profiles but disable learning writes when set to 'on'.",
    )
    parser.add_argument(
        "--host-learning",
        choices=["on", "off"],
        default=None,
        help="Enable/disable host auto-learning telemetry updates.",
    )
    parser.add_argument(
        "--host-learning-threshold",
        type=int,
        default=None,
        help="Clean-incognito successes required to promote candidate profile.",
    )
    parser.add_argument(
        "--host-profile-host",
        type=str,
        default=None,
        help="Host key for profile admin actions (print/set).",
    )
    parser.add_argument(
        "--host-profile-json",
        type=str,
        default=None,
        help="JSON payload for manual --host-profile-host active routing override.",
    )

    parser.add_argument(
        "--merge",
        action="store_true",
        help="Merge all output content into a single file.",
    )
    parser.add_argument(
        "--workers",
        "-w",
        type=str,
        default=None,
        help=(
            "Number of concurrent workers. Accepts integer or auto/max/dynamic. "
            "If omitted, runtime config defaults are used."
        ),
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Delay (seconds) between requests per worker (default: 0).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=".",
        help="Directory to save final output files.",
    )
    parser.add_argument(
        "--temp-dir",
        type=str,
        default=None,
        help="Directory for intermediate files (cleaned if --clean is used).",
    )
    parser.add_argument(
        "--output-name", type=str, help="Filename for the final merged output."
    )
    parser.add_argument(
        "--clean", action="store_true", help="Delete intermediate files after merging."
    )
    parser.add_argument(
        "--site-tree",
        action="store_true",
        help="Extract URLs from sitemap input without crawling content. Saves as CSV/JSON/XML.",
    )
    return parser.parse_args(args)


def _normalize_diagnostic_name(value: str | None) -> str | None:
    if value is None:
        return None
    raw = value.strip().lower()
    alias_map = {
        "toolkit_route": "toolkit_route",
        "challenge_matrix": "challenge_matrix",
        "bot_check": "bot_check",
        "browser_info": "browser_info",
    }
    return alias_map.get(raw)
