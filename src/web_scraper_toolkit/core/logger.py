# ./src/web_scraper_toolkit/core/logger.py
"""
Centralized logger setup utility shared by CLI, server handlers, and runtime modules.
Run: import `setup_logger` and call it during application startup or test bootstrapping.
Inputs: logger name, verbose toggle, and optional output log file path.
Outputs: configured `logging.Logger` instance with stdout and optional file handlers.
Side effects: clears existing handlers for the requested logger and mutates global logging state for that logger.
Operational notes: idempotent per-call for a logger name; designed to prevent duplicate handlers in repeated boots.
"""

import logging
import sys
from typing import Optional


def setup_logger(
    name: str = "WebScraperToolkit",
    verbose: bool = False,
    log_file: Optional[str] = None,
) -> logging.Logger:
    """
    Sets up a configured logger with standard formatting.

    Args:
        name: Logger name.
        verbose: If True, set level to DEBUG, else INFO.
        log_file: Optional path to log file.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name)

    # Reset handlers to avoid duplicates
    if logger.handlers:
        logger.handlers.clear()

    level = logging.DEBUG if verbose else logging.INFO
    logger.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File Handler
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
