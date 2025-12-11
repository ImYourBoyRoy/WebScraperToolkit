# ./run_server.py
"""
Shim for local development.
Please use 'web-scraper-server' (or 'python -m web_scraper_toolkit.server.mcp_server')
when installed.
"""
from web_scraper_toolkit.server.mcp_server import main

if __name__ == "__main__":
    main()
