import sys
import os
import pkgutil
import importlib
import traceback

# Add src to path so we can import as if installed
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))


def verify_package(package_name):
    print(f"🔍 Verifying package: {package_name}")
    try:
        root_pkg = importlib.import_module(package_name)
        print(f"✅ Root import successful: {package_name}")
    except Exception as e:
        print(f"❌ Root import failed: {e}")
        traceback.print_exc()
        return

    # Walk through all submodules
    path = root_pkg.__path__
    prefix = package_name + "."

    for _, name, ispkg in pkgutil.walk_packages(path, prefix):
        print(f"   Checking {name}...", end=" ")
        try:
            importlib.import_module(name)
            print("✅ OK")
        except Exception as e:
            print("❌ FAILED")
            print(f"   Error: {e}")
            # traceback.print_exc()


if __name__ == "__main__":
    # verify_package("web_scraper_toolkit")
    try:
        importlib.import_module("web_scraper_toolkit.parsers.scraping_tools")
        print("✅ scraping_tools OK")
    except Exception:
        traceback.print_exc()
