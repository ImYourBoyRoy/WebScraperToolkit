# ./src/web_scraper_toolkit/core/logger.py
"""
Logger Module
=============

Sets up the centralized logging configuration for the project.
Ensures consistent log formatting, levels, and output destinations.

Usage:
    params = setup_logger(verbose=True)

Key Inputs:
    - verbose: Boolean flag to enable DEBUG level logging.

Key Outputs:
    - Configured 'logging.Logger' instance.
"""

import logging
import sys
from typing import Optional

def setup_logger(name: str = "WebScraperToolkit", verbose: bool = False, log_file: Optional[str] = None) -> logging.Logger:
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
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File Handler
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
    return logger
