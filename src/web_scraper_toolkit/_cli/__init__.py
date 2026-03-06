# ./src/web_scraper_toolkit/_cli/__init__.py
"""
Internal CLI split package for argument parsing and runtime orchestration.
Used by web_scraper_toolkit.cli facade to provide stable entrypoint behavior.
Run: imported by cli module; no direct standalone invocation.
Inputs: CLI args, config paths, runtime dependency bundle, and mode flags.
Outputs: parsed Namespace objects and executed workflow side effects.
Side effects: reads config files, starts crawlers, writes outputs, exits on failures.
Operational notes: private package; public callers should continue using cli.py APIs.
"""

from .arguments import _normalize_diagnostic_name, parse_arguments
from .bootstrap import bootstrap_default_config_files, load_global_config
from .runner import run_main_async

__all__ = [
    "parse_arguments",
    "_normalize_diagnostic_name",
    "load_global_config",
    "bootstrap_default_config_files",
    "run_main_async",
]
