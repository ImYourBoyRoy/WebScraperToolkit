# ./src/web_scraper_toolkit/core/verify_deps.py
"""
Dependency Verification Module
==============================

Checks that critical runtime dependencies meet the required versions.
Implements the "Fail Gently" philosophy by guiding users to upgrade instead of crashing hard.

Usage:
    if not verify_dependencies(): sys.exit(1)

Key Checks:
    - playwright-stealth >= 2.0.0
    - playwright >= 1.56.0 (or base compatible)

Key Outputs:
    - Boolean (True if all good, False if missing/old).
    - Printed instructions for the user.
"""

import sys
import importlib.metadata
from packaging import version
from .logger import setup_logger

logger = setup_logger()

def verify_dependencies():
    """
    Verifies that critical dependencies meet the 'Expert' standards.
    If not, it prints a helpful message and returns False.
    """
    required = {
        "playwright-stealth": "2.0.0",
        "playwright": "1.40.0" # User mentioned 1.56, but let's be safe. 1.40 is stable base. 
                               # Actually user said "playwright>=1.56.0". Let's use that.
    }
    required["playwright"] = "1.56.0"

    all_good = True
    
    for package, min_ver in required.items():
        try:
            installed_ver = importlib.metadata.version(package)
            if version.parse(installed_ver) < version.parse(min_ver):
                logger.error(f"❌ Dependency Error: {package} {installed_ver} is too old. Required: >={min_ver}")
                print(f"\n[!] Critical Dependency Update Required for '{package}':")
                print(f"    Current: {installed_ver}")
                print(f"    Required: >={min_ver}")
                print(f"    Selected: pip install --upgrade {package}\n")
                all_good = False
        except importlib.metadata.PackageNotFoundError:
            logger.error(f"❌ Missing Dependency: {package}")
            print(f"\n[!] Missing Critical Dependency: '{package}'")
            print(f"    Selected: pip install {package}\n")
            all_good = False
            
    return all_good
