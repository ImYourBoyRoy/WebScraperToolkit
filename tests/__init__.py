import logging
import sys
import os

# --- Expert Test Logging Strategy ---
# Goal: Suppress console noise during test execution while capturing strict debug logs to file.

# Ensure tests_output exists
OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../tests_output"))
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

LOG_FILE = os.path.join(OUTPUT_DIR, "tests_results.log")

# 1. Configure Root Logger to File Only
# We clear existing handlers first
root = logging.getLogger()
root.handlers = []

logging.basicConfig(
    filename=LOG_FILE,
    filemode="w",
    level=logging.DEBUG,
    encoding="utf-8",
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# 2. Monkeypatch `logging.basicConfig` to prevent sub-modules (like mcp_server)
# from overriding our configuration or adding new handlers.
original_basicConfig = logging.basicConfig


def noop_basicConfig(*args, **kwargs):
    pass


logging.basicConfig = noop_basicConfig

# 3. Monkeypatch `setup_logger` in core to prevent Console Handlers
# We need to import the module first.
try:
    import web_scraper_toolkit.core.logger

    def quiet_setup_logger(name="WebScraperToolkit", verbose=False, log_file=None):
        logger = logging.getLogger(name)
        # Verify it doesn't have console handlers?
        # Actually, since we control the root, stripping handlers here is good.
        if logger.handlers:
            logger.handlers.clear()

        # We DO NOT add a StreamHandler.
        # We rely on the Root Logger's FileHandler (propagation is True by default).
        return logger

    web_scraper_toolkit.core.logger.setup_logger = quiet_setup_logger

except ImportError:
    pass

# 4. Clean up specific loggers that might have already initialized
for name in ["WebScraperToolkit", "mcp_server", "web_scraper_toolkit"]:
    logging.getLogger(name).handlers = []
    logging.getLogger(name).propagate = True
