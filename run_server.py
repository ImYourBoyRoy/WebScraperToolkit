# ./run_server.py
"""
MCP Server Launcher
===================

Convenience script to launch the Web Scraper Toolkit MCP Server.
Automatically handles path configuration so you can run it directly from the root.

Usage:
    python run_server.py
"""

import sys
import os

# Ensure src is in python path
sys.path.insert(0, os.path.abspath("src"))

try:
    from web_scraper_toolkit.server.mcp_server import main

    print("🚀 Starting WebScraperToolkit MCP Server...")
    main()
except ImportError as e:
    print(f"❌ Failed to import server: {e}")
    print("Ensure you have installed dependencies: pip install -e .")
    sys.exit(1)
except Exception as e:
    print(f"❌ Server crashed: {e}")
    sys.exit(1)
